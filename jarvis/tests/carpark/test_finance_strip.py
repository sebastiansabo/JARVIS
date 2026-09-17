"""Tests for the shared finance field-stripping helper (`carpark/finance_guard.py`)
applied to the *mixed* endpoints — routes non-finance users still need but
whose payload contains some money fields: `GET /vehicles/<id>`,
`PUT /vehicles/<id>` (request body), and `/analytics/dashboard` +
`/analytics/kpis`. This complements `test_finance_gate.py` (Task 6), which
covers the *purely*-financial endpoints that are 403'd outright.

Uses the real Flask app (`app.py`) so the actual Flask-Login + carpark
permission-decorator wiring is exercised end-to-end (mirrors
`tests/carpark/test_acting_company.py` / `test_finance_gate.py`, sibling
tests from the same package). Under pytest, the top-level conftest.py mocks
psycopg2 before `app` is imported, so the real `UserRepository.get_by_id`
call made by Flask-Login's user_loader returns `{}` (falsy) instead of a
real user — we patch `app._user_repo.get_by_id` per-test to return a real
user dict so session-based login actually authenticates AND carries the
right `can_access_carpark` / `can_edit_carpark` / `can_view_carpark_finance`
flags (see `core/auth/models.py::User`).

GOTCHA (same as test_acting_company.py / test_finance_gate.py): `app.py`'s
Flask-Login user_loader caches loaded `User` objects per-process for 60s,
keyed by int(user_id). Reusing a uid already claimed by another carpark
test module, or reusing one uid for two different permission sets within
this file, would silently read the stale cached user. We use fresh uids
94001-94008 for the vehicle + dashboard/kpis cases and 96001-96004 for the
sibling /analytics/summary + /analytics/monthly-sales cases (confirmed
unused across `tests/carpark/` at the time this file was written —
91xxx/92xxx/93xxx/95xxx are taken by other modules), one per distinct login.

The GET/PUT vehicle assertions use the REAL `carpark_vehicles` table column
names (`acquisition_value`, `total_cost`, `cost_lines`, `reconditioning_cost`,
`minimum_price`, `pricing_sheets`, …) rather than the DISPO summary-row alias
names (`acquisition_price`/`total_costs`/`gross_margin`) — the detail payload
is `SELECT v.*` from that table, so the alias-named `FINANCE_VEHICLE_FIELDS`
tuple only ever matched `acquisition_price` there and let the rest leak. The
authoritative strip set is `finance_guard.FINANCE_VEHICLE_TABLE_FIELDS`; a
schema-anchored guard test at the bottom fails if a new DECIMAL money column
is added to `carpark_vehicles` without being classified STRIP-or-KEEP.

`GET /vehicles/<id>` wraps the vehicle under a `'vehicle'` key
(`jsonify({'vehicle': _serialize(vehicle)})` in `carpark/routes/vehicles.py`
`get_vehicle`) — NOT the brief's originally-sketched top-level shape, so
assertions below read `body['vehicle']`.
"""
import os
from unittest import mock

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest

import app as app_module
from app import app as flask_app
from carpark.routes import vehicles as vehicles_module
from carpark.routes import analytics as analytics_module


@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    return flask_app.test_client()


def _login(client, monkeypatch, uid, finance=False):
    user = {'id': uid, 'email': f't{uid}@x.com', 'name': 'T', 'company_id': 1,
            'can_access_carpark': True, 'can_edit_carpark': True,
            'can_view_carpark_finance': finance}
    monkeypatch.setattr(app_module._user_repo, 'get_by_id', lambda _u: user)
    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)


# ═══════════════════════════════════════════════
# GET /vehicles/<id>
# ═══════════════════════════════════════════════

