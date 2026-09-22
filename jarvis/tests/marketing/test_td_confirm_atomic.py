"""Real-DB tests for TdBookingRepository.confirm_booking_atomic — the race-safe
atomic confirm (advisory lock + in-txn 3-way availability recheck + PLANNED
foi_de_parcurs insert + booking flip), all in one execute_many transaction.

Runs against the real localhost DB (DATABASE_URL, default postgresql://localhost/defaultdb),
via the require_real_db fixture in conftest.py (skips cleanly when no real DB is available).
Imports the REAL psycopg2 (not the process-wide mock installed for the rest of the
suite) so the transaction / advisory lock / RETURNING behaviour is genuine.

company_id is NOT hardcoded (companies id=1 does not exist in defaultdb): the `booking`
fixture resolves a real seed company id once via a direct SELECT, mirroring
test_td_bookings_repository.py. created_by/default_advisor_user_id use users id=1,
which exists in the seed DB.

foi_de_parcurs has many NOT NULL columns without defaults (contract_id, km_start/end,
distance_km, fuel_*), so the fp_row inserted here fills all of them with valid throwaway
values. contract_id is UNIQUE, so the confirm row and the seeded conflict row use
distinct contract_ids.

A synthetic VIN ('CFACONF001') is used so the in-txn 3-way recheck sees no real
foi_de_parcurs sessions / fp_vehicles lock rows; the conflict test explicitly SEEDS a
live TD foi_de_parcurs row on that VIN/time and asserts TdConflict + booking untouched.

mkt_td_bookings has plain (non-CASCADE) FKs to pages/slots/cars, so bookings are deleted
before the page (whose slots/cars DO cascade) in teardown.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest  # noqa: E402
import psycopg2  # noqa: E402  (real driver, bound by conftest's require_real_db probe)
from datetime import datetime, timezone, timedelta  # noqa: E402
from database import get_db, get_cursor, release_db  # noqa: E402
from marketing.repositories.td_booking_repository import (  # noqa: E402
    TdBookingRepository, TdConflict,
)

repo = TdBookingRepository()

_VIN = 'CFACONF001'
_SLUG = 'cfa-confirm-1'
_FRM = '2099-10-01 10:00+03'
_TO = '2099-10-01 10:30+03'


def _fp_row(vin, company_id):
    """A foi_de_parcurs insert payload that satisfies every NOT NULL column
    (no server defaults on contract_id/km_*/distance_km/fuel_*)."""
    return {
        'vin': vin,
        'company_id': company_id,
        'contract_id': f'CFA-CONFIRM-{vin}',
        'route_type': 'TD',
        'status': 'PLANNED',
        'source': 'td_form',
        'client_name': 'Ion',
        'client_phone': '+40721000009',
        'advisor_name': 'Test Advisor',
        'departure_datetime': _FRM,
        'return_datetime': _TO,
        'km_start': 0,
        'km_end': 0,
        'distance_km': 0,
        'fuel_tank_capacity_liters': 0,
        'fuel_gauge_start_level': 'full',
        'fuel_gauge_end_level': 'full',
        'fuel_start_liters': 0,
        'fuel_end_liters': 0,
        'fuel_consumed_liters': 0,
    }


def _seed_conflict_fp(vin, company_id):
    """Insert a live PLANNED TD session on the same VIN/time (distinct contract_id)."""
    row = _fp_row(vin, company_id)
    row['contract_id'] = f'CFA-SEED-{vin}'
    cols = list(row.keys())
    ph = ', '.join(['%s'] * len(cols))
    repo.execute(f"INSERT INTO foi_de_parcurs ({', '.join(cols)}) VALUES ({ph})",
                 tuple(row[c] for c in cols))


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


@pytest.fixture
def booking(require_real_db):
    company_id = _resolve_company_id()

    # Defensive pre-clean: a prior aborted run could leave a foi_de_parcurs row on
    # this VIN (contract_id is UNIQUE -> would collide) or a page on this slug.
    repo.execute('DELETE FROM foi_de_parcurs WHERE vin=%s', (_VIN,))
    for pg in repo.query_all('SELECT id FROM mkt_td_booking_pages WHERE slug=%s', (_SLUG,)):
        repo.execute('DELETE FROM mkt_td_bookings WHERE page_id=%s', (pg['id'],))
        repo.execute('DELETE FROM mkt_td_booking_pages WHERE id=%s', (pg['id'],))

    p = repo.create_page({'company_id': company_id, 'slug': _SLUG, 'created_by': 1})
    c = repo.add_car(p['id'], vin=_VIN, default_advisor_user_id=1)
    repo.bulk_insert_slots([{'page_id': p['id'], 'car_id': c['id'], 'vin': _VIN,
                             'starts_at': _FRM, 'ends_at': _TO}])
    s = repo.list_open_slots(p['id'])[0]
    b = repo.create_booking({'page_id': p['id'], 'slot_id': s['id'], 'car_id': c['id'],
                             'customer_name': 'Ion', 'customer_phone_e164': '+40721000009',
                             'customer_email': 'ion@ex.com',
                             'expires_at': datetime.now(timezone.utc) + timedelta(hours=1)})
    yield p, c, s, b, company_id
    # bookings (plain FK) before page (slots/cars cascade); foi_de_parcurs has no FK
    # back to the mkt tables, so its cleanup order is independent.
    repo.execute('DELETE FROM foi_de_parcurs WHERE vin=%s', (_VIN,))
    repo.execute('DELETE FROM mkt_td_bookings WHERE page_id=%s', (p['id'],))
    repo.execute('DELETE FROM mkt_td_booking_pages WHERE id=%s', (p['id'],))


def test_confirm_creates_planned_fp(booking):
    p, c, s, b, company_id = booking
    res = repo.confirm_booking_atomic(b['id'], _VIN, _FRM, _TO, _fp_row(_VIN, company_id))
    fp = repo.query_one('SELECT * FROM foi_de_parcurs WHERE id=%s', (res['fp_id'],))
    assert fp['route_type'] == 'TD' and fp['status'] == 'PLANNED'
    assert repo.get_booking(b['id'])['status'] == 'confirmed'
    assert repo.get_booking(b['id'])['foi_de_parcurs_id'] == res['fp_id']


def test_confirm_conflicts_when_car_busy(booking):
    p, c, s, b, company_id = booking
    # Seed a conflicting live FP session on the same VIN/time.
    _seed_conflict_fp(_VIN, company_id)
    with pytest.raises(TdConflict):
        repo.confirm_booking_atomic(b['id'], _VIN, _FRM, _TO, _fp_row(_VIN, company_id))
    # booking untouched, and no confirm-row was left behind (transaction rolled back)
    assert repo.get_booking(b['id'])['status'] == 'pending_confirm'
    assert repo.query_one(
        "SELECT id FROM foi_de_parcurs WHERE contract_id=%s", (f'CFA-CONFIRM-{_VIN}',)) is None
