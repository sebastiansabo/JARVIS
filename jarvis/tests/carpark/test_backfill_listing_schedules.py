"""Task 8: backfill a 1h auto-update schedule for cars that were already
published/live on Shopify or Autovit before Task 7 introduced
`ensure_auto_schedule()` (default-on-publish). Without this one-off backfill,
every car published before that change would simply never auto-update,
since a `carpark_listing_schedules` row today only appears via a fresh
publish or an explicit user choice.

Mock-based, no DB, no network — mirrors test_publishing_schedule_autocreate.py's
idiom of patching `cadence_mod._schedule_repo` directly (the exact singleton
`ensure_auto_schedule` itself calls), plus patching the new published/live
vehicle-id lookups added to PublishingRepository/AutovitListingRepository.

Invocation:
    DATABASE_URL=postgresql://localhost/defaultdb \
        venv/bin/python -m pytest jarvis/tests/carpark/test_backfill_listing_schedules.py -v
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from datetime import datetime, timezone
from unittest.mock import ANY, patch

import carpark.connectors.cadence as cadence_mod
import scripts.backfill_listing_schedules as backfill_mod

_NOW = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)


def test_backfill_creates_rows_for_published():
    """Two published Shopify vehicles, no existing schedule rows → both get
    a fresh 1h schedule, and the counts reflect exactly two creations."""
    with patch.object(backfill_mod._pub_repo, 'list_published_vehicle_ids',
                       return_value=[10, 20]), \
         patch.object(backfill_mod._autovit_repo, 'list_live_vehicle_ids',
                       return_value=[]), \
         patch.object(cadence_mod._schedule_repo, 'get', return_value=None), \
         patch.object(cadence_mod._schedule_repo, 'upsert') as upsert:
        counts = backfill_mod.backfill(_NOW)

        assert upsert.call_count == 2
        upsert.assert_any_call(10, 'shopify', '1h', True, ANY)
        upsert.assert_any_call(20, 'shopify', '1h', True, ANY)
        assert counts == {'shopify_created': 2, 'autovit_created': 0,
                           'skipped_existing': 0}


def test_backfill_skips_explicit_manual():
    """A vehicle whose schedule row already exists (even cadence='manual')
    must be left untouched — ensure_auto_schedule's existing-row short-
    circuit fires, so no upsert happens and it's tallied as skipped."""
    existing_manual_row = {'id': 1, 'vehicle_id': 5, 'platform_type': 'shopify',
                            'cadence': 'manual', 'enabled': True, 'next_run_at': None}
    with patch.object(backfill_mod._pub_repo, 'list_published_vehicle_ids',
                       return_value=[5]), \
         patch.object(backfill_mod._autovit_repo, 'list_live_vehicle_ids',
                       return_value=[]), \
         patch.object(cadence_mod._schedule_repo, 'get', return_value=existing_manual_row), \
         patch.object(cadence_mod._schedule_repo, 'upsert') as upsert:
        counts = backfill_mod.backfill(_NOW)

        upsert.assert_not_called()
        assert counts == {'shopify_created': 0, 'autovit_created': 0,
                           'skipped_existing': 1}


def test_backfill_covers_both_platforms():
    """Published Shopify vehicles and live Autovit vehicles are both
    processed in a single backfill() call, each tagged with its own
    platform_type and tallied under its own counter."""
    with patch.object(backfill_mod._pub_repo, 'list_published_vehicle_ids',
                       return_value=[1, 2]), \
         patch.object(backfill_mod._autovit_repo, 'list_live_vehicle_ids',
                       return_value=[3]), \
         patch.object(cadence_mod._schedule_repo, 'get', return_value=None), \
         patch.object(cadence_mod._schedule_repo, 'upsert') as upsert:
        counts = backfill_mod.backfill(_NOW)

        assert upsert.call_count == 3
        upsert.assert_any_call(1, 'shopify', '1h', True, ANY)
        upsert.assert_any_call(2, 'shopify', '1h', True, ANY)
        upsert.assert_any_call(3, 'autovit', '1h', True, ANY)
        assert counts == {'shopify_created': 2, 'autovit_created': 1,
                           'skipped_existing': 0}
        backfill_mod._pub_repo.list_published_vehicle_ids.assert_called_once_with('shopify')
