"""Real-DB tests: non-EUR costs are converted to EUR via the shared rule
(money.COST_EUR_SQL) at every cost-sum reader, using each cost's stored
exchange_rate_eur (units of the cost currency per 1 EUR). RON stays the stored
source of truth; EUR is derived. A non-EUR cost with no rate falls back to its
raw amount (today's behavior, never worse).

Rates are seeded directly here so the READ side is tested independently of the
write-path/backfill that populate exchange_rate_eur (Tasks 2/3).
"""
import pytest

from carpark.services.vehicle_service import VehicleService
from carpark.services.pricing_service import PricingService
from carpark.repositories.dispo_repository import DispoRepository
from carpark.repositories.analytics_repository import AnalyticsRepository

from .conftest import REAL_DB_AVAILABLE
from database import get_db, get_cursor, release_db

FX_COMPANY_ID = 990009


@pytest.fixture
def fx_seed():
    """One SOLD vehicle (net buy 40000 EUR, sale 55000) with two costs:
      A = RON: amount 5000, vat 950, exchange_rate_eur 5.0  → 1000 EUR net, 190 EUR vat
      B = EUR: amount 200,  vat 0                           → 200 EUR net
    Converted totals: net 1200, vat 190, with_vat 1390 (raw would be 5200 / 6150)."""
    if not REAL_DB_AVAILABLE:
        pytest.skip('Real Postgres not available — skipping cost-FX DB test')
    conn = get_db(); conn.autocommit = False; cur = get_cursor(conn); ids = {}
    try:
        cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (FX_COMPANY_ID,))
        cur.execute('''
            INSERT INTO carpark_vehicles
                (vin, brand, model, category, status, company_id, acquisition_date,
                 acquisition_price, purchase_vat_rate, purchase_price_net, sale_price, sale_date)
            VALUES (%s,%s,%s,'SH','SOLD',%s, CURRENT_DATE, 50000, 25, 40000, 55000, CURRENT_DATE)
            RETURNING id
        ''', ('TESTFX00000000001', 'TestBrand', 'TestModel', FX_COMPANY_ID))
        vid = cur.fetchone()['id']; ids['vehicle_id'] = vid
        cur.execute('''INSERT INTO carpark_vehicle_costs
                       (vehicle_id, cost_type, amount, vat_amount, currency, exchange_rate_eur)
                       VALUES (%s,'repair',5000,950,'RON',5.0)''', (vid,))
        cur.execute('''INSERT INTO carpark_vehicle_costs
                       (vehicle_id, cost_type, amount, vat_amount, currency)
                       VALUES (%s,'other',200,0,'EUR')''', (vid,))
        conn.commit(); yield ids
    finally:
        try:
            cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (FX_COMPANY_ID,))
            conn.commit()
        finally:
            release_db(conn)


def test_get_profitability_converts_ron_costs(fx_seed):
    p = VehicleService().get_profitability(fx_seed['vehicle_id'])
    assert float(p['total_costs']) == 1200.0           # 1000 (RON/5) + 200 (EUR), not raw 5200


def test_floor_price_converts_cost_with_vat(fx_seed):
    f = PricingService().calculate_floor_price(fx_seed['vehicle_id'])
    # total_cost = gross acquisition 50000 + converted with_vat (1000+190 + 200) = 51390, not 56150
    assert float(f['components']['total_cost']) == 51390.0


def test_dispo_gross_margin_converts_costs(fx_seed):
    rows = DispoRepository().summary(FX_COMPANY_ID, {})['rows']
    row = next(r for r in rows if r['id'] == fx_seed['vehicle_id'])
    assert float(row['total_costs']) == 1200.0
    assert float(row['gross_margin']) == 55000 - 40000 - 1200  # 13800


def test_analytics_overview_converts_costs(fx_seed):
    ov = AnalyticsRepository().get_profitability_overview(FX_COMPANY_ID, period_days=3650)
    assert float(ov['total_costs']) == 1200.0


def test_get_costs_serializes_eur_equivalents(fx_seed):
    costs = VehicleService().get_costs(fx_seed['vehicle_id'])
    by_cur = {c['currency']: c for c in costs}
    assert float(by_cur['RON']['amount_eur']) == 1000.0      # 5000 / 5.0
    assert float(by_cur['RON']['vat_amount_eur']) == 190.0   # 950 / 5.0
    assert float(by_cur['EUR']['amount_eur']) == 200.0       # EUR unchanged


def _mock_rate(value):
    import carpark.services.vehicle_service as vs
    return lambda currency, date: value


def test_create_cost_captures_bnr_rate_for_ron(invoice_transfer_seed, monkeypatch):
    import carpark.services.vehicle_service as vs
    monkeypatch.setattr(vs, 'get_exchange_rate', _mock_rate(5.0))
    cost = VehicleService().create_cost(invoice_transfer_seed['vehicle_id'],
        {'cost_type': 'repair', 'amount': 500, 'currency': 'RON', 'date': '2025-11-17'})
    assert float(cost['exchange_rate_eur']) == 5.0


def test_create_cost_eur_gets_no_rate(invoice_transfer_seed, monkeypatch):
    import carpark.services.vehicle_service as vs
    monkeypatch.setattr(vs, 'get_exchange_rate', _mock_rate(5.0))
    cost = VehicleService().create_cost(invoice_transfer_seed['vehicle_id'],
        {'cost_type': 'repair', 'amount': 500, 'currency': 'EUR', 'date': '2025-11-17'})
    assert cost.get('exchange_rate_eur') is None


