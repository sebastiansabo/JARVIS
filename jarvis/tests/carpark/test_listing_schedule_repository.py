"""Real-DB integration tests for ListingScheduleRepository.

Runs against localhost/defaultdb via the probe in conftest.py (see its
module docstring). Uses a local `seeded_vehicle` fixture that mirrors the
`dispo_seed` fixture's probe/seed/teardown idiom, but seeds a single
minimal carpark_vehicles row under the shared TEST_COMPANY_ID sentinel —
teardown deletes it (and cascades to any carpark_listing_schedules rows
created mid-test, since that FK is ON DELETE CASCADE).

Invocation:
    venv/bin/python -m pytest jarvis/tests/carpark/test_listing_schedule_repository.py -v
"""
import os
from datetime import datetime, timezone, timedelta

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest

from database import get_db, get_cursor, release_db

from carpark.repositories.listing_schedule_repository import ListingScheduleRepository

from .conftest import REAL_DB_AVAILABLE, TEST_COMPANY_ID


@pytest.fixture
def seeded_vehicle():
    if not REAL_DB_AVAILABLE:
        pytest.skip(
            'Real Postgres not available (DATABASE_URL unreachable or psycopg2 '
            'mocked) — skipping carpark DB-backed test'
        )

    conn = get_db()
    conn.autocommit = False
    cur = get_cursor(conn)
    try:
        # Defensive: clean up any leftover rows from a previously crashed run.
        cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (TEST_COMPANY_ID,))

        cur.execute('''
            INSERT INTO carpark_vehicles (vin, brand, model, status, company_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', ('TESTSCHED0000001', 'TestBrand', 'TestModel', 'READY_FOR_SALE', TEST_COMPANY_ID))
        vehicle_id = cur.fetchone()['id']
        conn.commit()
        yield {'id': vehicle_id}
    finally:
        try:
            cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (TEST_COMPANY_ID,))
            conn.commit()
            cur.execute('SELECT COUNT(*) AS cnt FROM carpark_vehicles WHERE company_id = %s',
                        (TEST_COMPANY_ID,))
            remaining = cur.fetchone()['cnt']
        finally:
            release_db(conn)
        assert remaining == 0, (
            f'teardown left {remaining} orphan carpark_vehicles row(s) for '
            f'company_id={TEST_COMPANY_ID}'
        )


def test_upsert_then_get(seeded_vehicle):
    repo = ListingScheduleRepository()
    vid = seeded_vehicle['id']
    repo.upsert(vid, 'shopify', 'daily', True, None)
    row = repo.get(vid, 'shopify')
    assert row['cadence'] == 'daily' and row['enabled'] is True


def test_upsert_is_idempotent_on_vehicle_platform(seeded_vehicle):
    repo = ListingScheduleRepository()
    vid = seeded_vehicle['id']
    repo.upsert(vid, 'shopify', 'daily', True, None)
    repo.upsert(vid, 'shopify', '2h', False, None)
    row = repo.get(vid, 'shopify')
    assert row['cadence'] == '2h' and row['enabled'] is False


def test_list_due_selects_only_due_interval_rows(seeded_vehicle):
    repo = ListingScheduleRepository(); vid = seeded_vehicle['id']
    now = datetime.now(timezone.utc)
    repo.upsert(vid, 'shopify', 'daily', True, now - timedelta(minutes=1))   # due
    due = repo.list_due('shopify', now)
    assert any(r['vehicle_id'] == vid for r in due)


def test_list_due_excludes_manual_instant_and_future(seeded_vehicle):
    repo = ListingScheduleRepository(); vid = seeded_vehicle['id']
    now = datetime.now(timezone.utc)
    repo.upsert(vid, 'shopify', 'manual', True, None)
    assert all(r['vehicle_id'] != vid for r in repo.list_due('shopify', now))
    repo.upsert(vid, 'shopify', 'instant', True, None)
    assert all(r['vehicle_id'] != vid for r in repo.list_due('shopify', now))
    repo.upsert(vid, 'shopify', 'daily', True, now + timedelta(hours=1))     # future
    assert all(r['vehicle_id'] != vid for r in repo.list_due('shopify', now))


def test_mark_run_sets_next_and_result(seeded_vehicle):
    repo = ListingScheduleRepository(); vid = seeded_vehicle['id']
    now = datetime.now(timezone.utc)
    row = repo.upsert(vid, 'shopify', 'daily', True, None)
    nxt = now + timedelta(minutes=1440)
    updated = repo.mark_run(row['id'], nxt, 'pushed')
    assert updated['last_result'] == 'pushed' and updated['last_run_at'] is not None
