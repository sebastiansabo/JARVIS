"""Real-DB tests for TdSlotService (slot materialization + 3-way availability).

Runs against the real localhost DB (DATABASE_URL, default postgresql://localhost/defaultdb),
via the require_real_db fixture in conftest.py (skips cleanly when no real DB is available).

company_id is NOT hardcoded (companies id=1 does not exist in defaultdb): the `page`
fixture resolves a real seed company id once via a direct SELECT, mirroring
test_td_booking_repository.py / test_td_bookings_repository.py / test_td_slots_repository.py.
created_by/default_advisor_user_id use users id=1, which does exist in the seed DB.

The window date is 2099-10-01, far in the future, so materialized slots never collide
with real Foaie de Parcurs data for the (non-existent) test VIN. min_lead_minutes=0 on
the page keeps available_slots' lead-time filter out of the way. test_available_filters_by_3way
monkeypatches svc.is_car_free directly (per the task brief) so availability is deterministic
and doesn't depend on real FP/vehicle-lock data for the test VIN.

mkt_td_bookings has plain (non-CASCADE) FKs to mkt_td_booking_pages/mkt_td_slots/
mkt_td_booking_cars, so any booking row a test creates must be deleted before the `page`
fixture's page teardown runs. These tests don't create bookings, but the teardown still
clears them defensively for symmetry with the sibling test files.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from database import get_db, get_cursor, release_db  # noqa: E402
from marketing.repositories.td_booking_repository import TdBookingRepository  # noqa: E402
from marketing.services.td_slot_service import TdSlotService  # noqa: E402

repo = TdBookingRepository()


@pytest.fixture
def page(require_real_db):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute('SELECT id FROM companies WHERE is_active ORDER BY id LIMIT 1')
        row = cur.fetchone()
    finally:
        release_db(conn)
    assert row is not None, 'no active company found in seed DB'
    company_id = row['id']

    p = repo.create_page({'company_id': company_id, 'slug': 'mat-test-1', 'created_by': 1,
                          'slot_minutes': 30, 'min_lead_minutes': 0})
    repo.add_car(p['id'], vin='MAT00001', default_advisor_user_id=1)
    repo.add_window(p['id'], '2099-10-01', '10:00', '11:00')  # far future
    yield p
    # mkt_td_bookings has NO ON DELETE CASCADE from page/slot/car -> delete any
    # bookings created by the test before the page (and its slots/cars, which DO
    # cascade) is torn down, or this DELETE hits an FK violation.
    repo.execute('DELETE FROM mkt_td_bookings WHERE page_id=%s', (p['id'],))
    repo.execute('DELETE FROM mkt_td_booking_pages WHERE id=%s', (p['id'],))


def test_materialize_generates_two_slots(page):
    svc = TdSlotService()
    assert svc.materialize_slots(page['id']) == 2      # 10:00, 10:30
    assert svc.materialize_slots(page['id']) == 0      # idempotent


def test_available_filters_by_3way(page, monkeypatch):
    svc = TdSlotService()
    svc.materialize_slots(page['id'])
    # car busy -> no availability
    monkeypatch.setattr(svc, 'is_car_free', lambda vin, frm, to: False)
    assert svc.available_slots(page['id'], datetime(2099, 1, 1, tzinfo=timezone.utc)) == []
    # car free -> both slots
    monkeypatch.setattr(svc, 'is_car_free', lambda vin, frm, to: True)
    assert len(svc.available_slots(page['id'], datetime(2099, 1, 1, tzinfo=timezone.utc))) == 2


def test_available_respects_lead_time(page):
    svc = TdSlotService()
    svc.materialize_slots(page['id'])
    svc.is_car_free = lambda vin, frm, to: True
    # now is after both slots -> nothing available regardless of car-free status
    far_after = datetime(2099, 10, 2, tzinfo=timezone.utc)
    assert svc.available_slots(page['id'], far_after) == []


def test_is_car_free_none_safe_when_vehicle_has_no_lock_row(page):
    # MAT00001 doesn't exist in fp_vehicles / foi_de_parcurs, so all three checks
    # (find_conflicts, get_lock_by_vin, get_open_session) hit real (empty) data --
    # this exercises the None-guard on get_lock_by_vin against the real DB.
    svc = TdSlotService()
    assert svc.is_car_free('MAT00001', datetime(2099, 10, 1, 10, 0, tzinfo=timezone.utc),
                            datetime(2099, 10, 1, 10, 30, tzinfo=timezone.utc)) is True
