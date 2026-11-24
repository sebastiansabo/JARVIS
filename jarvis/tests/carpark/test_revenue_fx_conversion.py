"""Real-DB tests: non-EUR revenues convert to EUR via the shared rule
(money.REVENUE_EUR_SQL) at every revenue-sum reader, using each revenue's stored
exchange_rate_eur. RON stays the source of truth. Mirror of
test_cost_fx_conversion.py (costs). BNR is mocked by the carpark conftest.
"""
import pytest

from carpark.services.vehicle_service import VehicleService
from carpark.repositories.dispo_repository import DispoRepository

from .conftest import REAL_DB_AVAILABLE
from database import get_db, get_cursor, release_db

REVFX_COMPANY_ID = 990011


@pytest.fixture
def revfx_seed():
    """One SOLD vehicle with two revenues: RON (5000/950 @ 5.0 → 1000/190 EUR)
    and EUR (200). Converted total_revenues = 1200 (raw would be 5200)."""
    if not REAL_DB_AVAILABLE:
        pytest.skip('Real Postgres not available — skipping revenue-FX DB test')
    conn = get_db(); conn.autocommit = False; cur = get_cursor(conn); ids = {}
    try:
        cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (REVFX_COMPANY_ID,))
        cur.execute('''
            INSERT INTO carpark_vehicles
                (vin, brand, model, category, status, company_id, acquisition_date,
                 acquisition_price, purchase_vat_rate, purchase_price_net, sale_price, sale_date)
            VALUES (%s,%s,%s,'SH','SOLD',%s, CURRENT_DATE, 50000, 25, 40000, 55000, CURRENT_DATE)
            RETURNING id
        ''', ('TESTREVFX00000001', 'TestBrand', 'TestModel', REVFX_COMPANY_ID))
        vid = cur.fetchone()['id']; ids['vehicle_id'] = vid
        cur.execute('''INSERT INTO carpark_vehicle_revenues
                       (vehicle_id, revenue_type, amount, vat_amount, currency, exchange_rate_eur)
                       VALUES (%s,'sale',5000,950,'RON',5.0)''', (vid,))
        cur.execute('''INSERT INTO carpark_vehicle_revenues
                       (vehicle_id, revenue_type, amount, vat_amount, currency)
                       VALUES (%s,'commission',200,0,'EUR')''', (vid,))
        conn.commit(); yield ids
    finally:
        try:
            cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (REVFX_COMPANY_ID,))
            conn.commit()
        finally:
            release_db(conn)


def test_get_profitability_converts_ron_revenues(revfx_seed):
    p = VehicleService().get_profitability(revfx_seed['vehicle_id'])
    assert float(p['total_revenues']) == 1200.0   # 1000 (RON/5) + 200 (EUR), not raw 5200


def test_dispo_total_revenues_converts(revfx_seed):
    rows = DispoRepository().summary(REVFX_COMPANY_ID, {})['rows']
    row = next(r for r in rows if r['id'] == revfx_seed['vehicle_id'])
    assert float(row['total_revenues']) == 1200.0


def test_get_revenues_serializes_eur_equivalents(revfx_seed):
    revs = VehicleService().get_revenues(revfx_seed['vehicle_id'])
    by_cur = {r['currency']: r for r in revs}
    assert float(by_cur['RON']['amount_eur']) == 1000.0
    assert float(by_cur['RON']['vat_amount_eur']) == 190.0
    assert float(by_cur['EUR']['amount_eur']) == 200.0


def _mock_rate(value):
    return lambda currency, date: value


def test_create_revenue_captures_bnr_rate_for_ron(invoice_transfer_seed, monkeypatch):
    import carpark.services.vehicle_service as vs
    monkeypatch.setattr(vs, 'get_exchange_rate', _mock_rate(5.0))
    rev = VehicleService().create_revenue(invoice_transfer_seed['vehicle_id'],
        {'revenue_type': 'sale', 'amount': 500, 'currency': 'RON', 'date': '2025-11-17'})
    assert float(rev['exchange_rate_eur']) == 5.0


