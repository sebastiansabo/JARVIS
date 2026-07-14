"""Tests for mobile login 2FA: OTP challenge on /api/auth/token and
/api/auth/verify-otp issuing tokens + a trusted-device token.

Uses the Flask test client against a minimal app registering mobile_bp,
with _user_repo / AuthService / push helpers mocked at the module level
where they are imported into core.mobile.routes.auth.
"""
import os
import types
from datetime import datetime, timedelta, timezone

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

from core.mobile import mobile_bp
import core.mobile.routes.auth as auth_mod


SECRET = auth_mod._JWT_SECRET


class FakeUser:
    """Minimal stand-in matching the subset of core.auth.models.User used here."""

    def __init__(self, data):
        self.id = data['id']
        self.email = data.get('email', 'user@example.com')
        self.name = data.get('name', 'Test User')
        self.role_id = None
        self.phone = None
        self.company = None
        self.department = None
        self.role_name = None


@pytest.fixture(autouse=True)
def patch_user_model(monkeypatch):
    # Avoid the real User model (which may pull in extra attrs) and
    # _user_json's permission-repo lookups.
    monkeypatch.setattr(auth_mod, 'User', FakeUser)
    monkeypatch.setattr(auth_mod, '_user_json', lambda user: {'id': user.id, 'email': user.email})


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(mobile_bp)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def fresh_rate_limiter(monkeypatch):
    # Avoid cross-test rate-limit bleed (module-level _auth_limiter is shared, in-memory).
    from core.utils.api_helpers import RateLimiter
    monkeypatch.setattr(auth_mod, '_auth_limiter', RateLimiter())


def _user_row(user_id=1, email='user@example.com', name='Test User'):
    return {'id': user_id, 'email': email, 'name': name, 'is_active': True}


