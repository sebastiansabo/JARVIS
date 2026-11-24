"""Task 5 — convergence tests: acquisition costs now count everywhere.

Proves the design's core claim: the three structured cost readers
(`VehicleService.get_profitability`, `DispoRepository.summary`,
`PricingService.calculate_floor_price`) already `SUM` ALL
`carpark_vehicle_costs` rows by `vehicle_id` with no cost-type special-casing,
so the new `achizitie` cost type (registered in Task 1 — see
`carpark/routes/costs.py`) is picked up automatically, with no reader code
changes. This is a tests-only task: if every assertion below passes against
the EXISTING readers, convergence is structural — no production code changes
are required.

Seeds TWO SOLD vehicles under a dedicated sentinel company, identical on
every money field except one has a single structured `achizitie` cost row:

  WITH_COST vehicle:  acquisition_price(gross)=50000, purchase_vat_rate=25,
                      purchase_price_net(net buy)=40000, sale_price=55000,
                      + one carpark_vehicle_costs row
                      (cost_type='achizitie', amount=1000, vat_amount=0).
  BASELINE  vehicle:  identical acquisition/sale fields, NO cost rows.

Expectations (net-basis, mirrors test_cost_model_profit.py's profit_seed):
  net_buy = purchase_price_net = 40000 for both (acquisition_currency is not
  'RON', so carpark.money.net_buy()/NET_BUY_SQL read purchase_price_net
  directly — see carpark/money.py).

  1. get_profitability: total_costs == 1000 (WITH_COST) / 0 (BASELINE);
     profit == total_revenues - net_buy - total_costs for each, and the
     WITH_COST profit is exactly 1000 less than BASELINE's.
  2. DispoRepository.summary: gross_margin == sale_price - net_buy -
     total_costs for each row (14000 WITH_COST vs. 15000 BASELINE).
  3. PricingService.calculate_floor_price: components['total_cost'] ==
     acquisition_price(GROSS) + total_with_vat, where total_with_vat =
     SUM(amount) + SUM(vat_amount). Because the achizitie row's vat_amount=0,
     this is acquisition_price + 1000, NOT acquisition_price + 1190 (the
     anti-VAT-inflation claim: a migrated achizitie row never inflates the
     floor price by a phantom VAT add-on).

Runs against localhost/defaultdb via conftest's REAL_DB_AVAILABLE probe,
using the `require_real_db` fixture (skips cleanly if unreachable).

Invocation:
    DATABASE_URL=postgresql://localhost/defaultdb \
        venv/bin/python -m pytest jarvis/tests/carpark/test_cost_unification_convergence.py -v

Sentinel company_id=990007 — next free after every other sentinel already in
use in this package (990001 dispo_seed, 990002 phase2_e2e/cost_model_profit,
990003 carpark_scheduler/import_centralizator, 990004 import_centralizator's
OTHER_COMPANY_ID, 990005 backfill_acq_currency, 990006
backfill_cost_lines_to_structured — see that file's header for the running
registry).
"""
import pytest

from carpark.services.vehicle_service import VehicleService
from carpark.repositories.dispo_repository import DispoRepository
from carpark.services.pricing_service import PricingService

from database import get_db, get_cursor, release_db

CONV_COMPANY_ID = 990007

VIN_WITH_COST = 'TESTCONV000000001'
VIN_BASELINE = 'TESTCONV000000002'
assert len(VIN_WITH_COST) == 17
assert len(VIN_BASELINE) == 17

ACQUISITION_PRICE_GROSS = 50000
PURCHASE_VAT_RATE = 25
NET_BUY = 40000  # purchase_price_net; 50000 / 1.25 == 40000, consistent with the VAT rate
SALE_PRICE = 55000
ACHIZITIE_AMOUNT = 1000
ACHIZITIE_VAT_AMOUNT = 0  # migrated backfill rows carry no VAT — the anti-inflation case