def _real_vehicle_row():
    """A `carpark_vehicles` `SELECT v.*` row — every finance/cost column that
    must be stripped for a non-finance user, plus the selling/listing/current
    prices and a plain attribute that must survive."""
    return {
        'id': 1, 'vin': 'X' * 17, 'brand': 'BMW', 'model': 'X5',
        # STRIP — acquisition / cost / margin
        'acquisition_value': 12345, 'acquisition_vat': 2345,
        'acquisition_price': 14690, 'acquisition_currency': 'EUR',
        'acquisition_exchange_rate': 4.97,
        'purchase_price_net': 12000, 'purchase_price_currency': 'EUR',
        'purchase_vat_rate': 19.0, 'reconditioning_cost': 500,
        'transport_cost': 200, 'registration_cost': 100, 'other_costs': 50,
        'total_cost': 12850, 'minimum_price': 15000,
        'cost_lines': '[{"label":"transport","amount":200}]',
        'pricing_sheets': '[{"id":1,"status":"published","margin":1500}]',
        # KEEP — selling / listing / current price + attributes
        'current_price': 18000, 'list_price': 18500,
        'promotional_price': 17900, 'sale_price': 17500,
        'price_currency': 'EUR',
    }


STRIP_COLS = ('acquisition_value', 'acquisition_vat', 'acquisition_price',
              'acquisition_currency', 'acquisition_exchange_rate',
              'purchase_price_net', 'purchase_price_currency',
              'purchase_vat_rate', 'reconditioning_cost', 'transport_cost',
              'registration_cost', 'other_costs', 'total_cost',
              'minimum_price', 'cost_lines', 'pricing_sheets')
KEEP_COLS = ('current_price', 'list_price', 'promotional_price', 'sale_price')


def test_get_vehicle_strips_finance_columns_without_finance(client, monkeypatch):
    _login(client, monkeypatch, uid=94001, finance=False)
    with mock.patch.object(vehicles_module._vehicle_service, 'get_vehicle',
                            return_value=_real_vehicle_row()):
        r = client.get('/api/carpark/vehicles/1')
    assert r.status_code == 200
    body = r.get_json()['vehicle']
    for col in STRIP_COLS:
        assert col not in body, f'finance column {col} leaked to non-finance user'
    # Selling/listing/current price + plain attributes survive.
    for col in KEEP_COLS:
        assert col in body, f'non-finance user lost selling-side field {col}'
    assert body['id'] == 1 and body['vin'] == 'X' * 17 and body['model'] == 'X5'


def test_get_vehicle_keeps_finance_with_permission(client, monkeypatch):
    _login(client, monkeypatch, uid=94002, finance=True)
    with mock.patch.object(vehicles_module._vehicle_service, 'get_vehicle',
                            return_value=_real_vehicle_row()):
        r = client.get('/api/carpark/vehicles/1')
    body = r.get_json()['vehicle']
    for col in STRIP_COLS + KEEP_COLS:
        assert col in body, f'finance user must see {col}'
    assert body['acquisition_value'] == 12345 and body['total_cost'] == 12850


# ═══════════════════════════════════════════════
# PUT /vehicles/<id>
# ═══════════════════════════════════════════════

def _capturing_update_vehicle(monkeypatch, base_vehicle):
    """Patch _vehicle_service.update_vehicle to (a) record the exact data
    dict it was handed and (b) return a plausible vehicle so the route's
    happy path completes. Mirrors test_dispo_routes.py's helper of the
    same name."""
    captured = {}

    def _update(vehicle_id, data, **kwargs):
        captured['data'] = dict(data)
        return {**base_vehicle, **data}

    monkeypatch.setattr(vehicles_module._vehicle_service, 'update_vehicle', _update)
    return captured


def test_put_vehicle_strips_finance_columns_without_finance(client, monkeypatch):
    _login(client, monkeypatch, uid=94003, finance=False)
    base = {'id': 1, 'company_id': 1, 'vin': 'X' * 17}
    captured = _capturing_update_vehicle(monkeypatch, base)
    with mock.patch.object(vehicles_module, '_verify_vehicle_ownership',
                            return_value=(base, None)):
        r = client.put('/api/carpark/vehicles/1', json={
            'acquisition_value': 99999, 'acquisition_vat': 1000,
            'reconditioning_cost': 500, 'transport_cost': 200,
            'total_cost': 12000, 'cost_lines': '[{"label":"x","amount":9}]',
            'pricing_sheets': '[{"margin":1}]', 'minimum_price': 15000,
            # selling-side + plain attribute a non-finance editor MAY set
            'current_price': 18000, 'model': 'X5',
        })
    assert r.status_code == 200
    for col in STRIP_COLS:
        assert col not in captured['data'], \
            f'non-finance editor was able to write finance column {col}'
    # Non-finance editor can still set selling price + attributes.
    assert captured['data']['current_price'] == 18000
    assert captured['data']['model'] == 'X5'


