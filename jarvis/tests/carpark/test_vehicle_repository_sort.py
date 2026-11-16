"""Real-DB regression test for catalog sorting by the computed "Days" column.

Guards against a HTTP 500 on `GET /api/carpark/vehicles?sort=stationary_days`.
`stationary_days` is a computed SELECT alias, NOT a real column, yet it was on
the sort whitelist while the query emitted `ORDER BY v.stationary_days` — which
Postgres rejects with `UndefinedColumn: column v.stationary_days does not
exist`. That ProgrammingError is neither ValueError nor TypeError, so the route
fell through to its blanket `except Exception` and returned 500 "Internal
error" (telemetry: 10 hits / 2 users who clicked the "Days" header).

Runs against localhost/defaultdb via the probe in conftest.py; skips when no
real DB is available (e.g. CI without Postgres).

Invocation:
    DATABASE_URL=postgresql://localhost/defaultdb \
        venv/bin/python -m pytest jarvis/tests/carpark/test_vehicle_repository_sort.py -v
"""
from datetime import date, timedelta

import pytest

from carpark.repositories.vehicle_repository import VehicleRepository

from .conftest import REAL_DB_AVAILABLE, TEST_COMPANY_ID

_OLD_VIN = 'TESTSORT00000001'  # arrived 200 days ago -> large stationary_days
_NEW_VIN = 'TESTSORT00000002'  # arrived 5 days ago   -> small stationary_days


@pytest.fixture
def sort_seed():
    """Seed two vehicles under TEST_COMPANY_ID with different arrival dates so
    sort order by stationary_days is observable. Cleans up before and after."""
    if not REAL_DB_AVAILABLE:
        pytest.skip('requires localhost/defaultdb')
    from database import get_db, get_cursor, release_db
    conn = get_db()
    conn.autocommit = False
    cur = get_cursor(conn)
    today = date.today()
    try:
        cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (TEST_COMPANY_ID,))
        cur.execute(
            '''INSERT INTO carpark_vehicles
                   (vin, brand, model, status, company_id, acquisition_date, arrival_date)
               VALUES (%s, %s, %s, %s, %s, %s, %s)''',
            (_OLD_VIN, 'TestBrand', 'OldModel', 'READY_FOR_SALE', TEST_COMPANY_ID,
             today - timedelta(days=200), today - timedelta(days=200)))
        cur.execute(
            '''INSERT INTO carpark_vehicles
                   (vin, brand, model, status, company_id, acquisition_date, arrival_date)
               VALUES (%s, %s, %s, %s, %s, %s, %s)''',
            (_NEW_VIN, 'TestBrand', 'NewModel', 'READY_FOR_SALE', TEST_COMPANY_ID,
             today - timedelta(days=5), today - timedelta(days=5)))
        conn.commit()
        yield
    finally:
        try:
            cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (TEST_COMPANY_ID,))
            conn.commit()
        finally:
            release_db(conn)


def test_get_catalog_sort_by_stationary_days(sort_seed):
    """Sorting by the computed "Days" column must return rows (not crash), and
    DESC must put the longest-stationary vehicle first."""
    result = VehicleRepository().get_catalog(
        filters={'company_id': TEST_COMPANY_ID},
        sort_by='stationary_days',
        sort_dir='DESC',
    )
    order = [item['vin'] for item in result['items']]
    assert _OLD_VIN in order and _NEW_VIN in order
    assert order.index(_OLD_VIN) < order.index(_NEW_VIN)
