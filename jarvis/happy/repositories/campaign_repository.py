"""Campaign repository — admin CRUD, audience rules, and target materialization.

`refresh_targets` is the audience resolver: it turns declarative include/exclude
rules (happy.campaign_audience) into materialized rows in happy.campaign_targets.
Phase 0 correction: only `company` is fully populated, `department` partially;
the dimension→column map stays complete but the authoring UI exposes populated
dimensions only.
"""
import json
import logging

from core.base_repository import BaseRepository

logger = logging.getLogger("jarvis.happy.campaign_repository")

# Columns a client may set on create/update. Everything else (status, published_at,
# created_by, approved_by, timestamps) is managed by the service/repo.
_WRITABLE = (
    "slug", "kind", "tier", "placements", "locale", "kicker", "title", "summary",
    "body_md", "media_key", "media_alt", "cta_label", "cta_href", "cta_deeplink",
    "event_at", "ack_mode", "ack_deadline_at", "dismissible", "escalation",
    "starts_at", "ends_at", "source_type", "source_id",
)

# Audience dimension -> users column. Values are always bound as %s params; the
# column name comes only from this whitelist (never from user input).
_DIMENSION_COLUMNS = {
    "company": "company", "brand": "brand", "department": "department",
    "subdepartment": "subdepartment", "org_unit": "org_unit_id",
    "contract_status": "contract_status", "role": "role_id", "user": "id",
}