def test_put_vehicle_keeps_finance_columns_with_finance(client, monkeypatch):
    _login(client, monkeypatch, uid=94004, finance=True)
    base = {'id': 1, 'company_id': 1, 'vin': 'X' * 17}
    captured = _capturing_update_vehicle(monkeypatch, base)
    with mock.patch.object(vehicles_module, '_verify_vehicle_ownership',
                            return_value=(base, None)):
        r = client.put('/api/carpark/vehicles/1', json={
            'acquisition_value': 99999, 'reconditioning_cost': 500,
            'total_cost': 12000,
        })
    assert r.status_code == 200
    assert captured['data']['acquisition_value'] == 99999
    assert captured['data']['reconditioning_cost'] == 500


# ═══════════════════════════════════════════════
# /analytics/dashboard, /analytics/kpis
#
# Fixtures mirror the REAL AnalyticsService output shapes (see
# carpark/repositories/analytics_repository.py: get_profitability_overview,
# get_monthly_sales, get_cost_overview) so the tests prove the actual leak
# is closed — not just the one `total_costs` key a hand-trimmed fixture
# would have exposed.
# ═══════════════════════════════════════════════

def _real_profitability():
    """AnalyticsRepository.get_profitability_overview() output — all money."""
    return {
        'vehicles_sold': 4, 'total_revenue': 100000, 'total_acquisition': 80000,
        'total_costs': 5000, 'total_gross_profit': 15000,
        'avg_margin_percent': 15.0, 'avg_profit_per_unit': 3750,
        'avg_days_to_sell': 22,
    }


def _real_dashboard_payload():
    """Mirrors AnalyticsService.get_dashboard() — includes every
    finance-bearing structure a real call would return."""
    return {
        'summary': {'total_vehicles': 3, 'in_stock': 2,
                    'total_stock_value': 50000, 'total_acquisition_value': 40000},
        'kpis': {'avg_days_on_lot': 10, 'inventory_turn_rate': 1.2, 'groi': 5},
        'aging_distribution': [{'bucket': '0-15', 'count': 1, 'total_value': 20000}],
        'profitability': _real_profitability(),
        'brand_breakdown': [{'brand': 'BMW', 'count': 2, 'total_value': 40000}],
        'monthly_sales': [
            {'month': '2026-08', 'sold': 2, 'revenue': 50000, 'gross_profit': 8000},
            {'month': '2026-09', 'sold': 2, 'revenue': 50000, 'gross_profit': 7000},
        ],
        'publishing': {'total_views': 100, 'total_inquiries': 10},
        'cost_overview': [{'cost_type': 'transport', 'entries': 3,
                           'vehicles': 2, 'total_amount': 1200}],
        'recent_activity': [{'vehicle_id': 1, 'new_status': 'SOLD'}],
    }


def _real_kpis_payload():
    """Mirrors AnalyticsService.get_kpis() — kpis + groi + profitability."""
    return {
        'avg_days_on_lot': 10, 'inventory_turn_rate': 1.2, 'groi': 5,
        'profitability': _real_profitability(),
    }


def test_analytics_dashboard_strips_finance_without_permission(client, monkeypatch):
    _login(client, monkeypatch, uid=94005, finance=False)
    with mock.patch.object(analytics_module, '_acting_company_id', return_value=1), \
         mock.patch.object(analytics_module._analytics, 'get_dashboard',
                            return_value=_real_dashboard_payload()):
        r = client.get('/api/carpark/analytics/dashboard')
    assert r.status_code == 200
    body = r.get_json()
    # Finance-bearing STRUCTURES gone entirely.
    assert 'profitability' not in body
    assert 'cost_overview' not in body
    # Per-month profit gone; count + revenue kept (revenue == sale_price, not finance).
    assert body['monthly_sales'], 'monthly_sales itself should survive'
    for row in body['monthly_sales']:
        assert 'gross_profit' not in row
        assert 'revenue' in row and 'sold' in row
    assert body['monthly_sales'][0]['revenue'] == 50000
    # NESTED leaks closed: summary.total_acquisition_value + kpis.groi gone.
    assert 'total_acquisition_value' not in body['summary']
    assert 'groi' not in body['kpis']
    # Non-finance structures untouched.
    assert body['summary']['total_vehicles'] == 3
    assert body['summary']['total_stock_value'] == 50000
    assert body['kpis']['avg_days_on_lot'] == 10


