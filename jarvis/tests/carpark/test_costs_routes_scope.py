"""Finding E — the child-id cost/revenue/cost-line routes (carpark/routes/costs.py)
must not leak existence: a cross-tenant cost_id/line_id/revenue_id has to 404
with the SAME entity-specific body as an unknown id ("Cost not found" etc.),
NOT the ownership helper's generic "Vehicle not found". Otherwise the differing
body is an existence oracle (distinguishes "exists in another tenant" from
"doesn't exist"). Mirrors the already-normalized documents.py delete.

Mock-based minimal-app harness (mirrors test_pricing_routes_scope.py): current_user
patched on both the vehicles module (carpark decorators + _may_act_on_company) and
the costs module; _service / _vehicle_service patched per test; no real DB.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

from carpark import carpark_bp
import carpark.routes.vehicles as vehicles_mod
import carpark.routes.costs as costs_mod

COMPANY_ID = 10
OTHER_COMPANY_ID = 999


class FakeUser:
    def __init__(self, company_id=COMPANY_ID, can_access_settings=False):
        self.id = 1
        self.company_id = company_id
        self.is_authenticated = True
        self.can_access_carpark = True
        self.can_edit_carpark = True
        self.can_delete_carpark = True
        self.can_view_carpark_finance = True
        self.can_access_settings = can_access_settings


@pytest.fixture(autouse=True)
def _user(monkeypatch):
    u = FakeUser()
    monkeypatch.setattr(vehicles_mod, 'current_user', u)
    monkeypatch.setattr(costs_mod, 'current_user', u)
    monkeypatch.setattr(vehicles_mod, 'get_actable_company_ids', lambda _x: {COMPANY_ID})


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(carpark_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _foreign_vehicle(monkeypatch):
    """The child row's vehicle belongs to a company outside the actable set."""
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle',
                        lambda vid: {'id': vid, 'company_id': OTHER_COMPANY_ID})


def test_update_cost_cross_tenant_404_says_cost_not_found(client, monkeypatch):
    monkeypatch.setattr(costs_mod._service, 'get_cost', lambda cid: {'id': cid, 'vehicle_id': 42})
    _foreign_vehicle(monkeypatch)
    mutated = []
    monkeypatch.setattr(costs_mod._service, 'update_cost', lambda cid, data: mutated.append(cid))
    r = client.put('/api/carpark/costs/5', json={'amount': 100})
    assert r.status_code == 404
    assert r.get_json()['error'] == 'Cost not found'  # NOT 'Vehicle not found'
    assert mutated == []


def test_delete_cost_cross_tenant_404_says_cost_not_found(client, monkeypatch):
    monkeypatch.setattr(costs_mod._service, 'get_cost', lambda cid: {'id': cid, 'vehicle_id': 42})
    _foreign_vehicle(monkeypatch)
    deleted = []
    monkeypatch.setattr(costs_mod._service, 'delete_cost', lambda cid: deleted.append(cid) or True)
    r = client.delete('/api/carpark/costs/5')
    assert r.status_code == 404
    assert r.get_json()['error'] == 'Cost not found'
    assert deleted == []


def test_update_cost_line_cross_tenant_404_says_cost_line_not_found(client, monkeypatch):
    monkeypatch.setattr(costs_mod._service, 'get_cost_line', lambda lid: {'id': lid, 'vehicle_id': 42})
    _foreign_vehicle(monkeypatch)
    mutated = []
    monkeypatch.setattr(costs_mod._service, 'update_cost_line', lambda lid, **k: mutated.append(lid))
    r = client.put('/api/carpark/cost-lines/5', json={'description': 'x'})
    assert r.status_code == 404
    assert r.get_json()['error'] == 'Cost line not found'
    assert mutated == []


def test_update_revenue_cross_tenant_404_says_revenue_not_found(client, monkeypatch):
    monkeypatch.setattr(costs_mod._service, 'get_revenue', lambda rid: {'id': rid, 'vehicle_id': 42})
    _foreign_vehicle(monkeypatch)
    mutated = []
    monkeypatch.setattr(costs_mod._service, 'update_revenue', lambda rid, data: mutated.append(rid))
    r = client.put('/api/carpark/revenues/5', json={'amount': 100})
    assert r.status_code == 404
    assert r.get_json()['error'] == 'Revenue not found'
    assert mutated == []


def test_update_cost_own_company_allowed(client, monkeypatch):
    """Own-company child row still updates normally (regression guard)."""
    monkeypatch.setattr(costs_mod._service, 'get_cost', lambda cid: {'id': cid, 'vehicle_id': 42})
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle',
                        lambda vid: {'id': vid, 'company_id': COMPANY_ID})
    monkeypatch.setattr(costs_mod._service, 'update_cost',
                        lambda cid, data: {'id': cid, 'amount': data.get('amount')})
    r = client.put('/api/carpark/costs/5', json={'amount': 100})
    assert r.status_code == 200
    assert r.get_json()['cost']['amount'] == 100
