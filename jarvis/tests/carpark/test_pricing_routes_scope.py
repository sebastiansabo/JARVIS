"""Tenant-scoping tests for the pricing RULE / PROMOTION routes
(carpark/routes/pricing.py). These endpoints are keyed by rule_id/promo_id
and never load a vehicle, so before this fix a guessed id let a caller
read/edit/delete/execute another company's pricing rules and promotions.
Rules and promotions carry their own company_id, so scoping checks that
against the caller's actable set (own + org-responsable; Admin = any).

Mock-based, mirroring test_dispo_routes.py: a minimal Flask app registers
carpark_bp, LOGIN_DISABLED makes @login_required a no-op, and current_user
is patched on both the vehicles module (where carpark_required +
_may_act_on_company live) and the pricing module (which calls
_may_act_on_company with its own current_user). _pricing_service is
patched per test; no real DB.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

from carpark import carpark_bp
import carpark.routes.vehicles as vehicles_mod
import carpark.routes.pricing as pricing_mod

COMPANY_ID = 10
OTHER_COMPANY_ID = 99


class FakeUser:
    def __init__(self, id=1, company_id=COMPANY_ID, can_access_settings=False):
        self.id = id
        self.company_id = company_id
        self.is_authenticated = True
        self.can_access_carpark = True
        self.can_edit_carpark = True
        self.can_delete_carpark = True
        self.can_view_carpark_finance = True
        self.can_access_settings = can_access_settings


def _set_user(monkeypatch, user):
    monkeypatch.setattr(vehicles_mod, 'current_user', user)
    monkeypatch.setattr(pricing_mod, 'current_user', user)


@pytest.fixture(autouse=True)
def default_user(monkeypatch):
    _set_user(monkeypatch, FakeUser())
    # _may_act_on_company consults the actable set only for non-own companies.
    monkeypatch.setattr(vehicles_mod, 'get_actable_company_ids', lambda _u: {COMPANY_ID})


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


def _rule(company_id=OTHER_COMPANY_ID):
    return {'id': 1, 'company_id': company_id, 'name': 'R', 'action_type': 'percent'}


def _promo(company_id=OTHER_COMPANY_ID):
    return {'id': 1, 'company_id': company_id, 'name': 'P', 'target_type': 'all'}


# ── RULES ────────────────────────────────────────────────────────────────

def test_get_rule_cross_tenant_blocked_404(client, monkeypatch):
    monkeypatch.setattr(pricing_mod._pricing_service, 'get_rule', lambda rid: _rule())
    r = client.get('/api/carpark/pricing/rules/1')
    assert r.status_code == 404


def test_get_rule_own_company_allowed(client, monkeypatch):
    monkeypatch.setattr(pricing_mod._pricing_service, 'get_rule',
                        lambda rid: _rule(company_id=COMPANY_ID))
    r = client.get('/api/carpark/pricing/rules/1')
    assert r.status_code == 200
    assert r.get_json()['rule']['id'] == 1


def test_get_rule_admin_any_company_allowed(client, monkeypatch):
    _set_user(monkeypatch, FakeUser(can_access_settings=True))
    monkeypatch.setattr(pricing_mod._pricing_service, 'get_rule', lambda rid: _rule())
    r = client.get('/api/carpark/pricing/rules/1')
    assert r.status_code == 200


def test_update_rule_cross_tenant_blocked_404(client, monkeypatch):
    monkeypatch.setattr(pricing_mod._pricing_service, 'get_rule', lambda rid: _rule())
    updated = []
    monkeypatch.setattr(pricing_mod._pricing_service, 'update_rule',
                        lambda rid, data: updated.append(rid))
    r = client.put('/api/carpark/pricing/rules/1', json={'name': 'X'})
    assert r.status_code == 404
    assert updated == []


def test_delete_rule_cross_tenant_blocked_404(client, monkeypatch):
    monkeypatch.setattr(pricing_mod._pricing_service, 'get_rule', lambda rid: _rule())
    deleted = []
    monkeypatch.setattr(pricing_mod._pricing_service, 'delete_rule',
                        lambda rid: deleted.append(rid) or True)
    r = client.delete('/api/carpark/pricing/rules/1')
    assert r.status_code == 404
    assert deleted == []


def test_execute_rule_cross_tenant_blocked_404(client, monkeypatch):
    monkeypatch.setattr(pricing_mod._pricing_service, 'get_rule', lambda rid: _rule())
    executed = []
    monkeypatch.setattr(pricing_mod._pricing_service, 'execute_rule',
                        lambda *a, **k: executed.append(1))
    r = client.post('/api/carpark/pricing/rules/1/execute', json={'dry_run': True})
    assert r.status_code == 404
    assert executed == []


def test_list_rule_vehicles_cross_tenant_blocked_404(client, monkeypatch):
    monkeypatch.setattr(pricing_mod._pricing_service, 'get_rule', lambda rid: _rule())
    listed = []
    monkeypatch.setattr(pricing_mod._pricing_service, 'get_rule_vehicles',
                        lambda rid: listed.append(rid) or [])
    r = client.get('/api/carpark/pricing/rules/1/vehicles')
    assert r.status_code == 404
    assert listed == []


def test_simulate_cross_tenant_rule_blocked_404(client, monkeypatch):
    """A body-supplied rule_id (no vehicle_id) is scoped too — it must not
    leak/execute another company's rule config via the simulator."""
    monkeypatch.setattr(pricing_mod._pricing_service, 'get_rule', lambda rid: _rule())
    simulated = []
    monkeypatch.setattr(pricing_mod._pricing_service, 'simulate_rules',
                        lambda **k: simulated.append(1) or [])
    r = client.post('/api/carpark/pricing/simulate', json={'rule_id': 1})
    assert r.status_code == 404
    assert simulated == []


# ── PROMOTIONS ───────────────────────────────────────────────────────────

def test_get_promotion_cross_tenant_blocked_404(client, monkeypatch):
    monkeypatch.setattr(pricing_mod._pricing_service, 'get_promotion', lambda pid: _promo())
    r = client.get('/api/carpark/promotions/1')
    assert r.status_code == 404


def test_delete_promotion_cross_tenant_blocked_404(client, monkeypatch):
    monkeypatch.setattr(pricing_mod._pricing_service, 'get_promotion', lambda pid: _promo())
    deleted = []
    monkeypatch.setattr(pricing_mod._pricing_service, 'delete_promotion',
                        lambda pid: deleted.append(pid) or True)
    r = client.delete('/api/carpark/promotions/1')
    assert r.status_code == 404
    assert deleted == []


def test_promotion_own_company_allowed(client, monkeypatch):
    monkeypatch.setattr(pricing_mod._pricing_service, 'get_promotion',
                        lambda pid: _promo(company_id=COMPANY_ID))
    r = client.get('/api/carpark/promotions/1')
    assert r.status_code == 200
    assert r.get_json()['promotion']['id'] == 1