def test_analytics_dashboard_keeps_finance_with_permission(client, monkeypatch):
    _login(client, monkeypatch, uid=94007, finance=True)
    with mock.patch.object(analytics_module, '_acting_company_id', return_value=1), \
         mock.patch.object(analytics_module._analytics, 'get_dashboard',
                            return_value=_real_dashboard_payload()):
        r = client.get('/api/carpark/analytics/dashboard')
    assert r.status_code == 200
    body = r.get_json()
    prof = body['profitability']
    assert prof['total_acquisition'] == 80000
    assert prof['total_gross_profit'] == 15000
    assert prof['avg_margin_percent'] == 15.0
    assert prof['avg_profit_per_unit'] == 3750
    assert prof['total_costs'] == 5000
    assert body['cost_overview'][0]['total_amount'] == 1200
    assert body['monthly_sales'][0]['gross_profit'] == 8000
    # Nested finance kept for finance users.
    assert body['summary']['total_acquisition_value'] == 40000
    assert body['kpis']['groi'] == 5


def test_analytics_kpis_strips_finance_without_permission(client, monkeypatch):
    _login(client, monkeypatch, uid=94006, finance=False)
    with mock.patch.object(analytics_module, '_acting_company_id', return_value=1), \
         mock.patch.object(analytics_module._analytics, 'get_kpis',
                            return_value=_real_kpis_payload()):
        r = client.get('/api/carpark/analytics/kpis')
    assert r.status_code == 200
    body = r.get_json()
    assert 'profitability' not in body
    # groi (avg_margin_percent × turn_rate — recoverable margin) gone.
    assert 'groi' not in body
    # Non-finance KPI counts/rates survive.
    assert body['avg_days_on_lot'] == 10
    assert body['inventory_turn_rate'] == 1.2


def test_analytics_kpis_keeps_finance_with_permission(client, monkeypatch):
    _login(client, monkeypatch, uid=94008, finance=True)
    with mock.patch.object(analytics_module, '_acting_company_id', return_value=1), \
         mock.patch.object(analytics_module._analytics, 'get_kpis',
                            return_value=_real_kpis_payload()):
        r = client.get('/api/carpark/analytics/kpis')
    assert r.status_code == 200
    body = r.get_json()
    prof = body['profitability']
    assert prof['total_gross_profit'] == 15000
    assert prof['avg_margin_percent'] == 15.0
    assert prof['total_acquisition'] == 80000
    assert body['groi'] == 5


# ═══════════════════════════════════════════════
# /analytics/summary  (sibling endpoint — same total_acquisition_value leak)
#
# Route returns get_inventory_summary() directly. Fresh uids 96001/96002.
# ═══════════════════════════════════════════════

def _real_summary_payload():
    """Mirrors AnalyticsRepository.get_inventory_summary()."""
    return {'total_vehicles': 3, 'in_stock': 2,
            'total_stock_value': 50000, 'total_acquisition_value': 40000}


def test_analytics_summary_strips_acquisition_without_permission(client, monkeypatch):
    _login(client, monkeypatch, uid=96001, finance=False)
    with mock.patch.object(analytics_module, '_acting_company_id', return_value=1), \
         mock.patch.object(analytics_module._analytics, 'get_summary',
                            return_value=_real_summary_payload()):
        r = client.get('/api/carpark/analytics/summary')
    assert r.status_code == 200
    body = r.get_json()
    assert 'total_acquisition_value' not in body
    # Counts + stock value (current_price sum, not finance) survive.
    assert body['total_vehicles'] == 3
    assert body['total_stock_value'] == 50000


def test_analytics_summary_keeps_acquisition_with_permission(client, monkeypatch):
    _login(client, monkeypatch, uid=96002, finance=True)
    with mock.patch.object(analytics_module, '_acting_company_id', return_value=1), \
         mock.patch.object(analytics_module._analytics, 'get_summary',
                            return_value=_real_summary_payload()):
        r = client.get('/api/carpark/analytics/summary')
    assert r.status_code == 200
    assert r.get_json()['total_acquisition_value'] == 40000


