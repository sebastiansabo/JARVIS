"""Pulse repository — anonymous surveys / eNPS (spec §7.5).

The anonymity architecture is the product: pulse_responses has NO user_id;
cohort_key is the smallest ancestor org node (Sincron organigram) whose subtree
has >= min_group_size members, else the company; results suppress any cohort with
fewer than min_group_size RESPONSES. Idempotency uses pulse_invites.responded
(a boolean, never joined to responses).
"""
import json
import logging
from collections import defaultdict

from core.base_repository import BaseRepository
from core.organization.ghost import ghost_exclude_clause

logger = logging.getLogger("jarvis.happy.pulse_repository")


class PulseError(ValueError):
    """Raised on invalid pulse operations; str(e) is a stable machine code."""


def _anonymity_notice(pulse):
    mgs = pulse.get("min_group_size", 5)
    return (
        f"Răspunsurile sunt anonime. Nu stocăm cine a răspuns — doar rezultate "
        f"agregate pe grupuri de cel puțin {mgs} persoane. Grupurile mai mici "
        f"sunt combinate cu unitatea superioară, iar data este păstrată fără oră."
    )


class PulseRepository(BaseRepository):

    # -- cohort engine (anonymity) -------------------------------------------

    def resolve_cohort(self, user_id, min_group_size=5):
        """Smallest ancestor org node with subtree >= min_group_size members,
        else the user's company, else 'all'. Robust if the organigram is absent.

        Ghost-user note (task 9): the `se.mapped_jarvis_user_id = %s` lookup
        below resolves the CALLING/responding user's OWN node (self-access,
        same shape as dept-pulse's `_ELIGIBLE_SQL` in task 8) — it must not
        gain a ghost filter, since a ghost still needs their own cohort key
        resolved to respond to a pulse. The function returns a cohort-key
        STRING ('node:<id>' / 'company:<id>'), never a list of user rows, so
        there is no audience to filter here in the first place."""
        try:
            row = self.query_one(
                """SELECT som.node_id, n.company_id
                     FROM sincron_employees se
                     JOIN sincron_org_members som
                       ON som.sincron_employee_id = se.sincron_employee_id
                      AND som.company_name = se.company_name
                     JOIN sincron_org_nodes n ON n.id = som.node_id
                    WHERE se.mapped_jarvis_user_id = %s AND se.is_active = TRUE
                    LIMIT 1""",
                (user_id,),
            )
        except Exception:
            row = None
        if not row:
            u = self.query_one("SELECT company_id FROM users WHERE id = %s", (user_id,))
            cid = (u or {}).get("company_id")
            return f"company:{cid}" if cid else "all"

        ancestors = self.query_all(
            """WITH RECURSIVE a AS (
                   SELECT id, parent_id, level FROM sincron_org_nodes WHERE id = %s
                   UNION ALL
                   SELECT p.id, p.parent_id, p.level FROM sincron_org_nodes p JOIN a ON p.id = a.parent_id)
               SELECT id, level FROM a ORDER BY level DESC""",
            (row["node_id"],),
        )
        for anc in ancestors:
            if self._subtree_members(anc["id"]) >= min_group_size:
                return f"node:{anc['id']}"
        return f"company:{row['company_id']}"

    def _subtree_members(self, node_id):
        """Distinct-employee headcount for a subtree, used only to size the
        anonymity threshold for `resolve_cohort`. Ghost-user note (task 9):
        this returns a scalar COUNT, not a list of user/employee rows — no
        identity is enumerated or exposed — and it counts raw Sincron
        org-membership rows (sincron_employee_id/company_name), which are
        not even joined to `users`/mapped_jarvis_user_id here. There is no
        user column to splice a ghost filter onto without inventing a join
        that this headcount doesn't otherwise need, so it is left
        unfiltered (a ghost's own headcount presence only affects which
        ancestor node is picked as the cohort boundary, never who is
        identified)."""
        r = self.query_one(
            """WITH RECURSIVE d AS (
                   SELECT id FROM sincron_org_nodes WHERE id = %s
                   UNION ALL
                   SELECT sn.id FROM sincron_org_nodes sn JOIN d ON sn.parent_id = d.id)
               SELECT count(DISTINCT m.sincron_employee_id || '|' || m.company_name) c
                 FROM d JOIN sincron_org_members m ON m.node_id = d.id""",
            (node_id,),
        )
        return r["c"] if r else 0

    # -- admin authoring ------------------------------------------------------

    def list(self, status=None):
        where, params = ("WHERE status = %s", [status]) if status else ("", [])
        return self.query_all(f"SELECT * FROM happy.pulses {where} ORDER BY created_at DESC", params)

    def get_pulse(self, pulse_id):
        return self.query_one("SELECT * FROM happy.pulses WHERE id = %s", (pulse_id,))

    def get_questions(self, pulse_id):
        return self.query_all(
            "SELECT id, position, prompt_ro, prompt_en, qtype, driver "
            "FROM happy.pulse_questions WHERE pulse_id = %s ORDER BY position",
            (pulse_id,),
        )

    def create(self, data, created_by):
        return self.execute(
            """INSERT INTO happy.pulses (slug, title, cadence, question_count, min_group_size,
                                         min_comment_group, indirect_protection, created_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
            (data["slug"], data["title"], data.get("cadence", "adhoc"),
             data.get("question_count", 5), data.get("min_group_size", 5),
             data.get("min_comment_group", 10), data.get("indirect_protection", True), created_by),
            returning=True,
        )

    def replace_questions(self, pulse_id, questions):
        pulse = self.get_pulse(pulse_id)
        if pulse and pulse.get("settings_locked_at"):
            raise PulseError("settings_locked")   # immutable after launch (§7.5)

        def _work(cursor):
            cursor.execute("DELETE FROM happy.pulse_questions WHERE pulse_id = %s", (pulse_id,))
            for i, q in enumerate(questions, start=1):
                if q.get("qtype") not in ("likert5", "enps", "single", "open") or not q.get("prompt_ro"):
                    raise PulseError(f"invalid_question_{i}")
                cursor.execute(
                    """INSERT INTO happy.pulse_questions (pulse_id, position, prompt_ro, prompt_en, qtype, driver)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (pulse_id, q.get("position", i), q["prompt_ro"], q.get("prompt_en"),
                     q["qtype"], q.get("driver")),
                )
            return len(questions)
        return self.execute_many(_work)

    def open_pulse(self, pulse_id, now, audience_user_ids=None):
        """Go live: lock settings, stamp opens_at, and build the invite list
        (default: all active users). Invites exist only to send + remind."""
        pulse = self.get_pulse(pulse_id)
        if not pulse:
            raise PulseError("not_found")
        if pulse["status"] != "draft":
            raise PulseError("not_draft")
        if not self.get_questions(pulse_id):
            raise PulseError("no_questions")

        def _work(cursor):
            cursor.execute(
                "UPDATE happy.pulses SET status='live', opens_at=%s, "
                "settings_locked_at=COALESCE(settings_locked_at, %s) WHERE id=%s",
                (now, now, pulse_id),
            )
            if audience_user_ids is None:
                # Default audience = every active user, materialized here —
                # this is the real enrollment site, so ghosts are ALWAYS
                # excluded (viewer_id=None), regardless of who opened the
                # pulse (task 9).
                gfrag, gargs = ghost_exclude_clause('id', viewer_id=None)
                cursor.execute(
                    "INSERT INTO happy.pulse_invites (pulse_id, user_id) "
                    f"SELECT %s, id FROM users WHERE is_active{gfrag} ON CONFLICT DO NOTHING",
                    (pulse_id, *gargs))
            else:
                # Explicit admin-picked id list (not a broad cohort
                # materialization) — task 9's brief scopes the ghost fix to
                # "INSERT...SELECT of an audience", i.e. the branch above.
                for uid in audience_user_ids:
                    cursor.execute(
                        "INSERT INTO happy.pulse_invites (pulse_id, user_id) VALUES (%s, %s) "
                        "ON CONFLICT DO NOTHING", (pulse_id, uid))
            cursor.execute("SELECT count(*) c FROM happy.pulse_invites WHERE pulse_id=%s", (pulse_id,))
            return cursor.fetchone()["c"]
        return self.execute_many(_work)

    def close_pulse(self, pulse_id, now):
        """Close and DROP the invite list (spec §7.5 — dropped at close)."""
        def _work(cursor):
            cursor.execute("UPDATE happy.pulses SET status='closed', closes_at=%s WHERE id=%s", (now, pulse_id))
            cursor.execute("DELETE FROM happy.pulse_invites WHERE pulse_id=%s", (pulse_id,))
            return True
        return self.execute_many(_work)

    # -- respondent -----------------------------------------------------------

    def get_current(self, user_id):
        pulse = self.query_one("SELECT * FROM happy.pulses WHERE status='live' ORDER BY opens_at DESC LIMIT 1")
        if not pulse:
            return None
        inv = self.query_one(
            "SELECT responded FROM happy.pulse_invites WHERE pulse_id=%s AND user_id=%s", (pulse["id"], user_id))
        return {
            "pulse": {"id": pulse["id"], "slug": pulse["slug"], "title": pulse["title"],
                      "cadence": pulse["cadence"], "closes_at": pulse["closes_at"]},
            "questions": self.get_questions(pulse["id"]),
            "invited": inv is not None,
            "responded": bool(inv and inv["responded"]),
            "anonymity_notice": _anonymity_notice(pulse),
        }

    def respond(self, pulse_id, user_id, answers, now):
        pulse = self.get_pulse(pulse_id)
        if not pulse or pulse["status"] != "live":
            raise PulseError("not_open")
        cohort = self.resolve_cohort(user_id, pulse["min_group_size"])   # resolved OUTSIDE the txn

        def _work(cursor):
            cursor.execute(
                "SELECT responded FROM happy.pulse_invites WHERE pulse_id=%s AND user_id=%s FOR UPDATE",
                (pulse_id, user_id))
            inv = cursor.fetchone()
            if inv is None:
                raise PulseError("not_invited")
            if inv["responded"]:
                raise PulseError("already_responded")
            cursor.execute(
                "INSERT INTO happy.pulse_responses (pulse_id, cohort_key, answers) VALUES (%s, %s, %s::jsonb)",
                (pulse_id, cohort, json.dumps(answers)))
            cursor.execute(
                "UPDATE happy.pulse_invites SET responded=TRUE WHERE pulse_id=%s AND user_id=%s",
                (pulse_id, user_id))
            return {"ok": True}
        return self.execute_many(_work)

    # -- results (threshold-enforced) ----------------------------------------

    def get_results(self, pulse_id):
        pulse = self.get_pulse(pulse_id)
        if not pulse:
            return None
        mgs = pulse["min_group_size"]
        questions = self.get_questions(pulse_id)
        responses = self.query_all(
            "SELECT cohort_key, answers FROM happy.pulse_responses WHERE pulse_id=%s", (pulse_id,))
        invited_row = self.query_one("SELECT count(*) c FROM happy.pulse_invites WHERE pulse_id=%s", (pulse_id,))
        invited = invited_row["c"] if invited_row else 0
        total = len(responses)

        def agg(rows):
            out = {}
            for q in questions:
                key = f"q{q['position']}"
                vals = [r["answers"].get(key) for r in rows if isinstance(r["answers"].get(key), (int, float))]
                if not vals:
                    continue
                if q["qtype"] == "enps":
                    promoters = sum(1 for v in vals if v >= 9)
                    detractors = sum(1 for v in vals if v <= 6)
                    out[key] = {"type": "enps", "n": len(vals),
                                "nps": round(100 * (promoters - detractors) / len(vals))}
                elif q["qtype"] in ("likert5", "single"):
                    out[key] = {"type": q["qtype"], "n": len(vals),
                                "avg": round(sum(vals) / len(vals), 2), "driver": q.get("driver")}
            return out

        by_cohort = defaultdict(list)
        for r in responses:
            by_cohort[r["cohort_key"]].append(r)
        cohorts = {}
        for ck, rows in by_cohort.items():
            cohorts[ck] = (agg(rows) if len(rows) >= mgs
                           else {"suppressed": True, "reason": "below_min_group_size", "n": len(rows)})

        return {
            "pulse_id": pulse_id,
            "min_group_size": mgs,
            "participation": {"responses": total, "invited": invited,
                              "rate": round(total / invited, 3) if invited else None},
            "overall": (agg(responses) if total >= mgs
                        else {"suppressed": True, "reason": "below_min_group_size", "n": total}),
            "cohorts": cohorts,
        }
