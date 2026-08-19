"""Flask route tests for the cancel + modify leave-permit routes (Task 7).

No connecteam route-test harness pre-existed; this mirrors the pattern in
tests/dept_pulse/test_dept_pulse_routes.py (Flask app fixture registering the
real blueprint + a FakeUser monkeypatched onto the routes module's
`current_user` binding).

One addition versus that pattern: connecteam routes are guarded by the
project's custom `api_login_required` (core/utils/api_helpers.py), not
flask_login's `@login_required`. That decorator checks `current_user.is_authenticated`
using its own `current_user` name bound in the api_helpers module, so
`app.config['LOGIN_DISABLED']` (which only short-circuits flask_login's own
decorator, per tests/crm/test_client_contacts.py) has no effect here — the
FakeUser must be patched onto *both* api_helpers.current_user (so the
decorator lets the request through) and routes.current_user (so the view
body's `current_user.id` resolves).

Routes under test delegate entirely to
core.connectors.connecteam.services.leave_permit_actions, which is
monkeypatched per-test — these tests exercise the HTTP layer (route
registration, auth gate, request/response shape, error-code mapping), not
the service logic (covered by test_leave_permit_actions.py).
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
    def __init__(self, uid):
        self.id = uid
        self.is_authenticated = True


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(connecteam_bp)
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test'
    # connecteam routes use the custom api_login_required (checks
    # current_user.is_authenticated directly, unlike flask_login's own
    # @login_required) so a LoginManager must be registered — otherwise an
    # unauthenticated request blows up with AttributeError instead of
    # resolving to flask_login's AnonymousUserMixin (is_authenticated=False).
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
    def _login(user_id):
        fake = FakeUser(user_id)
        monkeypatch.setattr(api_helpers, 'current_user', fake)
        monkeypatch.setattr(routes, 'current_user', fake)
        return fake
    return _login


# ── cancel route ──

_REASON = {'reason': 'plec la medic'}


def test_cancel_route_returns_service_status(client, monkeypatch, login_as):
    from core.connectors.connecteam.services import leave_permit_actions as lpa
    monkeypatch.setattr(lpa, 'cancel_leave_permit', lambda sid, uid, reason=None: {'status': 'cancelled'})
    login_as(user_id=9)
    r = client.post('/connecteam/api/submissions/leave-permit/42/cancel', json=_REASON)
    assert r.status_code == 200 and r.get_json()['data'] == {'status': 'cancelled'}


def test_cancel_route_400_without_reason(client, monkeypatch, login_as):
    from core.connectors.connecteam.services import leave_permit_actions as lpa
    called = {'n': 0}
    monkeypatch.setattr(lpa, 'cancel_leave_permit',
                        lambda sid, uid, reason=None: called.update(n=called['n'] + 1))
    login_as(user_id=9)
    r = client.post('/connecteam/api/submissions/leave-permit/42/cancel', json={'reason': '  '})
    assert r.status_code == 400
    assert called['n'] == 0                              # service never reached without a motive


def test_cancel_route_403_for_non_owner(client, monkeypatch, login_as):
    from core.connectors.connecteam.services import leave_permit_actions as lpa
    def boom(sid, uid, reason=None):
        raise PermissionError('nope')
    monkeypatch.setattr(lpa, 'cancel_leave_permit', boom)
    login_as(user_id=9)
    r = client.post('/connecteam/api/submissions/leave-permit/42/cancel', json=_REASON)
    assert r.status_code == 403
    assert r.get_json()['success'] is False


def test_cancel_route_409_on_value_error(client, monkeypatch, login_as):
    from core.connectors.connecteam.services import leave_permit_actions as lpa
    def boom(sid, uid, reason=None):
        raise ValueError('Cannot cancel a request in state cancellation_pending')
    monkeypatch.setattr(lpa, 'cancel_leave_permit', boom)
    login_as(user_id=9)
    r = client.post('/connecteam/api/submissions/leave-permit/42/cancel', json=_REASON)
    assert r.status_code == 409
    assert 'cancellation_pending' in r.get_json()['error']


def test_cancel_route_requires_auth(client):
    r = client.post('/connecteam/api/submissions/leave-permit/42/cancel', json=_REASON)
    assert r.status_code == 401


def test_cancel_route_passes_reason_submission_id_and_current_user(client, monkeypatch, login_as):
    from core.connectors.connecteam.services import leave_permit_actions as lpa
    captured = {}
    def fake_cancel(sid, uid, reason=None):
        captured['args'] = (sid, uid, reason)
        return {'status': 'cancellation_pending'}
    monkeypatch.setattr(lpa, 'cancel_leave_permit', fake_cancel)
    login_as(user_id=9)
    r = client.post('/connecteam/api/submissions/leave-permit/42/cancel', json=_REASON)
    assert r.status_code == 200
    assert captured['args'] == (42, 9, 'plec la medic')


# ── modify route ──

def test_modify_route_calls_service(client, monkeypatch, login_as):
    from core.connectors.connecteam.services import leave_permit_actions as lpa
    monkeypatch.setattr(lpa, 'update_leave_permit', lambda sid, uid, ans: {'submission_id': sid})
    login_as(user_id=9)
    r = client.patch('/connecteam/api/submissions/leave-permit/42', json={'answers': {'f_bi_duration_hours': '1'}})
    assert r.status_code == 200 and r.get_json()['data']['submission_id'] == 42


def test_modify_route_passes_answers_through(client, monkeypatch, login_as):
    from core.connectors.connecteam.services import leave_permit_actions as lpa
    captured = {}
    def fake_update(sid, uid, ans):
        captured['args'] = (sid, uid, ans)
        return {'submission_id': sid}
    monkeypatch.setattr(lpa, 'update_leave_permit', fake_update)
    login_as(user_id=9)
    r = client.patch('/connecteam/api/submissions/leave-permit/42', json={'answers': {'f_bi_duration_hours': '1'}})
    assert r.status_code == 200
    assert captured['args'] == (42, 9, {'f_bi_duration_hours': '1'})


def test_modify_route_403_for_non_owner(client, monkeypatch, login_as):
    from core.connectors.connecteam.services import leave_permit_actions as lpa
    def boom(sid, uid, ans):
        raise PermissionError('nope')
    monkeypatch.setattr(lpa, 'update_leave_permit', boom)
    login_as(user_id=9)
    r = client.patch('/connecteam/api/submissions/leave-permit/42', json={'answers': {}})
    assert r.status_code == 403


def test_modify_route_409_on_value_error(client, monkeypatch, login_as):
    from core.connectors.connecteam.services import leave_permit_actions as lpa
    def boom(sid, uid, ans):
        raise ValueError('Only a pending request can be modified')
    monkeypatch.setattr(lpa, 'update_leave_permit', boom)
    login_as(user_id=9)
    r = client.patch('/connecteam/api/submissions/leave-permit/42', json={'answers': {}})
    assert r.status_code == 409


def test_modify_route_requires_auth(client):
    r = client.patch('/connecteam/api/submissions/leave-permit/42', json={'answers': {}})
    assert r.status_code == 401
