"""Real-DB test for the expire_stale_bookings scheduled task (Task 12).

Runs against the real localhost DB (DATABASE_URL, default postgresql://localhost/defaultdb),
via the require_real_db fixture in conftest.py (skips cleanly when no real DB is available).

company_id is NOT hardcoded (companies id=1 does not exist in defaultdb): resolved via a
direct SELECT, mirroring test_td_bookings_repository.py's `slot` fixture.

expire_pending_bookings (TdBookingService) uses no app context (no current_app), so no
Flask app is needed to exercise expire_stale_bookings() here.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest  # noqa: E402
from datetime import datetime, timezone, timedelta  # noqa: E402
from database import get_db, get_cursor, release_db  # noqa: E402
from tasks.td_bookings import expire_stale_bookings  # noqa: E402
from marketing.repositories.td_booking_repository import TdBookingRepository  # noqa: E402

repo = TdBookingRepository()


@pytest.fixture
def slot(require_real_db):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute('SELECT id FROM companies WHERE is_active ORDER BY id LIMIT 1')
        row = cur.fetchone()
    finally:
        release_db(conn)
    assert row is not None, 'no active company found in seed DB'
    company_id = row['id']

    p = repo.create_page({'company_id': company_id, 'slug': 'exp-task-1', 'created_by': 1})
    c = repo.add_car(p['id'], vin='EXPTASK01', default_advisor_user_id=1)
    repo.bulk_insert_slots([{'page_id': p['id'], 'car_id': c['id'], 'vin': 'EXPTASK01',
                             'starts_at': '2099-10-01 10:00+03', 'ends_at': '2099-10-01 10:30+03'}])
    s = repo.list_open_slots(p['id'])[0]
    yield p, c, s
    # mkt_td_bookings has NO ON DELETE CASCADE from page/slot/car -> delete any
    # bookings created by the test before the page (and its slots/cars, which DO
    # cascade) is torn down, or this DELETE hits an FK violation.
    repo.execute('DELETE FROM mkt_td_bookings WHERE page_id=%s', (p['id'],))
    repo.execute('DELETE FROM mkt_td_booking_pages WHERE id=%s', (p['id'],))


def test_expire_task_flips_stale(slot):
    p, c, s = slot
    b = repo.create_booking({
        'page_id': p['id'], 'slot_id': s['id'], 'car_id': c['id'],
        'customer_name': 'X', 'customer_phone_e164': '+40721000099',
        'customer_email': 'x@ex.com',
        'expires_at': datetime.now(timezone.utc) - timedelta(minutes=1),
    })
    assert expire_stale_bookings() >= 1
    assert repo.get_booking(b['id'])['status'] == 'expired'
