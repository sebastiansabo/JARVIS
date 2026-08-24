"""Surface repository — the resolver's data provider + the event/state write path.

All reads the SurfaceResolver needs, plus impression/read/click/ack/snooze/dismiss
writes and the daily frequency ledger. Raw SQL, %s params, no ORM.
"""
import json
import logging
from datetime import datetime

from core.base_repository import BaseRepository
from happy.services.quiz import grade_quiz

logger = logging.getLogger("jarvis.happy.surface_repository")

# Placements that count against the per-day frequency governor.
_CAPPED_PLACEMENTS = ("interstitial", "dash_banner")

# BaseRepository.dict_from_row serializes datetimes to ISO strings for JSON. The
# resolver compares them against `now`, so revive these fields back to datetime.
_CAMPAIGN_DT = ("starts_at", "ends_at", "ack_deadline_at", "created_at", "event_at",
                "published_at", "updated_at")
_STATE_DT = ("snoozed_until", "dismissed_until", "first_seen_at")


def _to_dt(value):
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return value
    return value


def _revive(row, fields):
    for f in fields:
        if f in row:
            row[f] = _to_dt(row[f])
    return row


class SurfaceRepository(BaseRepository):

    # -- resolver reads -------------------------------------------------------

    def get_live_campaigns(self):
        """All live campaigns (window filtering happens in the resolver)."""
        return [_revive(r, _CAMPAIGN_DT)
                for r in self.query_all("SELECT * FROM happy.campaigns WHERE status = 'live'")]

    def get_targeted_campaign_ids(self, user_id):
        rows = self.query_all(
            "SELECT campaign_id FROM happy.campaign_targets WHERE user_id = %s",
            (user_id,),
        )
        return {r["campaign_id"] for r in rows}

    def is_targeted(self, campaign_id, user_id):
        """Whether the user is in the materialized audience for this campaign."""
        return self.query_one(
            "SELECT 1 AS ok FROM happy.campaign_targets WHERE campaign_id = %s AND user_id = %s",
            (campaign_id, user_id),
        ) is not None

    def get_user_states(self, user_id):
        """Merge campaign_state (snooze/dismiss) with acknowledgements into one map."""
        states = {}
        for r in self.query_all(
            """SELECT campaign_id, snooze_count, snoozed_until, dismissed_until, first_seen_at
                 FROM happy.campaign_state WHERE user_id = %s""",
            (user_id,),
        ):
            states[r["campaign_id"]] = {
                "snooze_count": r["snooze_count"],
                "snoozed_until": _to_dt(r["snoozed_until"]),
                "dismissed_until": _to_dt(r["dismissed_until"]),
                "first_seen_at": _to_dt(r["first_seen_at"]),
                "acknowledged": False,
            }
        for r in self.query_all(
            "SELECT campaign_id FROM happy.acknowledgements WHERE user_id = %s",
            (user_id,),
        ):
            states.setdefault(r["campaign_id"], {})["acknowledged"] = True
        return states

    def get_frequency(self, user_id, day):
        rows = self.query_all(
            "SELECT placement, shown_count FROM happy.frequency_ledger WHERE user_id = %s AND day = %s",
            (user_id, day),
        )
        return {r["placement"]: r["shown_count"] for r in rows}

    # -- resolver / event writes ---------------------------------------------

    def audit(self, action, campaign_id=None, actor_user_id=None, detail=None):
        """Write a durable audit row (survives the 30-day campaign_events purge)."""
        self.execute(
            """INSERT INTO happy.audit_log (campaign_id, actor_user_id, action, detail)
               VALUES (%s, %s, %s, %s::jsonb)""",
            (campaign_id, actor_user_id, action, json.dumps(detail or {})),
        )

    def record_cap_override(self, user_id, campaign_id, placement, now):
        """Audit a critical campaign that bypassed the daily cap (spec §5.2)."""
        logger.warning(
            "happy: critical cap-override user=%s campaign=%s placement=%s",
            user_id, campaign_id, placement,
        )
        self.audit("cap_override", campaign_id, user_id, {"placement": placement})

    # -- quiz (§5.4) ----------------------------------------------------------

    def get_quiz(self, campaign_id, include_answers=False):
        cols = "id, position, prompt, options" + (", correct_index" if include_answers else "")
        return self.query_all(
            f"SELECT {cols} FROM happy.quiz_questions WHERE campaign_id = %s ORDER BY position",
            (campaign_id,),
        )

    def record_quiz_attempt(self, campaign_id, answers):
        """Grade an attempt, update AGGREGATE per-question stats (no user_id, no
        per-person answers), and return the grade result (with reveal for wrong)."""
        questions = self.get_quiz(campaign_id, include_answers=True)
        result = grade_quiz(questions, answers)
        correct_by_pos = {r["position"]: r["correct"] for r in result["results"]}

        def _work(cursor):
            for q in questions:
                inc = 1 if correct_by_pos.get(q["position"]) else 0
                cursor.execute(
                    """INSERT INTO happy.quiz_question_stats (question_id, attempts, first_correct)
                       VALUES (%s, 1, %s)
                       ON CONFLICT (question_id) DO UPDATE
                         SET attempts = happy.quiz_question_stats.attempts + 1,
                             first_correct = happy.quiz_question_stats.first_correct + %s""",
                    (q["id"], inc, inc),
                )
            return True
        if questions:
            self.execute_many(_work)
        return result

    def record_event(self, campaign_id, user_id, surface, event_type, dwell_ms=None, platform="web"):
        """Log a raw analytics event (30-day retention). Fire-and-forget."""
        self.execute(
            """INSERT INTO happy.campaign_events
                   (campaign_id, user_id, surface, event_type, dwell_ms, platform)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (campaign_id, user_id, surface, event_type, dwell_ms, platform),
        )
        if event_type == "impression" and surface in _CAPPED_PLACEMENTS:
            self._bump_frequency(user_id, surface)

    def _bump_frequency(self, user_id, placement):
        self.execute(
            """INSERT INTO happy.frequency_ledger (user_id, day, placement, shown_count)
               VALUES (%s, CURRENT_DATE, %s, 1)
               ON CONFLICT (user_id, day, placement)
               DO UPDATE SET shown_count = happy.frequency_ledger.shown_count + 1""",
            (user_id, placement),
        )

    def record_ack(self, campaign_id, user_id, method, surface):
        """Idempotent acknowledgement (compliance record). Returns True on first write."""
        row = self.execute(
            """INSERT INTO happy.acknowledgements (campaign_id, user_id, method, surface)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (campaign_id, user_id) DO NOTHING
               RETURNING id""",
            (campaign_id, user_id, method, surface),
            returning=True,
        )
        self.record_event(campaign_id, user_id, surface, "ack")
        return row is not None

    def snooze(self, campaign_id, user_id, now, hours=24, max_snoozes=3):
        """Snooze for N hours; snooze_count is capped at max_snoozes (server-enforced)."""
        def _work(cursor):
            cursor.execute(
                """INSERT INTO happy.campaign_state (campaign_id, user_id, snooze_count, snoozed_until, first_seen_at)
                   VALUES (%s, %s, 1, %s + make_interval(hours => %s), NOW())
                   ON CONFLICT (campaign_id, user_id) DO UPDATE
                     SET snooze_count = LEAST(happy.campaign_state.snooze_count + 1, %s),
                         snoozed_until = %s + make_interval(hours => %s),
                         updated_at = NOW()
                   RETURNING snooze_count""",
                (campaign_id, user_id, now, hours, max_snoozes, now, hours),
            )
            return cursor.fetchone()["snooze_count"]
        count = self.execute_many(_work)
        self.record_event(campaign_id, user_id, "interstitial", "snooze")
        return count

    def dismiss(self, campaign_id, user_id, now, days=7):
        """Dismiss persists for N days per item per user (Marquee, spec §6.4)."""
        self.execute(
            """INSERT INTO happy.campaign_state (campaign_id, user_id, dismiss_count, dismissed_until, first_seen_at)
               VALUES (%s, %s, 1, %s + make_interval(days => %s), NOW())
               ON CONFLICT (campaign_id, user_id) DO UPDATE
                 SET dismiss_count = happy.campaign_state.dismiss_count + 1,
                     dismissed_until = %s + make_interval(days => %s),
                     updated_at = NOW()""",
            (campaign_id, user_id, now, days, now, days),
        )
        self.record_event(campaign_id, user_id, "dash_banner", "dismiss")

    def get_open_acks(self, user_id):
        """Campaigns targeted to the user that require ack and are not yet acked."""
        return self.query_all(
            """SELECT c.id, c.slug, c.title, c.tier, c.ack_mode, c.ack_deadline_at
                 FROM happy.campaigns c
                 JOIN happy.campaign_targets t ON t.campaign_id = c.id AND t.user_id = %s
                 LEFT JOIN happy.acknowledgements a ON a.campaign_id = c.id AND a.user_id = %s
                WHERE c.status = 'live' AND c.ack_mode <> 'none' AND a.id IS NULL
                ORDER BY c.ack_deadline_at ASC NULLS LAST""",
            (user_id, user_id),
        )
