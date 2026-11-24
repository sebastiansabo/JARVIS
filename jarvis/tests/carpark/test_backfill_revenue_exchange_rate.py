"""Real-DB tests for the revenue exchange_rate_eur backfill. BNR is mocked.
Mirror of test_backfill_cost_exchange_rate.py.
"""
import pytest

from .conftest import REAL_DB_AVAILABLE
from database import get_db, get_cursor, release_db

BFR_COMPANY_ID = 990012


@pytest.fixture
def bfr_seed():
    if not REAL_DB_AVAILABLE:
        pytest.skip('Real Postgres not available — skipping revenue backfill DB test')
    conn = get_db(); conn.autocommit = False; cur = get_cursor(conn); ids = {}
    try:
        cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (BFR_COMPANY_ID,))
        cur.execute('''INSERT INTO carpark_vehicles (vin, brand, model, status, company_id)
                       VALUES ('TESTBFREV00001','B','M','READY_FOR_SALE',%s) RETURNING id''', (BFR_COMPANY_ID,))
        vid = cur.fetchone()['id']; ids['vehicle_id'] = vid
        cur.execute('''INSERT INTO carpark_vehicle_revenues (vehicle_id, revenue_type, amount, currency, date)
                       VALUES (%s,'sale',500,'RON','2025-11-17') RETURNING id''', (vid,))
        ids['ron_id'] = cur.fetchone()['id']
        cur.execute('''INSERT INTO carpark_vehicle_revenues (vehicle_id, revenue_type, amount, currency, date)
                       VALUES (%s,'commission',200,'EUR','2025-11-17') RETURNING id''', (vid,))
        ids['eur_id'] = cur.fetchone()['id']
        conn.commit(); yield ids
    finally:
        try:
            cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (BFR_COMPANY_ID,))
            conn.commit()
        finally:
            release_db(conn)


def _rate(cur, rid):
    cur.execute('SELECT exchange_rate_eur FROM carpark_vehicle_revenues WHERE id = %s', (rid,))
    return cur.fetchone()['exchange_rate_eur']


def test_backfill_sets_rate_for_ron_and_skips_eur(bfr_seed, monkeypatch):
    import scripts.backfill_revenue_exchange_rate as bf
    monkeypatch.setattr(bf, 'get_exchange_rate', lambda cur, date: 5.0)
    result = bf.run(apply=True, company_id=BFR_COMPANY_ID)
    assert bfr_seed['ron_id'] in result['updated']
    assert bfr_seed['eur_id'] not in result['audited']
    conn = get_db(); cur = get_cursor(conn)
    try:
        assert float(_rate(cur, bfr_seed['ron_id'])) == 5.0
        assert _rate(cur, bfr_seed['eur_id']) is None
    finally:
        release_db(conn)


def test_backfill_is_idempotent(bfr_seed, monkeypatch):
    import scripts.backfill_revenue_exchange_rate as bf
    monkeypatch.setattr(bf, 'get_exchange_rate', lambda cur, date: 5.0)
    bf.run(apply=True, company_id=BFR_COMPANY_ID)
    second = bf.run(apply=True, company_id=BFR_COMPANY_ID)
    assert second['audited'] == [] and second['updated'] == []


def test_backfill_bnr_miss_goes_to_needs_review(bfr_seed, monkeypatch):
    import scripts.backfill_revenue_exchange_rate as bf
    monkeypatch.setattr(bf, 'get_exchange_rate', lambda cur, date: None)
    result = bf.run(apply=True, company_id=BFR_COMPANY_ID)
    assert bfr_seed['ron_id'] in result['needs_review']
    assert bfr_seed['ron_id'] not in result['updated']
    conn = get_db(); cur = get_cursor(conn)
    try:
        assert _rate(cur, bfr_seed['ron_id']) is None
    finally:
        release_db(conn)


def test_backfill_dry_run_writes_nothing(bfr_seed, monkeypatch):
    import scripts.backfill_revenue_exchange_rate as bf
    monkeypatch.setattr(bf, 'get_exchange_rate', lambda cur, date: 5.0)
    bf.run(apply=False, company_id=BFR_COMPANY_ID)
    conn = get_db(); cur = get_cursor(conn)
    try:
        assert _rate(cur, bfr_seed['ron_id']) is None
    finally:
        release_db(conn)
