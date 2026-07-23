"""HR nudges — rate-limited to 1 per user per day, platform-wide (spec §9).

Backed by the eval_nudges table rather than the in-memory RateLimiter, so the
limit survives restarts and holds across workers.
"""
from hr.evaluation360.repositories.event_repository import EvalEventRepository

NUDGE_DAILY_LIMIT = 1


class NudgeRateLimited(Exception):
    """Raised when a user has already been nudged the max times today."""


class NudgeService:
    def __init__(self, event_repo=None):
        self.events = event_repo or EvalEventRepository()

    def can_nudge(self, user_id):
        return self.events.nudges_today(user_id) < NUDGE_DAILY_LIMIT

    def nudge(self, cycle_id, user_id, source='hr_manual', actor_id=None):
        if not self.can_nudge(user_id):
            raise NudgeRateLimited(f'user {user_id} already nudged today')
        self.events.record_nudge(cycle_id=cycle_id, user_id=user_id, source=source)
        self.events.emit('nudge.sent', cycle_id=cycle_id, subject_id=user_id,
                         actor_id=actor_id, payload={'source': source})
        return True
