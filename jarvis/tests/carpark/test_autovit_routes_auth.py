# jarvis/tests/carpark/test_autovit_routes_auth.py
"""Autovit connector route authorization.

Mirrors the Shopify connector's gating: account-config writes (save/delete/
test-connection) require admin (can_access_settings); the read endpoints
(list/get/status/adverts) require CarPark access. Before this, every endpoint
was only @api_login_required, so any authenticated user could create/delete
dealer accounts (which store credentials) or trigger credential-using calls.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
import pytest
from flask import Flask
import core.utils.api_helpers as api_helpers
import carpark.routes.vehicles as vehicles_mod
from carpark.connectors.autovit import autovit_bp
import carpark.connectors.autovit.routes as routes_mod


class AdminUser:
    is_authenticated = True; id = 1; name = 'Admin'; company_id = 10
    can_access_carpark = True; can_edit_carpark = True
    can_view_carpark_finance = True; can_access_settings = True


class NoSettingsUser:
    # A CarPark manager WITHOUT admin: may read, must not manage accounts.
    is_authenticated = True; id = 2; name = 'Mgr'; company_id = 10
    can_access_carpark = True; can_edit_carpark = True
    can_view_carpark_finance = True; can_access_settings = False


class NoCarparkUser:
    # Authenticated but no CarPark access at all.
    is_authenticated = True; id = 3; name = 'Other'; company_id = 10
    can_access_carpark = False; can_edit_carpark = False
    can_view_carpark_finance = False; can_access_settings = False


def _set_user(monkeypatch, user):
    # admin_required / api_login_required read current_user from api_helpers;
    # carpark_required reads it from the vehicles module; the route bodies read
    # the autovit routes module's own import. Patch all three.
    monkeypatch.setattr(api_helpers, 'current_user', user)
    monkeypatch.setattr(vehicles_mod, 'current_user', user)
    monkeypatch.setattr(routes_mod, 'current_user', user)


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(autovit_bp)
    app.config['TESTING'] = True
    return app.test_client()


# ── writes require admin (can_access_settings) ──

def test_save_account_forbidden_without_settings(client, monkeypatch):
    _set_user(monkeypatch, NoSettingsUser())
    r = client.post('/autovit/api/config',
                    json={'email': 'a@b.c', 'client_id': 'x',
                          'client_secret': 's', 'password': 'p'})
    assert r.status_code == 403


def test_delete_account_forbidden_without_settings(client, monkeypatch):
    _set_user(monkeypatch, NoSettingsUser())
    r = client.delete('/autovit/api/config/5')
    assert r.status_code == 403


def test_test_connection_forbidden_without_settings(client, monkeypatch):
    _set_user(monkeypatch, NoSettingsUser())
    r = client.post('/autovit/api/test-connection', json={'account_id': 5})
    assert r.status_code == 403


# ── reads require CarPark access ──

def test_get_accounts_forbidden_without_carpark(client, monkeypatch):
    _set_user(monkeypatch, NoCarparkUser())
    r = client.get('/autovit/api/config')
    assert r.status_code == 403


def test_get_account_forbidden_without_carpark(client, monkeypatch):
    _set_user(monkeypatch, NoCarparkUser())
    r = client.get('/autovit/api/config/5')
    assert r.status_code == 403


def test_get_status_forbidden_without_carpark(client, monkeypatch):
    _set_user(monkeypatch, NoCarparkUser())
    r = client.get('/autovit/api/status')
    assert r.status_code == 403


def test_get_adverts_forbidden_without_carpark(client, monkeypatch):
    _set_user(monkeypatch, NoCarparkUser())
    r = client.get('/autovit/api/accounts/5/adverts')
    assert r.status_code == 403


# ── positive paths: proper permissions reach the handler ──

def test_get_accounts_allows_carpark_user(client, monkeypatch):
    _set_user(monkeypatch, NoSettingsUser())  # carpark access, no admin
    monkeypatch.setattr(routes_mod._repo, 'get_all_by_type', lambda t: [])
    r = client.get('/autovit/api/config')
    assert r.status_code == 200 and r.get_json()['success'] is True


def test_get_status_allows_carpark_user(client, monkeypatch):
    _set_user(monkeypatch, NoSettingsUser())
    monkeypatch.setattr(routes_mod._repo, 'get_all_by_type', lambda t: [])
    r = client.get('/autovit/api/status')
    assert r.status_code == 200 and r.get_json()['success'] is True


def test_save_account_allows_admin(client, monkeypatch):
    _set_user(monkeypatch, AdminUser())
    monkeypatch.setattr(routes_mod._repo, 'save',
                        lambda ctype, name, status='disconnected', config=None, credentials=None: 7)
    monkeypatch.setattr(routes_mod._repo, 'get',
                        lambda cid: {'id': 7, 'connector_type': 'autovit', 'name': 'a@b.c',
                                     'config': {'email': 'a@b.c'}, 'credentials': {'client_id': 'x'},
                                     'status': 'disconnected'})
    r = client.post('/autovit/api/config',
                    json={'email': 'a@b.c', 'client_id': 'x',
                          'client_secret': 's', 'password': 'p'})
    assert r.status_code == 201 and r.get_json()['success'] is True