@pytest.fixture
def conv_seed(require_real_db):
    """Seed WITH_COST + BASELINE vehicles under CONV_COMPANY_ID; teardown
    deletes every carpark_vehicles row for the sentinel company (the
    achizitie cost row cascades via vehicle_id ... ON DELETE CASCADE)."""
    conn = get_db()
    conn.autocommit = False
    cur = get_cursor(conn)
    ids = {}
    try:
        cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (CONV_COMPANY_ID,))

        cur.execute('''
            INSERT INTO carpark_vehicles
                (vin, brand, model, category, status, company_id, acquisition_date,
                 acquisition_price, purchase_vat_rate, purchase_price_net,
                 sale_price, sale_date)
            VALUES (%s,%s,%s,%s,%s,%s, CURRENT_DATE,
                    %s, %s, %s,
                    %s, CURRENT_DATE)
            RETURNING id
        ''', (VIN_WITH_COST, 'TestBrand', 'TestModel', 'SH', 'SOLD', CONV_COMPANY_ID,
              ACQUISITION_PRICE_GROSS, PURCHASE_VAT_RATE, NET_BUY,
              SALE_PRICE))
        ids['with_cost'] = cur.fetchone()['id']

        cur.execute('''INSERT INTO carpark_vehicle_costs (vehicle_id, cost_type, amount, vat_amount)
                       VALUES (%s, %s, %s, %s)''',
                    (ids['with_cost'], 'achizitie', ACHIZITIE_AMOUNT, ACHIZITIE_VAT_AMOUNT))

        cur.execute('''
            INSERT INTO carpark_vehicles
                (vin, brand, model, category, status, company_id, acquisition_date,
                 acquisition_price, purchase_vat_rate, purchase_price_net,
                 sale_price, sale_date)
            VALUES (%s,%s,%s,%s,%s,%s, CURRENT_DATE,
                    %s, %s, %s,
                    %s, CURRENT_DATE)
            RETURNING id
        ''', (VIN_BASELINE, 'TestBrand', 'TestModel', 'SH', 'SOLD', CONV_COMPANY_ID,
              ACQUISITION_PRICE_GROSS, PURCHASE_VAT_RATE, NET_BUY,
              SALE_PRICE))
        ids['baseline'] = cur.fetchone()['id']

        conn.commit()
        yield ids
    finally:
        try:
            cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (CONV_COMPANY_ID,))
            conn.commit()
            cur.execute('SELECT COUNT(*) AS cnt FROM carpark_vehicles WHERE company_id = %s',
                        (CONV_COMPANY_ID,))
            remaining = cur.fetchone()['cnt']
        finally:
            release_db(conn)
        assert remaining == 0, (
            f'teardown left {remaining} orphan carpark_vehicles row(s) for '
            f'company_id={CONV_COMPANY_ID}'
        )


# ─────────────────────────────────────────────────────────────────────────
# 1. VehicleService.get_profitability — Detail/Financiar basis
# ─────────────────────────────────────────────────────────────────────────

def test_profitability_counts_achizitie_cost(conv_seed):
    with_cost = VehicleService().get_profitability(conv_seed['with_cost'])
    baseline = VehicleService().get_profitability(conv_seed['baseline'])

    assert float(with_cost['total_costs']) == 1000.0
    assert float(baseline['total_costs']) == 0.0

    # Exact arithmetic: profit = total_revenues - net_buy - total_costs.
    # No revenue rows seeded, so total_revenues == 0 for both.
    assert float(with_cost['total_revenues']) == 0.0
    assert float(with_cost['profit']) == 0.0 - NET_BUY - 1000.0  # -41000
    assert float(baseline['profit']) == 0.0 - NET_BUY - 0.0      # -40000

    # The achizitie cost reduces profit by EXACTLY 1000 vs. the no-cost baseline.
    assert float(baseline['profit']) - float(with_cost['profit']) == 1000.0


# ─────────────────────────────────────────────────────────────────────────
# 2. DispoRepository.summary — pipeline grid margin
# ─────────────────────────────────────────────────────────────────────────

def test_dispo_summary_margin_counts_achizitie_cost(conv_seed):
    result = DispoRepository().summary(CONV_COMPANY_ID, {})
    by_vin = {row['vin']: row for row in result['rows']}

    with_cost = by_vin[VIN_WITH_COST]
    baseline = by_vin[VIN_BASELINE]

    assert with_cost['total_costs'] == 1000
    assert baseline['total_costs'] == 0

    # gross_margin = sale_price - net_buy - total_costs (NET_BUY_SQL, not gross acquisition_price)
    assert with_cost['gross_margin'] == SALE_PRICE - NET_BUY - 1000  # 14000
    assert baseline['gross_margin'] == SALE_PRICE - NET_BUY - 0      # 15000
    assert baseline['gross_margin'] - with_cost['gross_margin'] == 1000


# ─────────────────────────────────────────────────────────────────────────
# 3. PricingService.calculate_floor_price — anti-VAT-inflation
# ─────────────────────────────────────────────────────────────────────────

def test_floor_price_total_cost_no_vat_inflation(conv_seed):
    with_cost = PricingService().calculate_floor_price(conv_seed['with_cost'])
    baseline = PricingService().calculate_floor_price(conv_seed['baseline'])

    # total_cost = acquisition_price(GROSS) + cost_totals['total_with_vat'],
    # where total_with_vat = SUM(amount) + SUM(vat_amount). The achizitie row
    # has vat_amount=0, so this adds exactly 1000 — NOT 1000 * 1.19 (= 1190),
    # which is what a reader that re-applied a VAT rate to the cost would
    # (incorrectly) produce.
    assert with_cost['components']['total_cost'] == ACQUISITION_PRICE_GROSS + 1000  # 51000
    assert with_cost['components']['total_cost'] != ACQUISITION_PRICE_GROSS + 1190
    assert baseline['components']['total_cost'] == ACQUISITION_PRICE_GROSS + 0      # 50000
