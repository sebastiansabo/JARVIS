"""Real-DB tests for FoiParcursRepository.find_event_reservation.

A car assigned to an active Event TD page is reserved for that event's window
dates: a CLASSIC driving-session (TD / internal) whose interval overlaps one of
the car's event availability windows must be blocked, because the car is
committed to the event for that time. Outside the windows the car is free.

Real localhost DB via require_real_db (skips cleanly without one). Windows are
local wall-clock (Europe/Bucharest); December has no DST so 10:00 local == +02.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest  # noqa: E402
from database import get_db, get_cursor, release_db  # noqa: E402
from marketing.repositories.td_booking_repository import TdBookingRepository  # noqa: E402
from foi_parcurs.repositories.foi_parcurs_repository import FoiParcursRepository  # noqa: E402

td = TdBookingRepository()
fp = FoiParcursRepository()

_VIN = 'CFAEVT001'
_SLUG = 'cfa-evt-1'
# A window on 2099-12-01, 10:00-13:00 Europe/Bucharest.
_INSIDE = ('2099-12-01 11:00+02', '2099-12-01 11:30+02')   # inside 10:00-13:00
_OUTSIDE = ('2099-12-01 14:00+02', '2099-12-01 14:30+02')  # after the window


def _resolve_company_id():
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute('SELECT id FROM companies WHERE is_active ORDER BY id LIMIT 1')
        row = cur.fetchone()
    finally:
        release_db(conn)
    assert row is not None, 'no active company found in seed DB'
    return row['id']


def _clean():
    for pg in td.query_all('SELECT id FROM mkt_td_booking_pages WHERE slug=%s', (_SLUG,)):
        td.execute('DELETE FROM mkt_td_bookings WHERE page_id=%s', (pg['id'],))
        td.execute('DELETE FROM mkt_td_booking_pages WHERE id=%s', (pg['id'],))


@pytest.fixture
def event(require_real_db):
    _clean()
    company_id = _resolve_company_id()
    p = td.create_page({'company_id': company_id, 'slug': _SLUG, 'status': 'open', 'created_by': 1})
    c = td.add_car(p['id'], vin=_VIN, default_advisor_user_id=1)
    td.execute(
        "INSERT INTO mkt_td_booking_windows (page_id, window_date, start_time, end_time, slot_minutes) "
        "VALUES (%s, %s, %s, %s, %s)", (p['id'], '2099-12-01', '10:00', '13:00', 30))
    yield p, c
    _clean()


def test_reserved_during_event_window(event):
    rows = fp.find_event_reservation(_VIN, *_INSIDE)
    assert rows and rows[0]['slug'] == _SLUG


def test_free_outside_event_window(event):
    assert fp.find_event_reservation(_VIN, *_OUTSIDE) == []


def test_only_matches_same_vin(event):
    assert fp.find_event_reservation('OTHERVIN0', *_INSIDE) == []


def test_closed_event_does_not_reserve(event):
    p, _c = event
    td.set_page_status(p['id'], 'closed')
    assert fp.find_event_reservation(_VIN, *_INSIDE) == []


def test_inactive_car_does_not_reserve(event):
    p, c = event
    td.execute("UPDATE mkt_td_booking_cars SET is_active=FALSE WHERE id=%s", (c['id'],))
    assert fp.find_event_reservation(_VIN, *_INSIDE) == []


def test_draft_event_reserves(event):
    """A car on a DRAFT event (being prepared) already reserves its windows."""
    p, _c = event
    td.set_page_status(p['id'], 'draft')
    rows = fp.find_event_reservation(_VIN, *_INSIDE)
    assert rows and rows[0]['slug'] == _SLUG


def test_calendar_events_return_naive_local_window_bounds(event):
    """The calendar overlay must get NAIVE local wall-clock bounds (no tz shift):
    a 10:00-13:00 window stays 10:00-13:00, so the calendar's naiveDate renders
    the band at the right hour."""
    p, _c = event
    rows = td.list_events_for_calendar(p['company_id'], '2099-12-01', '2099-12-01')
    mine = [r for r in rows if r['slug'] == _SLUG]
    assert len(mine) == 1
    r = mine[0]
    assert r['vin'] == _VIN
    assert 'T10:00' in str(r['starts_at']) and 'T13:00' in str(r['ends_at'])