# ═══════════════════════════════════════════════
# /analytics/monthly-sales  (sibling endpoint — per-row gross_profit leak)
#
# Route returns {'sales': [...]} . Fresh uids 96003/96004.
# ═══════════════════════════════════════════════

def _real_monthly_sales_rows():
    """Mirrors AnalyticsRepository.get_monthly_sales() rows."""
    return [
        {'month': '2026-08', 'sold': 2, 'revenue': 50000, 'gross_profit': 8000},
        {'month': '2026-09', 'sold': 1, 'revenue': 25000, 'gross_profit': 4000},
    ]


def test_analytics_monthly_sales_strips_profit_without_permission(client, monkeypatch):
    _login(client, monkeypatch, uid=96003, finance=False)
    with mock.patch.object(analytics_module, '_acting_company_id', return_value=1), \
         mock.patch.object(analytics_module._analytics, 'get_monthly_sales',
                            return_value=_real_monthly_sales_rows()):
        r = client.get('/api/carpark/analytics/monthly-sales')
    assert r.status_code == 200
    rows = r.get_json()['sales']
    assert rows, 'sales list itself should survive'
    for row in rows:
        assert 'gross_profit' not in row
        assert 'month' in row and 'sold' in row and 'revenue' in row
    assert rows[0]['revenue'] == 50000


def test_analytics_monthly_sales_keeps_profit_with_permission(client, monkeypatch):
    _login(client, monkeypatch, uid=96004, finance=True)
    with mock.patch.object(analytics_module, '_acting_company_id', return_value=1), \
         mock.patch.object(analytics_module._analytics, 'get_monthly_sales',
                            return_value=_real_monthly_sales_rows()):
        r = client.get('/api/carpark/analytics/monthly-sales')
    assert r.status_code == 200
    rows = r.get_json()['sales']
    assert rows[0]['gross_profit'] == 8000


# ═══════════════════════════════════════════════
# Schema-anchored guard — fail if a new DECIMAL money column is added to
# carpark_vehicles without being classified STRIP (FINANCE_VEHICLE_TABLE_FIELDS)
# or explicitly KEEP. Money columns on this table are all DECIMAL(…); NUMERIC
# columns are physical specs (capacity/consumption), not money, so we scan
# DECIMAL only. This makes the finance strip drift-proof: the leak that
# prompted this fix (alias names vs table columns) would have tripped it.
# ═══════════════════════════════════════════════

def test_all_decimal_columns_on_carpark_vehicles_are_classified():
    import re
    import os as _os
    from carpark.finance_guard import FINANCE_VEHICLE_TABLE_FIELDS

    # Selling/listing/current price columns intentionally KEPT (consistent with
    # dispo keeping sale_price). Everything else DECIMAL must be STRIP.
    KEEP_DECIMAL = {'list_price', 'promotional_price', 'current_price', 'sale_price'}

    schema_path = _os.path.join(
        _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
        'migrations', 'domains', 'schema_carpark.py')
    with open(schema_path, encoding='utf-8') as fh:
        src = fh.read()

    # Isolate the CREATE TABLE carpark_vehicles ( ... ) block.
    start = src.index('CREATE TABLE IF NOT EXISTS carpark_vehicles')
    block = src[start:src.index("''", start)]

    # Column definitions like `    reconditioning_cost DECIMAL(12,2) DEFAULT 0,`
    decimal_cols = set(re.findall(r'^\s*([a-z_]+)\s+DECIMAL', block, re.MULTILINE))
    assert decimal_cols, 'guard test failed to parse any DECIMAL columns'

    classified = set(FINANCE_VEHICLE_TABLE_FIELDS) | KEEP_DECIMAL
    unclassified = decimal_cols - classified
    assert not unclassified, (
        f'Unclassified DECIMAL money column(s) on carpark_vehicles: {sorted(unclassified)}. '
        f'Add each to FINANCE_VEHICLE_TABLE_FIELDS (strip) or KEEP_DECIMAL (selling-side).')
