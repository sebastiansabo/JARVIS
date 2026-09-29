"""Add-vehicle fuel-type/capacity validation (POST /api/foi-parcurs/vehicles).

Regression guard: a plain Hybrid (HEV) has a fuel tank only and must NOT be
gated on battery capacity — only Electric and Plug-in Hybrid (PHEV) charge a
traction battery. The backend rule must mirror the frontend usesBattery/
usesFuelTank helpers and route_sheet_service. See the recurring "Hybrid gate on
battery capacity" bug: the frontend was fixed but this endpoint kept the old gate.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.vehicles as veh_routes


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def captured(monkeypatch):
    """Stub the repo so no DB is touched; capture what create() would persist."""
    seen = {}

    def fake_create(data):
        seen.update(data)
        return {'id': 1, **data}

    monkeypatch.setattr(veh_routes._vehicle_repo, 'get_by_vin', lambda vin: None)
    monkeypatch.setattr(veh_routes._vehicle_repo, 'create', fake_create)
    return seen


def _body(**over):
    b = {'vin': 'WAUZZZF4T1021365', 'mark': 'MG', 'model': 'ZS HEV'}
    b.update(over)
    return b


def test_hybrid_does_not_require_battery(client, captured):
    """The reported bug: adding a Hybrid must succeed with no battery, and the
    battery value is nulled (HEV = fuel only)."""
    resp = client.post('/api/foi-parcurs/vehicles',
                       json=_body(fuel_type='Hybrid', fuel_tank_capacity_liters=45))
    assert resp.status_code == 200, resp.get_json()
    assert captured['battery_capacity_kwh'] is None
    assert captured['fuel_tank_capacity_liters'] == 45


def test_hybrid_still_requires_tank(client, captured):
    resp = client.post('/api/foi-parcurs/vehicles', json=_body(fuel_type='Hybrid'))
    assert resp.status_code == 400
    assert 'Fuel capacity' in resp.get_json()['error']


def test_plugin_hybrid_is_accepted_and_gates_battery(client, captured):
    # Missing battery -> gated (PHEV genuinely charges).
    resp = client.post('/api/foi-parcurs/vehicles',
                       json=_body(fuel_type='Plug-in Hybrid', fuel_tank_capacity_liters=40))
    assert resp.status_code == 400
    assert 'Battery capacity' in resp.get_json()['error']
    # With both tank and battery -> accepted (old code rejected the fuel type outright).
    resp = client.post('/api/foi-parcurs/vehicles',
                       json=_body(fuel_type='Plug-in Hybrid',
                                  fuel_tank_capacity_liters=40, battery_capacity_kwh=16))
    assert resp.status_code == 200, resp.get_json()
    assert captured['battery_capacity_kwh'] == 16
    assert captured['fuel_tank_capacity_liters'] == 40


def test_electric_requires_battery_not_tank(client, captured):
    resp = client.post('/api/foi-parcurs/vehicles', json=_body(fuel_type='Electric'))
    assert resp.status_code == 400
    assert 'Battery capacity' in resp.get_json()['error']
    resp = client.post('/api/foi-parcurs/vehicles',
                       json=_body(fuel_type='Electric', battery_capacity_kwh=64))
    assert resp.status_code == 200, resp.get_json()
    assert captured['battery_capacity_kwh'] == 64
    assert captured['fuel_tank_capacity_liters'] is None
