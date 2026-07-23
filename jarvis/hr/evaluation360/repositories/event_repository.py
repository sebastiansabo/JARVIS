"""Append-only event log, nudge log (for the 1/day rate limit), and audit log."""
import json

from core.base_repository import BaseRepository


class EvalEventRepository(BaseRepository):
    """Writes eval_events / eval_nudges / eval_audit_log."""

    def emit(self, event_name, *, cycle_id=None, subject_id=None, assignment_id=None,
             actor_id=None, payload=None, device=None):
        """Record one of the nine event families (drives the indicator catalog)."""
        return self.execute(
            '''INSERT INTO eval_events
                 (event_name, cycle_id, subject_id, assignment_id, actor_id, payload, device)
               VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
            (event_name, cycle_id, subject_id, assignment_id, actor_id,
             json.dumps(payload or {}), device), returning=True,
        )

    def record_nudge(self, *, cycle_id, user_id, source='hr_manual'):
        return self.execute(
            'INSERT INTO eval_nudges (cycle_id, user_id, source) VALUES (%s,%s,%s) RETURNING id',
            (cycle_id, user_id, source), returning=True,
        )

    def nudges_today(self, user_id):
        """How many nudges this user already received today (rate-limit input)."""
        row = self.query_one(
            'SELECT COUNT(*) AS n FROM eval_nudges WHERE user_id = %s AND created_at::date = CURRENT_DATE',
            (user_id,))
        return (row or {}).get('n', 0)

    def audit(self, *, actor_id, action, entity_type=None, entity_id=None, details=None):
        return self.execute(
            '''INSERT INTO eval_audit_log (actor_id, action, entity_type, entity_id, details)
               VALUES (%s,%s,%s,%s,%s) RETURNING id''',
            (actor_id, action, entity_type, entity_id, json.dumps(details or {})),
            returning=True,
        )