def test_transfer_captures_bnr_rate(invoice_transfer_seed, monkeypatch):
    import carpark.services.vehicle_service as vs
    monkeypatch.setattr(vs, 'get_exchange_rate', _mock_rate(5.0))
    cost = VehicleService().transfer_document_to_cost(
        invoice_transfer_seed['vehicle_id'], invoice_transfer_seed['doc_id'],
        {'cost_type': 'other', 'amount': 500, 'currency': 'RON', 'date': '2025-11-17'})
    assert float(cost['exchange_rate_eur']) == 5.0


def test_bnr_miss_does_not_break_create(invoice_transfer_seed, monkeypatch):
    import carpark.services.vehicle_service as vs
    monkeypatch.setattr(vs, 'get_exchange_rate', _mock_rate(None))  # BNR has no rate
    cost = VehicleService().create_cost(invoice_transfer_seed['vehicle_id'],
        {'cost_type': 'repair', 'amount': 500, 'currency': 'RON', 'date': '2025-11-17'})
    assert cost.get('exchange_rate_eur') is None  # saved without a rate, no crash


def test_update_cost_rederives_rate_on_date_change(invoice_transfer_seed, monkeypatch):
    import carpark.services.vehicle_service as vs
    monkeypatch.setattr(vs, 'get_exchange_rate', _mock_rate(5.0))
    cost = VehicleService().create_cost(invoice_transfer_seed['vehicle_id'],
        {'cost_type': 'repair', 'amount': 500, 'currency': 'RON', 'date': '2025-11-17'})
    monkeypatch.setattr(vs, 'get_exchange_rate', _mock_rate(4.9))  # different day → different rate
    VehicleService().update_cost(cost['id'], {'date': '2025-10-01'})
    updated = VehicleService().get_cost(cost['id'])
    assert float(updated['exchange_rate_eur']) == 4.9


def test_update_cost_bnr_miss_keeps_existing_rate(invoice_transfer_seed, monkeypatch):
    """A date edit that BNR can't resolve must NOT clear an already-valid rate
    (that would silently revert the cost to the raw ~5x overstatement)."""
    import carpark.services.vehicle_service as vs
    monkeypatch.setattr(vs, 'get_exchange_rate', _mock_rate(5.0))
    cost = VehicleService().create_cost(invoice_transfer_seed['vehicle_id'],
        {'cost_type': 'repair', 'amount': 500, 'currency': 'RON', 'date': '2025-11-17'})
    monkeypatch.setattr(vs, 'get_exchange_rate', _mock_rate(None))  # miss on the new date
    VehicleService().update_cost(cost['id'], {'date': '2020-01-01'})
    updated = VehicleService().get_cost(cost['id'])
    assert float(updated['exchange_rate_eur']) == 5.0  # kept, not cleared


def test_cost_overview_converts_costs_in_aliased_join():
    """get_cost_overview joins carpark_vehicles v — verify the bare-column
    COST_EUR_SQL resolves and converts there too (the highest bare-column risk)."""
    if not REAL_DB_AVAILABLE:
        pytest.skip('Real Postgres not available')
    conn = get_db(); conn.autocommit = False; cur = get_cursor(conn)
    try:
        cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (FX_COMPANY_ID,))
        cur.execute('''INSERT INTO carpark_vehicles (vin, brand, model, status, company_id)
                       VALUES ('TESTFXOVERVIEW01','B','M','READY_FOR_SALE',%s) RETURNING id''', (FX_COMPANY_ID,))
        vid = cur.fetchone()['id']
        cur.execute('''INSERT INTO carpark_vehicle_costs (vehicle_id, cost_type, amount, currency, exchange_rate_eur)
                       VALUES (%s,'repair',5000,'RON',5.0)''', (vid,))
        conn.commit()
        rows = AnalyticsRepository().get_cost_overview(FX_COMPANY_ID)
        repair = next((r for r in rows if r['cost_type'] == 'repair'), None)
        assert repair is not None and float(repair['total_amount']) == 1000.0  # 5000/5.0, not raw
    finally:
        cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (FX_COMPANY_ID,))
        conn.commit(); release_db(conn)


def test_non_eur_cost_without_rate_falls_back_to_raw():
    """A RON cost with no exchange_rate_eur contributes its raw amount (unchanged)."""
    if not REAL_DB_AVAILABLE:
        pytest.skip('Real Postgres not available')
    conn = get_db(); conn.autocommit = False; cur = get_cursor(conn)
    try:
        cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (FX_COMPANY_ID,))
        cur.execute('''INSERT INTO carpark_vehicles (vin, brand, model, status, company_id)
                       VALUES ('TESTFXNORATE00001','B','M','READY_FOR_SALE',%s) RETURNING id''', (FX_COMPANY_ID,))
        vid = cur.fetchone()['id']
        cur.execute('''INSERT INTO carpark_vehicle_costs (vehicle_id, cost_type, amount, currency)
                       VALUES (%s,'repair',300,'RON')''', (vid,))  # no exchange_rate_eur
        conn.commit()
        p = VehicleService().get_profitability(vid)
        assert float(p['total_costs']) == 300.0  # raw fallback, not 0, not a crash
    finally:
        cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (FX_COMPANY_ID,))
        conn.commit(); release_db(conn)
