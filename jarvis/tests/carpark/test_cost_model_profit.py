"""Real-DB tests for the EUR net-basis profit model (analytics / dispo /
get_profitability). Runs against localhost/defaultdb via conftest's probe.

Seeds ONE sold vehicle under a dedicated sentinel company:
  gross acquisition 50000, VAT 25% → net buy 40000 (purchase_price_net),
  sale 55000, one cost (amount 2000 net / 2500 incl VAT), one revenue
  (amount 1000 net / 1190 incl VAT).

Net-basis expectations:
  analytics gross_profit   = 55000 - 40000 - 2000 = 13000  (was double-counted → -35000)
  get_profitability profit = 1000 - 40000 - 2000 = -41000  (net revenues - net buy - net costs)
(Dispo margin is intentionally left on gross basis for now — its grid shows an
editable GROSS acquisition column, so a net margin wouldn't tie out per row.)
"""
import pytest

from carpark.repositories.analytics_repository import AnalyticsRepository
from carpark.services.vehicle_service import VehicleService

from .conftest import REAL_DB_AVAILABLE
from database import get_db, get_cursor, release_db

PROFIT_COMPANY_ID = 990002


@pytest.fixture
def profit_seed():
    if not REAL_DB_AVAILABLE:
        pytest.skip('Real Postgres not available — skipping cost-model DB test')
    conn = get_db()
    conn.autocommit = False
    cur = get_cursor(conn)
    ids = {}
    try:
        cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (PROFIT_COMPANY_ID,))
        cur.execute('''
            INSERT INTO carpark_vehicles
                (vin, brand, model, category, status, company_id, acquisition_date,
                 acquisition_price, purchase_vat_rate, purchase_price_net,
                 sale_price, sale_date)
            VALUES (%s,%s,%s,%s,%s,%s, CURRENT_DATE,
                    50000, 25, 40000,
                    55000, CURRENT_DATE)
            RETURNING id
        ''', ('TESTPROFIT0000001', 'TestBrand', 'TestModel', 'SH', 'SOLD', PROFIT_COMPANY_ID))
        vid = cur.fetchone()['id']
        ids['vehicle_id'] = vid
        cur.execute('''INSERT INTO carpark_vehicle_costs (vehicle_id, cost_type, amount, vat_amount)
                       VALUES (%s, %s, %s, %s)''', (vid, 'istoric_import', 2000, 500))
        cur.execute('''INSERT INTO carpark_vehicle_revenues (vehicle_id, revenue_type, amount, vat_amount)
                       VALUES (%s, %s, %s, %s)''', (vid, 'bonus_leasing', 1000, 190))
        conn.commit()
        yield ids
    finally:
        try:
            cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (PROFIT_COMPANY_ID,))
            conn.commit()
        finally:
            release_db(conn)


def test_analytics_overview_counts_buy_price_once(profit_seed):
    ov = AnalyticsRepository().get_profitability_overview(PROFIT_COMPANY_ID, period_days=3650)
    assert float(ov['total_gross_profit']) == 13000.0
    assert float(ov['total_acquisition']) == 40000.0  # net buy, not gross 50000
    assert float(ov['total_costs']) == 2000.0          # extra costs from carpark_vehicle_costs


def test_monthly_sales_net_basis(profit_seed):
    rows = AnalyticsRepository().get_monthly_sales(PROFIT_COMPANY_ID, months=1)
    assert len(rows) == 1
    assert int(rows[0]['sold']) == 1
    assert float(rows[0]['revenue']) == 55000.0
    assert float(rows[0]['gross_profit']) == 13000.0


def test_get_profitability_net_basis(profit_seed):
    p = VehicleService().get_profitability(profit_seed['vehicle_id'])
    assert float(p['acquisition_price']) == 40000.0   # net buy
    assert float(p['total_costs']) == 2000.0           # net (amount only)
    assert float(p['total_revenues']) == 1000.0        # net (amount only)
    assert float(p['profit']) == -41000.0
