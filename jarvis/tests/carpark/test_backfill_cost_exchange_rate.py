"""Real-DB tests for the exchange_rate_eur backfill: stamp the BNR rate on
existing non-EUR costs that have none. BNR is mocked (never hit the network).
"""
import pytest

from .conftest import REAL_DB_AVAILABLE
from database import get_db, get_cursor, release_db

BF_COMPANY_ID = 990010  # sentinel; see test_backfill_acq_currency.py registry


@pytest.fixture
def bf_seed():
    if not REAL_DB_AVAILABLE:
        pytest.skip('Real Postgres not available — skipping backfill DB test')
    conn = get_db(); conn.autocommit = False; cur = get_cursor(conn); ids = {}
    try:
        cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (BF_COMPANY_ID,))
        cur.execute('''INSERT INTO carpark_vehicles (vin, brand, model, status, company_id)
                       VALUES ('TESTBFRATE000001','B','M','READY_FOR_SALE',%s) RETURNING id''', (BF_COMPANY_ID,))
        vid = cur.fetchone()['id']; ids['vehicle_id'] = vid
        cur.execute('''INSERT INTO carpark_vehicle_costs (vehicle_id, cost_type, amount, currency, date)
                       VALUES (%s,'repair',500,'RON','2025-11-17') RETURNING id''', (vid,))
        ids['ron_cost_id'] = cur.fetchone()['id']
        cur.execute('''INSERT INTO carpark_vehicle_costs (vehicle_id, cost_type, amount, currency, date)
                       VALUES (%s,'other',200,'EUR','2025-11-17') RETURNING id''', (vid,))
        ids['eur_cost_id'] = cur.fetchone()['id']
        conn.commit(); yield ids
    finally:
        try:
            cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (BF_COMPANY_ID,))
            conn.commit()
        finally:
            release_db(conn)


def _rate(cur, cost_id):
    cur.execute('SELECT exchange_rate_eur FROM carpark_vehicle_costs WHERE id = %s', (cost_id,))
    return cur.fetchone()['exchange_rate_eur']


def test_backfill_sets_rate_for_ron_and_skips_eur(bf_seed, monkeypatch):
    import scripts.backfill_cost_exchange_rate as bf
    monkeypatch.setattr(bf, 'get_exchange_rate', lambda cur, date: 5.0)
    result = bf.run(apply=True, company_id=BF_COMPANY_ID)
    assert bf_seed['ron_cost_id'] in result['updated']
    assert bf_seed['eur_cost_id'] not in result['audited']  # EUR never considered
    conn = get_db(); cur = get_cursor(conn)
    try:
        assert float(_rate(cur, bf_seed['ron_cost_id'])) == 5.0
        assert _rate(cur, bf_seed['eur_cost_id']) is None
    finally:
        release_db(conn)


def test_backfill_is_idempotent(bf_seed, monkeypatch):
    import scripts.backfill_cost_exchange_rate as bf
    monkeypatch.setattr(bf, 'get_exchange_rate', lambda cur, date: 5.0)
    bf.run(apply=True, company_id=BF_COMPANY_ID)
    second = bf.run(apply=True, company_id=BF_COMPANY_ID)  # already has a rate → no-op
    assert second['audited'] == []
    assert second['updated'] == []


def test_backfill_bnr_miss_goes_to_needs_review(bf_seed, monkeypatch):
    import scripts.backfill_cost_exchange_rate as bf
    monkeypatch.setattr(bf, 'get_exchange_rate', lambda cur, date: None)  # no rate
    result = bf.run(apply=True, company_id=BF_COMPANY_ID)
    assert bf_seed['ron_cost_id'] in result['needs_review']
    assert bf_seed['ron_cost_id'] not in result['updated']
    conn = get_db(); cur = get_cursor(conn)
    try:
        assert _rate(cur, bf_seed['ron_cost_id']) is None  # never guessed/written
    finally:
        release_db(conn)


def test_backfill_dry_run_writes_nothing(bf_seed, monkeypatch):
    import scripts.backfill_cost_exchange_rate as bf
    monkeypatch.setattr(bf, 'get_exchange_rate', lambda cur, date: 5.0)
    bf.run(apply=False, company_id=BF_COMPANY_ID)
    conn = get_db(); cur = get_cursor(conn)
    try:
        assert _rate(cur, bf_seed['ron_cost_id']) is None
    finally:
        release_db(conn)