def test_trusted_device_returns_tokens_no_otp(client, monkeypatch):
    monkeypatch.setattr(auth_mod._user_repo, 'authenticate', lambda e, p: _user_row())
    monkeypatch.setattr(auth_mod._user_repo, 'update_last_login', lambda uid: True)

    class FakeSvc:
        def validate_trusted_device_token(self, token, uid, device_id, secret):
            assert token == 'trusted-tok'
            assert uid == 1
            assert device_id == 'dev-1'
            return True

    monkeypatch.setattr(auth_mod, 'AuthService', FakeSvc)

    resp = client.post('/api/auth/token', json={
        'email': 'user@example.com',
        'password': 'pw',
        'device_id': 'dev-1',
        'trusted_device_token': 'trusted-tok',
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert 'access_token' in body
    assert 'refresh_token' in body
    assert 'otp_required' not in body
    assert body['user']['id'] == 1


def test_untrusted_device_with_push_sends_push_otp(client, monkeypatch):
    monkeypatch.setattr(auth_mod._user_repo, 'authenticate', lambda e, p: _user_row())
    monkeypatch.setattr(auth_mod._user_repo, 'update_last_login', lambda uid: True)
    monkeypatch.setattr(auth_mod._user_repo, 'create_otp', lambda uid, code_hash, expires_at: 42)

    class FakeSvc:
        OTP_EXPIRY_MINUTES = 5

        def _generate_otp_code(self):
            return '123456'

        def _hash_otp(self, code, secret):
            return f'hash:{code}'

    monkeypatch.setattr(auth_mod, 'AuthService', FakeSvc)

    class FakeDeviceRepo:
        def get_tokens_for_users(self, user_ids):
            return [{'id': 1, 'user_id': 1, 'push_token': 'tok-abc'}]

    monkeypatch.setattr(auth_mod, '_DeviceRepo', FakeDeviceRepo)

    sent = {}

    def fake_send_push(user_ids, title, body, data=None, category='system', bypass_rules=False):
        sent['user_ids'] = user_ids
        sent['title'] = title
        sent['body'] = body
        sent['data'] = data
        sent['bypass_rules'] = bypass_rules

    monkeypatch.setattr(auth_mod, 'send_push_to_users', fake_send_push)

    resp = client.post('/api/auth/token', json={
        'email': 'user@example.com',
        'password': 'pw',
        'device_id': 'new-device',
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {'otp_required': True, 'challenge_id': 42, 'channel': 'push'}

    assert sent['user_ids'] == [1]
    assert sent['bypass_rules'] is True
    assert '123456' in sent['body']
    assert sent['data'] == {'type': 'login_otp', 'code': '123456'}


def test_untrusted_device_without_push_sends_email_otp(client, monkeypatch):
    monkeypatch.setattr(auth_mod._user_repo, 'authenticate', lambda e, p: _user_row())
    monkeypatch.setattr(auth_mod._user_repo, 'update_last_login', lambda uid: True)

    class FakeSvc:
        def generate_and_send_otp(self, user_id, email, name, secret):
            assert user_id == 1
            return (99, True, None)

    monkeypatch.setattr(auth_mod, 'AuthService', FakeSvc)

    class FakeDeviceRepo:
        def get_tokens_for_users(self, user_ids):
            return []

    monkeypatch.setattr(auth_mod, '_DeviceRepo', FakeDeviceRepo)

    push_called = {'called': False}
    monkeypatch.setattr(
        auth_mod, 'send_push_to_users',
        lambda *a, **kw: push_called.update(called=True),
    )

    resp = client.post('/api/auth/token', json={'email': 'user@example.com', 'password': 'pw'})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {'otp_required': True, 'challenge_id': 99, 'channel': 'email'}
    assert push_called['called'] is False


def test_verify_otp_wrong_code_returns_401(client, monkeypatch):
    monkeypatch.setattr(
        auth_mod._user_repo, 'get_otp',
        lambda otp_id: {'id': otp_id, 'user_id': 1, 'code': 'hash', 'used_at': None,
                         'attempts': 0, 'expires_at': datetime.now(timezone.utc) + timedelta(minutes=5)},
    )

    class FakeSvc:
        def verify_otp(self, otp_id, code, secret):
            return (False, 'Invalid code. 4 attempts remaining.')

    monkeypatch.setattr(auth_mod, 'AuthService', FakeSvc)

    resp = client.post('/api/auth/verify-otp', json={
        'challenge_id': 42, 'code': '000000', 'device_id': 'dev-1',
    })
    assert resp.status_code == 401
    assert 'error' in resp.get_json()


def test_verify_otp_correct_code_returns_tokens_and_trusted_token(client, monkeypatch):
    monkeypatch.setattr(
        auth_mod._user_repo, 'get_otp',
        lambda otp_id: {'id': otp_id, 'user_id': 1, 'code': 'hash', 'used_at': None,
                         'attempts': 0, 'expires_at': datetime.now(timezone.utc) + timedelta(minutes=5)},
    )
    monkeypatch.setattr(auth_mod._user_repo, 'get_by_id', lambda uid: _user_row(user_id=uid))
    monkeypatch.setattr(auth_mod._user_repo, 'update_last_login', lambda uid: True)

    class FakeSvc:
        def verify_otp(self, otp_id, code, secret):
            return (True, '')

        def create_trusted_device_token(self, user_id, device_id, secret):
            assert user_id == 1
            assert device_id == 'dev-1'
            return 'new-trusted-token'

    monkeypatch.setattr(auth_mod, 'AuthService', FakeSvc)

    resp = client.post('/api/auth/verify-otp', json={
        'challenge_id': 42, 'code': '123456', 'device_id': 'dev-1',
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert 'access_token' in body
    assert 'refresh_token' in body
    assert body['trusted_device_token'] == 'new-trusted-token'
    assert body['user']['id'] == 1


def test_verify_otp_missing_challenge_returns_401(client, monkeypatch):
    monkeypatch.setattr(auth_mod._user_repo, 'get_otp', lambda otp_id: None)
    resp = client.post('/api/auth/verify-otp', json={
        'challenge_id': 999, 'code': '123456', 'device_id': 'dev-1',
    })
    assert resp.status_code == 401
