"""Cadence → interval mapping for listing auto-update schedules."""
from datetime import timedelta

from carpark.repositories.listing_schedule_repository import ListingScheduleRepository

# 'manual' and 'instant' both map to None (no fixed polling interval). 'instant' is not
# scheduled via next_run_at — it's meant to be handled event-driven (triggered on vehicle
# save) by the future scheduler.
_MIN = {'1h': 60, '2h': 120, '3h': 180, '5h': 300, 'daily': 1440, 'manual': None, 'instant': None}

# Single source of truth for the accepted cadence values (route validation etc.).
VALID_CADENCES = frozenset(_MIN.keys())

_schedule_repo = ListingScheduleRepository()


def cadence_to_minutes(cadence: str):
    if cadence not in _MIN:
        raise ValueError(f'Unknown cadence: {cadence}')
    return _MIN[cadence]


def ensure_auto_schedule(vehicle_id: int, platform_type: str, now) -> None:
    """Default a vehicle to a 1h auto-update schedule on a SUCCESSFUL publish.

    Called from both the Shopify and Autovit publish routes (Task 7) right
    after a publish succeeds. If a `carpark_listing_schedules` row already
    exists for (vehicle_id, platform_type) — any cadence, including an
    explicit 'manual' choice — it is left completely untouched: this must
    never clobber a user's own setting. Only when NO row exists yet does it
    upsert one with cadence='1h', enabled=True, next_run_at=now+1h, so "auto-
    update on by default" actually takes effect instead of being a no-op.

    Task 8's backfill reuses this exact same get-then-upsert-if-absent rule
    for existing cars published before this default existed.
    """
    if _schedule_repo.get(vehicle_id, platform_type) is not None:
        return
    next_run_at = now + timedelta(minutes=cadence_to_minutes('1h'))
    _schedule_repo.upsert(vehicle_id, platform_type, '1h', True, next_run_at)
