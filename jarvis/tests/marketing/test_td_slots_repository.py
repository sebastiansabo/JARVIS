"""Real-DB tests for TdBookingRepository slots (idempotent bulk insert + open-slot query).

Runs against the real localhost DB (DATABASE_URL, default postgresql://localhost/defaultdb),
via the require_real_db fixture in conftest.py (skips cleanly when no real DB is available).

company_id is NOT hardcoded (companies id=1 does not exist in defaultdb): the `car`
fixture resolves a real seed company id once via a direct SELECT, mirroring
test_td_booking_repository.py. created_by/default_advisor_user_id use users id=1,
which does exist in the seed DB.

Note: mkt_td_bookings has plain (non-CASCADE) FKs to mkt_td_booking_pages/mkt_td_slots/
mkt_td_booking_cars, so any booking row inserted directly in a test must be deleted
before the `car` fixture's page teardown runs, or that DELETE raises a FK violation.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest  # noqa: E402
from database import get_db, get_cursor, release_db  # noqa: E402
from marketing.repositories.td_booking_repository import TdBookingRepository  # noqa: E402

repo = TdBookingRepository()


@pytest.fixture
def car(require_real_db):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute('SELECT id FROM companies WHERE is_active ORDER BY id LIMIT 1')
        row = cur.fetchone()
    finally:
        release_db(conn)
    assert row is not None, 'no active company found in seed DB'
    company_id = row['id']

    p = repo.create_page({'company_id': company_id, 'slug': 'slot-test-1', 'created_by': 1})
    c = repo.add_car(p['id'], vin='SLOT0001', default_advisor_user_id=1)
    yield p, c
    # FK cascades (page_id ON DELETE CASCADE on cars/windows/slots) clean up any cars/
    # windows/slots created in tests. mkt_td_bookings has NO cascade, so tests that
    # insert a booking must delete it themselves before this teardown runs.
    repo.execute('DELETE FROM mkt_td_booking_pages WHERE id=%s', (p['id'],))


def test_bulk_insert_idempotent(car):
    p, c = car
    rows = [{'page_id': p['id'], 'car_id': c['id'], 'vin': 'SLOT0001',
             'starts_at': '2026-10-01 10:00+03', 'ends_at': '2026-10-01 10:30+03'}]
    assert repo.bulk_insert_slots(rows) == 1
    assert repo.bulk_insert_slots(rows) == 0   # conflict -> skipped
    assert len(repo.list_open_slots(p['id'])) == 1


def test_bulk_insert_empty_rows_is_noop(car):
    assert repo.bulk_insert_slots([]) == 0


def test_list_open_slots_excludes_active_booking(car):
    p, c = car
    rows = [
        {'page_id': p['id'], 'car_id': c['id'], 'vin': 'SLOT0001',
         'starts_at': '2026-10-02 09:00+03', 'ends_at': '2026-10-02 09:30+03'},
        {'page_id': p['id'], 'car_id': c['id'], 'vin': 'SLOT0001',
         'starts_at': '2026-10-02 10:00+03', 'ends_at': '2026-10-02 10:30+03'},
    ]
    assert repo.bulk_insert_slots(rows) == 2
    slots = repo.list_open_slots(p['id'])
    assert len(slots) == 2
    booked_slot_id = slots[0]['id']

    repo.execute(
        "INSERT INTO mkt_td_bookings (page_id, slot_id, car_id, customer_name, "
        "customer_phone_e164, customer_email, status, expires_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,'pending_confirm', NOW() + interval '1 day')",
        (p['id'], booked_slot_id, c['id'], 'Jane Doe', '+40712345678', 'jane@example.com'))
    try:
        open_after = repo.list_open_slots(p['id'])
        assert len(open_after) == 1
        assert open_after[0]['id'] != booked_slot_id
    finally:
        repo.execute('DELETE FROM mkt_td_bookings WHERE page_id=%s', (p['id'],))
