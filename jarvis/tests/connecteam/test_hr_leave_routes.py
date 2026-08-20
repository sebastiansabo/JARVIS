"""Flask route tests for the HR-scoped leave edit/archive/restore routes.

Mirrors tests/connecteam/test_leave_permit_routes.py, but these routes are
guarded by @admin_required (checks current_user.can_access_settings), so the
FakeUser carries that flag. The service layer (leave_permit_actions) is
monkeypatched — these exercise the HTTP layer only (auth gate, request/response
shape, error-code mapping).
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask
from flask_login import LoginManager

import core.utils.api_helpers as api_helpers
import core.connectors.connecteam.routes as routes
from core.connectors.connecteam import connecteam_bp


class FakeUser:
    def __init__(self, uid, is_admin=True):
        self.id = uid
        self.is_authenticated = True
        self.can_access_settings = is_admin


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(connecteam_bp)
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test'
    login_manager = LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def _load_user(user_id):
        return None

    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def login_as(monkeypatch):
    def _login(user_id, is_admin=True):
        fake = FakeUser(user_id, is_admin=is_admin)
        monkeypatch.setattr(api_helpers, 'current_user', fake)
        monkeypatch.setattr(routes, 'current_user', fake)
        return fake
    return _login


_EDIT = {'leave_date': '2026-08-20', 'leave_start_time': '09:00',
         'leave_end_time': '11:00', 'leave_reason': 'Personal'}


# ── auth gate ──

def test_edit_requires_auth(client):
    r = client.patch('/connecteam/api/hr/leaves/jarvis/42', json=_EDIT)
    assert r.status_code == 401


def test_edit_forbidden_for_non_admin(client, login_as):
    login_as(user_id=9, is_admin=False)
    r = client.patch('/connecteam/api/hr/leaves/jarvis/42', json=_EDIT)
    assert r.status_code == 403


def test_archive_requires_auth(client):
    r = client.post('/connecteam/api/hr/leaves/jarvis/42/archive')
    assert r.status_code == 401


# ── edit route ──

def test_edit_route_calls_service(client, monkeypatch, login_as):
    from core.connectors.connecteam.services import leave_permit_actions as lpa
    captured = {}
    def fake(source, eid, fields):
        captured['args'] = (source, eid, fields)
        return {'source': source, 'id': eid}
    monkeypatch.setattr(lpa, 'hr_update_leave', fake)
    login_as(user_id=9)
    r = client.patch('/connecteam/api/hr/leaves/connecteam/7', json=_EDIT)
    assert r.status_code == 200 and r.get_json()['data'] == {'source': 'connecteam', 'id': 7}
    assert captured['args'] == ('connecteam', 7, _EDIT)


def test_edit_route_400_on_value_error(client, monkeypatch, login_as):
    from core.connectors.connecteam.services import leave_permit_actions as lpa
    monkeypatch.setattr(lpa, 'hr_update_leave',
        lambda s, e, f: (_ for _ in ()).throw(ValueError('Data invalidă')))
    login_as(user_id=9)
    r = client.patch('/connecteam/api/hr/leaves/jarvis/42', json=_EDIT)
    assert r.status_code == 400 and 'invalid' in r.get_json()['error'].lower()


def test_edit_route_404_on_lookup_error(client, monkeypatch, login_as):
    from core.connectors.connecteam.services import leave_permit_actions as lpa
    monkeypatch.setattr(lpa, 'hr_update_leave',
        lambda s, e, f: (_ for _ in ()).throw(LookupError('Submission not found')))
    login_as(user_id=9)
    r = client.patch('/connecteam/api/hr/leaves/jarvis/999', json=_EDIT)
    assert r.status_code == 404


# ── archive / restore routes ──

def test_archive_route_calls_service_with_true(client, monkeypatch, login_as):
    from core.connectors.connecteam.services import leave_permit_actions as lpa
    captured = {}
    def fake(source, eid, actor_id, archived):
        captured['args'] = (source, eid, actor_id, archived)
        return {'source': source, 'id': eid, 'archived': archived}
    monkeypatch.setattr(lpa, 'hr_set_archived', fake)
    login_as(user_id=9)
    r = client.post('/connecteam/api/hr/leaves/jarvis/42/archive')
    assert r.status_code == 200 and r.get_json()['data']['archived'] is True
    assert captured['args'] == ('jarvis', 42, 9, True)


def test_restore_route_calls_service_with_false(client, monkeypatch, login_as):
    from core.connectors.connecteam.services import leave_permit_actions as lpa
    captured = {}
    def fake(source, eid, actor_id, archived):
        captured['args'] = (source, eid, actor_id, archived)
        return {'source': source, 'id': eid, 'archived': archived}
    monkeypatch.setattr(lpa, 'hr_set_archived', fake)
    login_as(user_id=9)
    r = client.post('/connecteam/api/hr/leaves/connecteam/7/restore')
    assert r.status_code == 200 and r.get_json()['data']['archived'] is False
    assert captured['args'] == ('connecteam', 7, 9, False)


def test_archive_route_404_on_lookup_error(client, monkeypatch, login_as):
    from core.connectors.connecteam.services import leave_permit_actions as lpa
    monkeypatch.setattr(lpa, 'hr_set_archived',
        lambda s, e, a, archived: (_ for _ in ()).throw(LookupError('Submission not found')))
    login_as(user_id=9)
    r = client.post('/connecteam/api/hr/leaves/jarvis/999/archive')
    assert r.status_code == 404