class CampaignRepository(BaseRepository):

    # -- CRUD -----------------------------------------------------------------

    def list(self, status=None, limit=100, offset=0):
        where, params = "", []
        if status:
            where = "WHERE status = %s"
            params.append(status)
        params.extend([limit, offset])
        return self.query_all(
            f"SELECT * FROM happy.campaigns {where} ORDER BY created_at DESC LIMIT %s OFFSET %s",
            params,
        )

    def get(self, campaign_id):
        return self.query_one("SELECT * FROM happy.campaigns WHERE id = %s", (campaign_id,))

    def create(self, data, created_by):
        cols, vals, params = ["created_by"], ["%s"], [created_by]
        for k in _WRITABLE:
            if k in data:
                cols.append(k)
                vals.append("%s")
                params.append(self._adapt(k, data[k]))
        sql = (
            f"INSERT INTO happy.campaigns ({', '.join(cols)}) "
            f"VALUES ({', '.join(vals)}) RETURNING *"
        )
        return self.execute(sql, params, returning=True)

    def update(self, campaign_id, data):
        sets, params = [], []
        for k in _WRITABLE:
            if k in data:
                sets.append(f"{k} = %s")
                params.append(self._adapt(k, data[k]))
        if not sets:
            return self.get(campaign_id)
        sets.append("updated_at = NOW()")
        params.append(campaign_id)
        return self.execute(
            f"UPDATE happy.campaigns SET {', '.join(sets)} WHERE id = %s RETURNING *",
            params, returning=True,
        )

    def set_status(self, campaign_id, status, user_id):
        """Transition status; on publish, stamp published_at + approved_by."""
        if status == "live":
            return self.execute(
                """UPDATE happy.campaigns
                      SET status = 'live', published_at = COALESCE(published_at, NOW()),
                          approved_by = %s, updated_at = NOW()
                    WHERE id = %s RETURNING *""",
                (user_id, campaign_id), returning=True,
            )
        return self.execute(
            "UPDATE happy.campaigns SET status = %s, updated_at = NOW() WHERE id = %s RETURNING *",
            (status, campaign_id), returning=True,
        )

    @staticmethod
    def _adapt(key, value):
        # JSONB column takes a JSON string; TEXT[] (placements) passes through as a list.
        if key == "escalation" and value is not None and not isinstance(value, str):
            return json.dumps(value)
        return value

    # -- audience -------------------------------------------------------------

    def get_audience(self, campaign_id):
        return self.query_all(
            "SELECT id, mode, dimension, value FROM happy.campaign_audience WHERE campaign_id = %s",
            (campaign_id,),
        )

    def replace_audience(self, campaign_id, rules):
        """Replace the campaign's declarative audience rules atomically."""
        def _work(cursor):
            cursor.execute("DELETE FROM happy.campaign_audience WHERE campaign_id = %s", (campaign_id,))
            for r in rules:
                if r.get("dimension") not in _DIMENSION_COLUMNS or r.get("mode") not in ("include", "exclude"):
                    raise ValueError(f"invalid audience rule: {r}")
                cursor.execute(
                    """INSERT INTO happy.campaign_audience (campaign_id, mode, dimension, value)
                       VALUES (%s, %s, %s, %s)""",
                    (campaign_id, r["mode"], r["dimension"], str(r["value"])),
                )
            return len(rules)
        return self.execute_many(_work)

    def _audience_where(self, rules):
        """Build a safe (sql, params) predicate over active users from audience rules."""
        includes = [r for r in rules if r["mode"] == "include"]
        excludes = [r for r in rules if r["mode"] == "exclude"]
        params = []

        def preds(rs):
            out = []
            for r in rs:
                col = _DIMENSION_COLUMNS[r["dimension"]]   # whitelisted column
                out.append(f'"{col}"::text = %s')
                params.append(str(r["value"]))
            return out

        inc = preds(includes)
        exc = preds(excludes)
        clause = "is_active"
        if inc:
            clause += " AND (" + " OR ".join(inc) + ")"
        if exc:
            clause += " AND NOT (" + " OR ".join(exc) + ")"
        return clause, params

    def preview_audience(self, rules):
        """Count + per-company cohort breakdown only — never a name list (spec §8.2)."""
        where, params = self._audience_where(rules)
        total = self.query_one(f"SELECT COUNT(*) AS n FROM users WHERE {where}", params)
        cohorts = self.query_all(
            f"""SELECT COALESCE(company, '(unknown)') AS company, COUNT(*) AS n
                  FROM users WHERE {where} GROUP BY 1 ORDER BY 2 DESC""",
            params,
        )
        return {"count": total["n"] if total else 0, "cohorts": cohorts}

    def refresh_targets(self, campaign_id, prune=False):
        """Materialize campaign_targets from the campaign's audience rules.

        prune=True  -> full recompute (delete + insert), used at publish.
        prune=False -> additive only, used nightly for new-joiner inheritance.
        Returns the number of targeted users.
        """
        rules = self.get_audience(campaign_id)
        where, params = self._audience_where(rules)

        def _work(cursor):
            if prune:
                cursor.execute("DELETE FROM happy.campaign_targets WHERE campaign_id = %s", (campaign_id,))
            cursor.execute(
                f"""INSERT INTO happy.campaign_targets (campaign_id, user_id)
                    SELECT %s, id FROM users WHERE {where}
                    ON CONFLICT (campaign_id, user_id) DO NOTHING""",
                [campaign_id] + params,
            )
            cursor.execute("SELECT COUNT(*) AS n FROM happy.campaign_targets WHERE campaign_id = %s", (campaign_id,))
            return cursor.fetchone()["n"]
        n = self.execute_many(_work)
        logger.info("happy: refreshed targets campaign=%s prune=%s -> %s users", campaign_id, prune, n)
        return n

    # -- quiz (admin) ---------------------------------------------------------

    def get_quiz(self, campaign_id):
        """Admin view — includes correct_index for editing."""
        return self.query_all(
            "SELECT id, position, prompt, options, correct_index "
            "FROM happy.quiz_questions WHERE campaign_id = %s ORDER BY position",
            (campaign_id,),
        )

    def replace_quiz(self, campaign_id, questions):
        """Replace a campaign's quiz questions atomically. Validates shape."""
        def _work(cursor):
            cursor.execute("DELETE FROM happy.quiz_questions WHERE campaign_id = %s", (campaign_id,))
            for i, q in enumerate(questions, start=1):
                options = q.get("options")
                if not q.get("prompt") or not isinstance(options, list) or len(options) < 2:
                    raise ValueError(f"quiz question {i}: prompt + >=2 options required")
                ci = q.get("correct_index")
                if not isinstance(ci, int) or ci < 0 or ci >= len(options):
                    raise ValueError(f"quiz question {i}: correct_index out of range")
                position = q.get("position", i)
                cursor.execute(
                    """INSERT INTO happy.quiz_questions (campaign_id, position, prompt, options, correct_index)
                       VALUES (%s, %s, %s, %s::jsonb, %s)""",
                    (campaign_id, position, q["prompt"], json.dumps(options), ci),
                )
            return len(questions)
        return self.execute_many(_work)

    # -- compliance -----------------------------------------------------------

    # -- Board analytics (§10) ------------------------------------------------

    def get_stats(self, campaign_id):
        """Rollups only — raw events are never exposed (spec §8.2). The funnel
        sums per-day engagement (approximate uniques, since raw events purge at
        30 days); acknowledged is exact from happy.acknowledgements."""
        daily = self.query_all(
            """SELECT day, cohort_key, targeted, reached, read_8s, clicked, acknowledged, dismissed
                 FROM happy.campaign_daily_stats WHERE campaign_id = %s ORDER BY day""",
            (campaign_id,),
        )
        funnel = self.query_one(
            """SELECT COALESCE(MAX(targeted),0) targeted, COALESCE(SUM(reached),0) reached,
                      COALESCE(SUM(read_8s),0) read_8s, COALESCE(SUM(clicked),0) clicked,
                      COALESCE(SUM(dismissed),0) dismissed
                 FROM happy.campaign_daily_stats WHERE campaign_id = %s""",
            (campaign_id,),
        ) or {}
        ack = self.query_one("SELECT count(*) c FROM happy.acknowledgements WHERE campaign_id = %s", (campaign_id,))
        funnel["acknowledged"] = ack["c"] if ack else 0
        return {"daily": daily, "funnel": funnel}

    def board_health(self):
        """KPI summary for Happy Board (§2/§10). Aggregates only — no per-person data."""
        live = self.query_one("SELECT count(*) c FROM happy.campaigns WHERE status = 'live'")
        backlog = self.query_one(
            """SELECT count(*) c, MIN(c.ack_deadline_at) oldest
                 FROM happy.campaigns c
                 JOIN happy.campaign_targets t ON t.campaign_id = c.id
                 LEFT JOIN happy.acknowledgements a ON a.campaign_id = c.id AND a.user_id = t.user_id
                WHERE c.status = 'live' AND c.ack_mode <> 'none' AND a.id IS NULL""")
        kudos = self.query_one("SELECT count(*) c FROM happy.kudos WHERE created_at >= NOW() - INTERVAL '7 days'")
        flagged = self.query_one("SELECT count(*) c FROM happy.kudos WHERE flagged")
        pulse = self.query_one(
            """SELECT p.id, p.title, p.status,
                      (SELECT count(*) FROM happy.pulse_responses r WHERE r.pulse_id = p.id) responses,
                      (SELECT count(*) FROM happy.pulse_invites i WHERE i.pulse_id = p.id) invited
                 FROM happy.pulses p WHERE p.status IN ('live','closed')
                ORDER BY p.created_at DESC LIMIT 1""")
        return {
            "live_campaigns": (live or {}).get("c", 0),
            "open_ack_backlog": {"count": (backlog or {}).get("c", 0), "oldest_deadline": (backlog or {}).get("oldest")},
            "kudos_last_7d": (kudos or {}).get("c", 0),
            "flagged_kudos": (flagged or {}).get("c", 0),
            "latest_pulse": pulse,
        }

    def compliance_export(self, campaign_id):
        """The one legitimate per-person export (spec §8.2): the acknowledgement
        list for a campaign — targeted users and their ack state. Identified by
        user_id only; no engagement history."""
        return self.query_all(
            """SELECT t.user_id,
                      (a.id IS NOT NULL) AS acknowledged,
                      a.acknowledged_at, a.method
                 FROM happy.campaign_targets t
                 LEFT JOIN happy.acknowledgements a
                        ON a.campaign_id = t.campaign_id AND a.user_id = t.user_id
                WHERE t.campaign_id = %s
                ORDER BY acknowledged, t.user_id""",
            (campaign_id,),
        )
