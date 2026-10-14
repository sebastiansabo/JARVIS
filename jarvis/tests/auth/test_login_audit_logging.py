"""Tests for login audit logging (web + mobile observability fixes).

Mobile auth routes previously wrote NO audit rows for login attempts, so a
failed mobile login left zero server trace (telemetry can't see pre-session
events either). These tests pin the new `user_events` rows: platform marker,
failure reasons, and OTP-stage failures.

Harness mirrors test_mobile_login_otp.py: a minimal Flask app with mobile_bp
and module-level deps monkeypatched in core.mobile.routes.auth.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

from core.mobile import mobile_bp
import core.mobile.routes.auth as auth_mod


class FakeUser:
    def __init__(self, data):
        self.id = data['id']
        self.email = data.get('email', 'user@example.com')
        self.name = data.get('name', 'Test User')
        self.role_name = data.get('role_name')
        self.role_id = None
        self.phone = None
        self.company = None
        self.department = None


@pytest.fixture(autouse=True)
def patch_user_model(monkeypatch):
    monkeypatch.setattr(auth_mod, 'User', FakeUser)
    monkeypatch.setattr(auth_mod, '_user_json', lambda user: {'id': user.id, 'email': user.email})


@pytest.fixture(autouse=True)
def fresh_rate_limiter(monkeypatch):
    from core.utils.api_helpers import RateLimiter
    monkeypatch.setattr(auth_mod, '_auth_limiter', RateLimiter())


@pytest.fixture(autouse=True)
def recorded_events(monkeypatch):
    """Capture every audit log_event call instead of hitting the DB."""
    events = []

    class FakeEventRepo:
        def log_event(self, **kwargs):
            events.append(kwargs)
            return 1

    monkeypatch.setattr(auth_mod, '_event_repo', FakeEventRepo())
    return events


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(mobile_bp)
    app.config['TESTING'] = True
    return app.test_client()


def _row(user_id=1, email='user@example.com', role_name=None):
    return {'id': user_id, 'email': email, 'name': 'Test User', 'is_active': True, 'role_name': role_name}


def _only(events, event_type):
    return [e for e in events if e['event_type'] == event_type]


# ── /api/auth/token ──────────────────────────────────────────────

def test_mobile_bad_credentials_logs_login_failed(client, monkeypatch, recorded_events):
    monkeypatch.setattr(auth_mod._user_repo, 'authenticate_identifier', lambda i, p: None)
    monkeypatch.setattr(auth_mod._user_repo, 'classify_login_failure', lambda i: 'bad_password')

    resp = client.post('/api/auth/token', json={'email': 'user@example.com', 'password': 'wrong'})
    assert resp.status_code == 401

    fails = _only(recorded_events, 'login_failed')
    assert len(fails) == 1
    assert fails[0]['details']['platform'] == 'mobile'
    assert fails[0]['details']['reason'] == 'bad_password'
    assert fails[0]['user_email'] == 'user@example.com'


def test_mobile_inactive_account_reason_propagates(client, monkeypatch, recorded_events):
    monkeypatch.setattr(auth_mod._user_repo, 'authenticate_identifier', lambda i, p: None)
    monkeypatch.setattr(auth_mod._user_repo, 'classify_login_failure', lambda i: 'inactive_account')

    resp = client.post('/api/auth/token', json={'email': 'gone@example.com', 'password': 'x'})
    assert resp.status_code == 401
    assert _only(recorded_events, 'login_failed')[0]['details']['reason'] == 'inactive_account'


def test_mobile_phone_login_nonviewer_logs_failure(client, monkeypatch, recorded_events):
    # Non-viewer (role_name None) using a phone identifier (no '@') → 403.
    monkeypatch.setattr(auth_mod._user_repo, 'authenticate_identifier', lambda i, p: _row(role_name='Advisor'))

    resp = client.post('/api/auth/token', json={'identifier': '0712345678', 'password': 'pw'})
    assert resp.status_code == 403

    fails = _only(recorded_events, 'login_failed')
    assert len(fails) == 1
    assert fails[0]['details']['reason'] == 'phone_login_nonviewer'
    assert fails[0]['user_id'] == 1


def test_mobile_viewer_success_logs_login(client, monkeypatch, recorded_events):
    monkeypatch.setattr(auth_mod._user_repo, 'authenticate_identifier', lambda i, p: _row(role_name='Viewer'))
    monkeypatch.setattr(auth_mod._user_repo, 'update_last_login', lambda uid: None)

    resp = client.post('/api/auth/token', json={'identifier': '0712345678', 'password': 'pw'})
    assert resp.status_code == 200

    logins = _only(recorded_events, 'login')
    assert len(logins) == 1
    assert logins[0]['details']['platform'] == 'mobile'
    assert logins[0]['details']['factor'] == 'viewer'


def test_mobile_rate_limited_logs_failure(client, monkeypatch, recorded_events):
    # Exhaust the limiter (10 per window) then the 11th should log + 429.
    monkeypatch.setattr(auth_mod._user_repo, 'authenticate_identifier', lambda i, p: None)
    monkeypatch.setattr(auth_mod._user_repo, 'classify_login_failure', lambda i: 'bad_password')
    for _ in range(10):
        client.post('/api/auth/token', json={'email': 'u@e.com', 'password': 'x'})
    resp = client.post('/api/auth/token', json={'email': 'u@e.com', 'password': 'x'})
    assert resp.status_code == 429
    assert any(e['details'].get('reason') == 'rate_limited' for e in _only(recorded_events, 'login_failed'))


# ── /api/auth/verify-otp ─────────────────────────────────────────

def test_mobile_otp_verify_failure_logs_otp_failed(client, monkeypatch, recorded_events):
    monkeypatch.setattr(auth_mod._user_repo, 'get_otp', lambda cid: {'user_id': 7, 'used_at': None})

    class FakeSvc:
        def verify_otp(self, cid, code, secret):
            return False, 'Invalid code. 2 attempts remaining.'

    monkeypatch.setattr(auth_mod, 'AuthService', FakeSvc)

    resp = client.post('/api/auth/verify-otp', json={'challenge_id': 10, 'code': '000000'})
    assert resp.status_code == 401
    fails = _only(recorded_events, 'login_otp_failed')
    assert len(fails) == 1
    assert fails[0]['details']['reason'] == 'otp_failed'
    assert fails[0]['user_id'] == 7


def test_mobile_otp_verify_success_logs_login(client, monkeypatch, recorded_events):
    monkeypatch.setattr(auth_mod._user_repo, 'get_otp', lambda cid: {'user_id': 7, 'used_at': None})
    monkeypatch.setattr(auth_mod._user_repo, 'get_by_id', lambda uid: _row(user_id=7))
    monkeypatch.setattr(auth_mod._user_repo, 'update_last_login', lambda uid: None)

    class FakeSvc:
        def verify_otp(self, cid, code, secret):
            return True, ''

        def create_trusted_device_token(self, uid, did, secret):
            return 'trusted-tok'

    monkeypatch.setattr(auth_mod, 'AuthService', FakeSvc)

    resp = client.post('/api/auth/verify-otp', json={'challenge_id': 10, 'code': '123456', 'device_id': 'd1'})
    assert resp.status_code == 200
    logins = _only(recorded_events, 'login')
    assert len(logins) == 1
    assert logins[0]['details']['factor'] == 'otp'
    assert logins[0]['details']['platform'] == 'mobile'


def test_audit_failure_never_breaks_login(client, monkeypatch):
    """A broken audit logger must not turn a valid login into an error."""
    monkeypatch.setattr(auth_mod._user_repo, 'authenticate_identifier', lambda i, p: _row(role_name='Viewer'))
    monkeypatch.setattr(auth_mod._user_repo, 'update_last_login', lambda uid: None)

    class BoomRepo:
        def log_event(self, **kwargs):
            raise RuntimeError('db down')

    monkeypatch.setattr(auth_mod, '_event_repo', BoomRepo())

    resp = client.post('/api/auth/token', json={'identifier': '0712345678', 'password': 'pw'})
    assert resp.status_code == 200  # login still succeeds despite audit failure
