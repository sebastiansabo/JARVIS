"""Real-DB tests for FoiParcursRepository.find_sessions_overlapping_event.

When staff add a car to an Event TD page, we warn them if that car already has a
(non-terminal) driving session overlapping ANY of the event's availability
windows -- otherwise the car looks bookable in the admin but shows no slots on
the public form (is_car_free hides it). This is the inverse of
find_event_reservation.

Real localhost DB via require_real_db (skips cleanly without one). December has
no DST so 10:00 local == +02.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest  # noqa: E402
from database import get_db, get_cursor, release_db  # noqa: E402
from marketing.repositories.td_booking_repository import TdBookingRepository  # noqa: E402
from foi_parcurs.repositories.foi_parcurs_repository import FoiParcursRepository  # noqa: E402

td = TdBookingRepository()
fp = FoiParcursRepository()

_VIN = 'CFACARCONF1'
_SLUG = 'cfa-carconf-1'


def _resolve_company_id():
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute('SELECT id FROM companies WHERE is_active ORDER BY id LIMIT 1')
        row = cur.fetchone()
    finally:
        release_db(conn)
    assert row is not None
    return row['id']


def _fp_row(company_id, contract_id, status, dep, ret):
    return {
        'vin': _VIN, 'company_id': company_id, 'contract_id': contract_id,
        'route_type': 'TD', 'status': status, 'source': 'td_form',
        'client_name': 'Ion', 'client_phone': '+40721000009', 'advisor_name': 'Adv',
        'departure_datetime': dep, 'return_datetime': ret,
        'km_start': 0, 'km_end': 0, 'distance_km': 0, 'fuel_tank_capacity_liters': 0,
        'fuel_gauge_start_level': 'full', 'fuel_gauge_end_level': 'full',
        'fuel_start_liters': 0, 'fuel_end_liters': 0, 'fuel_consumed_liters': 0,
    }


def _insert_fp(row):
    cols = list(row.keys())
    ph = ', '.join(['%s'] * len(cols))
    fp.execute(f"INSERT INTO foi_de_parcurs ({', '.join(cols)}) VALUES ({ph})",
               tuple(row[c] for c in cols))


def _clean():
    fp.execute("DELETE FROM foi_de_parcurs WHERE vin=%s", (_VIN,))
    for pg in td.query_all("SELECT id FROM mkt_td_booking_pages WHERE slug=%s", (_SLUG,)):
        td.execute("DELETE FROM mkt_td_bookings WHERE page_id=%s", (pg['id'],))
        td.execute("DELETE FROM mkt_td_booking_pages WHERE id=%s", (pg['id'],))


@pytest.fixture
def event(require_real_db):
    _clean()
    company_id = _resolve_company_id()
    p = td.create_page({'company_id': company_id, 'slug': _SLUG, 'status': 'open', 'created_by': 1})
    td.execute("INSERT INTO mkt_td_booking_windows (page_id, window_date, start_time, end_time, slot_minutes) "
               "VALUES (%s,%s,%s,%s,%s)", (p['id'], '2099-12-01', '10:00', '13:00', 30))
    yield p, company_id
    _clean()


def test_overlapping_live_session_is_flagged(event):
    p, company_id = event
    _insert_fp(_fp_row(company_id, 'CARCONF-OVL', 'PLANNED',
                       '2099-12-01 11:00+02', '2099-12-01 12:00+02'))
    rows = fp.find_sessions_overlapping_event(_VIN, p['id'])
    assert rows and rows[0]['contract_id'] == 'CARCONF-OVL'


def test_multiday_session_covering_window_is_flagged(event):
    p, company_id = event
    _insert_fp(_fp_row(company_id, 'CARCONF-MULTI', 'PLANNED',
                       '2099-11-30 08:00+02', '2099-12-05 08:00+02'))
    assert len(fp.find_sessions_overlapping_event(_VIN, p['id'])) == 1


def test_nonoverlapping_session_ignored(event):
    p, company_id = event
    _insert_fp(_fp_row(company_id, 'CARCONF-OUT', 'PLANNED',
                       '2099-12-02 11:00+02', '2099-12-02 12:00+02'))
    assert fp.find_sessions_overlapping_event(_VIN, p['id']) == []


def test_terminal_session_ignored(event):
    p, company_id = event
    _insert_fp(_fp_row(company_id, 'CARCONF-DONE', 'COMPLETED',
                       '2099-12-01 11:00+02', '2099-12-01 12:00+02'))
    assert fp.find_sessions_overlapping_event(_VIN, p['id']) == []


def test_other_vin_ignored(event):
    p, company_id = event
    _insert_fp(_fp_row(company_id, 'CARCONF-OVL', 'PLANNED',
                       '2099-12-01 11:00+02', '2099-12-01 12:00+02'))
    assert fp.find_sessions_overlapping_event('SOMEOTHERVIN', p['id']) == []
