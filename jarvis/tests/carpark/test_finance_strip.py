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
94001-94008 (confirmed unused across `tests/carpark/` at the time this file
was written — 91xxx/92xxx/93xxx/95xxx are taken by other modules), one per
distinct login.

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

def test_get_vehicle_strips_acquisition_price_without_finance(client, monkeypatch):
    _login(client, monkeypatch, uid=94001, finance=False)
    with mock.patch.object(vehicles_module._vehicle_service, 'get_vehicle',
                            return_value={'id': 1, 'vin': 'X' * 17, 'acquisition_price': 12345,
                                          'total_costs': 500, 'gross_margin': 800}):
        r = client.get('/api/carpark/vehicles/1')
    assert r.status_code == 200
    body = r.get_json()['vehicle']
    assert 'acquisition_price' not in body and 'gross_margin' not in body and 'total_costs' not in body
    assert body['id'] == 1 and body['vin'] == 'X' * 17


def test_get_vehicle_keeps_finance_with_permission(client, monkeypatch):
    _login(client, monkeypatch, uid=94002, finance=True)
    with mock.patch.object(vehicles_module._vehicle_service, 'get_vehicle',
                            return_value={'id': 1, 'vin': 'X' * 17, 'acquisition_price': 12345}):
        r = client.get('/api/carpark/vehicles/1')
    assert r.get_json()['vehicle'].get('acquisition_price') == 12345


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


def test_put_vehicle_strips_acquisition_price_without_finance(client, monkeypatch):
    _login(client, monkeypatch, uid=94003, finance=False)
    base = {'id': 1, 'company_id': 1, 'vin': 'X' * 17}
    captured = _capturing_update_vehicle(monkeypatch, base)
    with mock.patch.object(vehicles_module, '_verify_vehicle_ownership',
                            return_value=(base, None)):
        r = client.put('/api/carpark/vehicles/1', json={
            'acquisition_price': 99999, 'gross_margin': 500, 'model': 'X5',
        })
    assert r.status_code == 200
    assert 'acquisition_price' not in captured['data']
    assert 'gross_margin' not in captured['data']
    assert captured['data']['model'] == 'X5'


def test_put_vehicle_keeps_acquisition_price_with_finance(client, monkeypatch):
    _login(client, monkeypatch, uid=94004, finance=True)
    base = {'id': 1, 'company_id': 1, 'vin': 'X' * 17}
    captured = _capturing_update_vehicle(monkeypatch, base)
    with mock.patch.object(vehicles_module, '_verify_vehicle_ownership',
                            return_value=(base, None)):
        r = client.put('/api/carpark/vehicles/1', json={'acquisition_price': 99999})
    assert r.status_code == 200
    assert captured['data']['acquisition_price'] == 99999


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
    # Non-finance structures untouched.
    assert body['summary']['total_vehicles'] == 3
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


def test_analytics_kpis_strips_finance_without_permission(client, monkeypatch):
    _login(client, monkeypatch, uid=94006, finance=False)
    with mock.patch.object(analytics_module, '_acting_company_id', return_value=1), \
         mock.patch.object(analytics_module._analytics, 'get_kpis',
                            return_value=_real_kpis_payload()):
        r = client.get('/api/carpark/analytics/kpis')
    assert r.status_code == 200
    body = r.get_json()
    assert 'profitability' not in body
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
    prof = r.get_json()['profitability']
    assert prof['total_gross_profit'] == 15000
    assert prof['avg_margin_percent'] == 15.0
    assert prof['total_acquisition'] == 80000
