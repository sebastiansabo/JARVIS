"""Task 8: backfill a 1h auto-update schedule for cars that were already
published/live on Shopify or Autovit before Task 7 introduced
`ensure_auto_schedule()` (default-on-publish).

Without this one-off backfill, a car that was published prior to Task 7
would simply never get an auto-update schedule row — `carpark_listing_schedules`
rows today only appear either via a fresh publish (which now calls
`ensure_auto_schedule`) or an explicit user choice in the UI. This script
closes that gap for the existing fleet.

Does NOT import the Flask `app` module (jarvis/app.py's `create_app()` starts
a background scheduler thread as an import-time side effect — see
reference_database_init_on_import / the init_db-on-import gotcha). It only
imports repositories, which go through `core.base_repository` -> `database.py`
(whose module-level `init_db()` is idempotent schema setup — the same cost
every other repository-based script/test in this codebase already accepts).
Never queries with raw f-string SQL: the one platform_type parameter is
passed positionally via `%s`.

Idempotent + re-runnable: delegates the actual create-or-skip decision to
`carpark.connectors.cadence.ensure_auto_schedule`, which is a documented
no-op whenever a `carpark_listing_schedules` row already exists for
(vehicle_id, platform_type) — including an explicit cadence='manual' row.
So re-running this script, or running it after Task 7's routes have already
created rows for some vehicles, never clobbers anything; this module only
adds its own `_schedule_repo.get()` peek beforehand so it can report
accurate counts of what actually happened.

Usage (from the jarvis/ dir):
    DATABASE_URL=... python scripts/backfill_listing_schedules.py
"""
from datetime import datetime, timezone

from carpark.connectors import cadence
from carpark.connectors.cadence import ensure_auto_schedule
from carpark.repositories.publishing_repository import PublishingRepository
from carpark.repositories.autovit_listing_repository import AutovitListingRepository

_pub_repo = PublishingRepository()
_autovit_repo = AutovitListingRepository()


def _ensure_and_count(vehicle_id: int, platform_type: str, now, counts: dict, created_key: str) -> None:
    """Peek at whether a schedule row already exists (purely for counting —
    the create-or-skip decision itself still lives entirely in
    ensure_auto_schedule), then delegate to it."""
    already_had_row = cadence._schedule_repo.get(vehicle_id, platform_type) is not None
    ensure_auto_schedule(vehicle_id, platform_type, now)
    counts['skipped_existing' if already_had_row else created_key] += 1


def backfill(now) -> dict:
    """Give every already-published Shopify listing and every live Autovit
    listing a 1h auto-update schedule, unless one already exists (any
    cadence, including an explicit 'manual'). Returns counts, e.g.
    {'shopify_created': n, 'autovit_created': m, 'skipped_existing': k}."""
    counts = {'shopify_created': 0, 'autovit_created': 0, 'skipped_existing': 0}

    for vehicle_id in _pub_repo.list_published_vehicle_ids('shopify'):
        _ensure_and_count(vehicle_id, 'shopify', now, counts, 'shopify_created')

    for vehicle_id in _autovit_repo.list_live_vehicle_ids():
        _ensure_and_count(vehicle_id, 'autovit', now, counts, 'autovit_created')

    return counts


if __name__ == '__main__':
    now = datetime.now(timezone.utc)
    result = backfill(now)
    print(result)
