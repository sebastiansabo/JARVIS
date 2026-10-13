# jarvis/tests/carpark/test_carbackground_routes.py
"""CarBackground connector route authorization + config reporting.

Mirrors test_autovit_routes_auth.py's auth-stub approach: `carpark_required`
and `admin_required` read `current_user` from their *own* defining modules
(carpark.routes.vehicles / core.utils.api_helpers) at call time, so patching
those module-level bindings (not the decorated route functions) is what
actually flips the gate for a test client request.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

import core.utils.api_helpers as api_helpers
import carpark.routes.vehicles as vehicles_mod
from carpark.connectors.carbackground import carbackground_bp
import carpark.connectors.carbackground.routes as routes_mod


class AdminUser:
    is_authenticated = True
    id = 1
    can_access_carpark = True
    can_edit_carpark = True
    can_access_settings = True


class NoSettingsUser:
    # CarPark access but not admin: may read, must not write config.
    is_authenticated = True
    id = 2
    can_access_carpark = True
    can_edit_carpark = True
    can_access_settings = False


class NoCarparkUser:
    # Authenticated but no CarPark access at all.
    is_authenticated = True
    id = 3
    can_access_carpark = False
    can_edit_carpark = False
    can_access_settings = False


def _set_user(monkeypatch, user):
    monkeypatch.setattr(api_helpers, 'current_user', user)
    monkeypatch.setattr(vehicles_mod, 'current_user', user)


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(carbackground_bp)
    app.config['TESTING'] = True
    return app.test_client()


# ── package wiring: __init__.py must import routes (Task 3 left this out on
#    purpose; this test fails if that `from . import routes` line regresses,
#    since every other test here imports routes_mod directly and would mask it) ──

def test_package_init_wires_routes_module():
    import sys
    import importlib
    for mod in ('carpark.connectors.carbackground.routes', 'carpark.connectors.carbackground'):
        sys.modules.pop(mod, None)
    pkg = importlib.import_module('carpark.connectors.carbackground')
    assert 'carpark.connectors.carbackground.routes' in sys.modules, (
        '__init__.py must `from . import routes` so registering the blueprint wires endpoints')
    assert len(pkg.carbackground_bp.deferred_functions) >= 5


# ── GET /api/config ──

def test_config_get_forbidden_without_carpark(client, monkeypatch):
    _set_user(monkeypatch, NoCarparkUser())
    r = client.get('/carbackground/api/config')
    assert r.status_code == 403


def test_config_get_reports_unconfigured(client, monkeypatch):
    _set_user(monkeypatch, NoSettingsUser())
    monkeypatch.setattr(routes_mod._repo, 'get_by_type', lambda t: None)
    r = client.get('/carbackground/api/config')
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is True
    assert body['configured'] is False


def test_config_get_reports_configured(client, monkeypatch):
    _set_user(monkeypatch, NoSettingsUser())
    monkeypatch.setattr(routes_mod._repo, 'get_by_type', lambda t: {
        'id': 7, 'status': 'connected',
        'credentials': {'api_key': 'secret'},
        'config': {'background_id': 'bg-1'},
        'last_error': None,
    })
    r = client.get('/carbackground/api/config')
    assert r.status_code == 200
    body = r.get_json()
    assert body['configured'] is True
    conn = body['connector']
    assert conn['has_api_key'] is True
    assert conn['background_id'] == 'bg-1'
    assert 'secret' not in str(conn), 'api key leaked in /api/config response'


def test_config_get_reports_preferred_backgrounds(client, monkeypatch):
    _set_user(monkeypatch, NoSettingsUser())
    monkeypatch.setattr(routes_mod._repo, 'get_by_type', lambda t: {
        'id': 7, 'status': 'connected',
        'credentials': {'api_key': 'secret'},
        'config': {'background_id': 'bg-1',
                   'preferred_background_ids': ['bg-1', 'bg-2', 'bg-3']},
        'last_error': None,
    })
    r = client.get('/carbackground/api/config')
    assert r.status_code == 200
    conn = r.get_json()['connector']
    assert conn['background_id'] == 'bg-1'
    assert conn['preferred_background_ids'] == ['bg-1', 'bg-2', 'bg-3']


def test_config_get_preferred_falls_back_to_single_legacy(client, monkeypatch):
    # A pre-feature connector with only background_id reports it as the lone preferred id.
    _set_user(monkeypatch, NoSettingsUser())
    monkeypatch.setattr(routes_mod._repo, 'get_by_type', lambda t: {
        'id': 7, 'status': 'connected',
        'credentials': {'api_key': 'secret'},
        'config': {'background_id': 'bg-1'},
        'last_error': None,
    })
    r = client.get('/carbackground/api/config')
    conn = r.get_json()['connector']
    assert conn['preferred_background_ids'] == ['bg-1']


# ── POST /api/config requires admin ──

def test_config_post_forbidden_without_settings(client, monkeypatch):
    _set_user(monkeypatch, NoSettingsUser())
    r = client.post('/carbackground/api/config', json={'api_key': 'x'})
    assert r.status_code == 403


def test_config_post_allows_admin_creates_connector(client, monkeypatch):
    _set_user(monkeypatch, AdminUser())
    monkeypatch.setattr(routes_mod._repo, 'get_by_type', lambda t: None)
    monkeypatch.setattr(routes_mod._repo, 'save',
                        lambda ctype, name, status='disconnected', config=None, credentials=None: 42)
    monkeypatch.setattr(routes_mod._repo, 'get', lambda cid: {
        'id': cid, 'status': 'connected',
        'credentials': {'api_key': 'new-key'},
        'config': {'background_id': 'bg-2'},
        'last_error': None,
    })
    r = client.post('/carbackground/api/config',
                    json={'api_key': 'new-key', 'background_id': 'bg-2'})
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is True
    assert body['connector']['has_api_key'] is True
    assert body['connector']['background_id'] == 'bg-2'
    assert 'new-key' not in str(body), 'api key leaked in POST /api/config response'


def test_config_post_saves_preferred_list_and_default(client, monkeypatch):
    _set_user(monkeypatch, AdminUser())
    saved = {}
    monkeypatch.setattr(routes_mod._repo, 'get_by_type', lambda t: None)

    def _fake_save(ctype, name, status='disconnected', config=None, credentials=None):
        saved['config'] = config
        return 42

    monkeypatch.setattr(routes_mod._repo, 'save', _fake_save)
    monkeypatch.setattr(routes_mod._repo, 'get', lambda cid: {
        'id': cid, 'status': 'connected',
        'credentials': {'api_key': 'k'},
        'config': saved['config'],
        'last_error': None,
    })
    r = client.post('/carbackground/api/config', json={
        'api_key': 'k', 'background_id': 'bg-a',
        'preferred_background_ids': ['bg-a', 'bg-b'],
    })
    assert r.status_code == 200
    assert saved['config']['preferred_background_ids'] == ['bg-a', 'bg-b']
    assert saved['config']['background_id'] == 'bg-a'
    assert r.get_json()['connector']['preferred_background_ids'] == ['bg-a', 'bg-b']


def test_config_post_rejects_default_not_in_preferred(client, monkeypatch):
    _set_user(monkeypatch, AdminUser())
    monkeypatch.setattr(routes_mod._repo, 'get_by_type', lambda t: None)
    r = client.post('/carbackground/api/config', json={
        'api_key': 'k', 'background_id': 'bg-c',
        'preferred_background_ids': ['bg-a', 'bg-b'],
    })
    assert r.status_code == 400
    assert 'preferred' in r.get_json()['error'].lower()


# ── GET /api/backgrounds, /api/credits, /api/logs require CarPark access ──

def test_backgrounds_forbidden_without_carpark(client, monkeypatch):
    _set_user(monkeypatch, NoCarparkUser())
    r = client.get('/carbackground/api/backgrounds')
    assert r.status_code == 403


def test_backgrounds_allows_carpark_user(client, monkeypatch):
    _set_user(monkeypatch, NoSettingsUser())
    monkeypatch.setattr(routes_mod._client, 'list_backgrounds', lambda: [{'id': 'bg-1'}])
    r = client.get('/carbackground/api/backgrounds')
    assert r.status_code == 200
    assert r.get_json()['backgrounds'] == [{'id': 'bg-1'}]


def test_credits_forbidden_without_carpark(client, monkeypatch):
    _set_user(monkeypatch, NoCarparkUser())
    r = client.get('/carbackground/api/credits')
    assert r.status_code == 403


def test_credits_allows_carpark_user(client, monkeypatch):
    _set_user(monkeypatch, NoSettingsUser())
    monkeypatch.setattr(routes_mod._client, 'credits', lambda: 100)
    r = client.get('/carbackground/api/credits')
    assert r.status_code == 200
    assert r.get_json()['balance'] == 100


def test_logs_forbidden_without_carpark(client, monkeypatch):
    _set_user(monkeypatch, NoCarparkUser())
    r = client.get('/carbackground/api/logs')
    assert r.status_code == 403


def test_logs_empty_without_connector(client, monkeypatch):
    _set_user(monkeypatch, NoSettingsUser())
    monkeypatch.setattr(routes_mod._repo, 'get_by_type', lambda t: None)
    r = client.get('/carbackground/api/logs')
    assert r.status_code == 200
    assert r.get_json()['logs'] == []


def test_logs_bad_limit_does_not_500(client, monkeypatch):
    # A non-integer ?limit must not raise ValueError -> 500; it falls back to 20.
    _set_user(monkeypatch, NoSettingsUser())
    monkeypatch.setattr(routes_mod._repo, 'get_by_type', lambda t: {'id': 9})
    captured = {}

    def _fake_logs(cid, limit):
        captured['limit'] = limit
        return []

    monkeypatch.setattr(routes_mod._repo, 'get_sync_logs', _fake_logs)
    r = client.get('/carbackground/api/logs?limit=abc')
    assert r.status_code == 200
    assert r.get_json()['logs'] == []
    assert captured['limit'] == 20