def test_create_revenue_eur_gets_no_rate(invoice_transfer_seed, monkeypatch):
    import carpark.services.vehicle_service as vs
    monkeypatch.setattr(vs, 'get_exchange_rate', _mock_rate(5.0))
    rev = VehicleService().create_revenue(invoice_transfer_seed['vehicle_id'],
        {'revenue_type': 'sale', 'amount': 500, 'currency': 'EUR', 'date': '2025-11-17'})
    assert rev.get('exchange_rate_eur') is None


def test_transfer_revenue_captures_bnr_rate(invoice_transfer_seed, monkeypatch):
    import carpark.services.vehicle_service as vs
    monkeypatch.setattr(vs, 'get_exchange_rate', _mock_rate(5.0))
    rev = VehicleService().transfer_document_to_revenue(
        invoice_transfer_seed['vehicle_id'], invoice_transfer_seed['doc_id'],
        {'revenue_type': 'sale', 'amount': 500, 'currency': 'RON', 'date': '2025-11-17'})
    assert float(rev['exchange_rate_eur']) == 5.0


def test_bnr_miss_does_not_break_revenue_create(invoice_transfer_seed, monkeypatch):
    import carpark.services.vehicle_service as vs
    monkeypatch.setattr(vs, 'get_exchange_rate', _mock_rate(None))
    rev = VehicleService().create_revenue(invoice_transfer_seed['vehicle_id'],
        {'revenue_type': 'sale', 'amount': 500, 'currency': 'RON', 'date': '2025-11-17'})
    assert rev.get('exchange_rate_eur') is None  # saved without a rate, no crash


def test_update_revenue_rederives_rate_on_date_change(invoice_transfer_seed, monkeypatch):
    import carpark.services.vehicle_service as vs
    monkeypatch.setattr(vs, 'get_exchange_rate', _mock_rate(5.0))
    rev = VehicleService().create_revenue(invoice_transfer_seed['vehicle_id'],
        {'revenue_type': 'sale', 'amount': 500, 'currency': 'RON', 'date': '2025-11-17'})
    monkeypatch.setattr(vs, 'get_exchange_rate', _mock_rate(4.9))
    VehicleService().update_revenue(rev['id'], {'date': '2025-10-01'})
    updated = VehicleService().get_revenue(rev['id'])
    assert float(updated['exchange_rate_eur']) == 4.9


def test_update_revenue_bnr_miss_keeps_existing_rate(invoice_transfer_seed, monkeypatch):
    import carpark.services.vehicle_service as vs
    monkeypatch.setattr(vs, 'get_exchange_rate', _mock_rate(5.0))
    rev = VehicleService().create_revenue(invoice_transfer_seed['vehicle_id'],
        {'revenue_type': 'sale', 'amount': 500, 'currency': 'RON', 'date': '2025-11-17'})
    monkeypatch.setattr(vs, 'get_exchange_rate', _mock_rate(None))  # miss on the new date
    VehicleService().update_revenue(rev['id'], {'date': '2020-01-01'})
    updated = VehicleService().get_revenue(rev['id'])
    assert float(updated['exchange_rate_eur']) == 5.0  # kept, not cleared


def test_non_eur_revenue_without_rate_falls_back_to_raw():
    if not REAL_DB_AVAILABLE:
        pytest.skip('Real Postgres not available')
    conn = get_db(); conn.autocommit = False; cur = get_cursor(conn)
    try:
        cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (REVFX_COMPANY_ID,))
        cur.execute('''INSERT INTO carpark_vehicles (vin, brand, model, status, company_id)
                       VALUES ('TESTREVFXNORATE1','B','M','READY_FOR_SALE',%s) RETURNING id''', (REVFX_COMPANY_ID,))
        vid = cur.fetchone()['id']
        cur.execute('''INSERT INTO carpark_vehicle_revenues (vehicle_id, revenue_type, amount, currency)
                       VALUES (%s,'sale',300,'RON')''', (vid,))
        conn.commit()
        p = VehicleService().get_profitability(vid)
        assert float(p['total_revenues']) == 300.0  # raw fallback, not 0/crash
    finally:
        cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (REVFX_COMPANY_ID,))
        conn.commit(); release_db(conn)
