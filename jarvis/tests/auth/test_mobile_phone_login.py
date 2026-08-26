"""Mobile /api/auth/token: Viewer phone/email single-factor token issue,
non-viewer phone 403, non-viewer email still OTP challenge."""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask
from core.mobile import mobile_bp
import core.mobile.routes.auth as auth_mod


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(mobile_bp)
    return app.test_client()


class _User:
    def __init__(self, role_name):
        self.id = 5
        self.email = 'v@example.com'
        self.name = 'V'
        self.role_name = role_name
        self.role_id = None
        self.phone = None
        self.company = None
        self.department = None


def _patch(monkeypatch, role_name):
    monkeypatch.setattr(auth_mod._user_repo, 'authenticate_identifier',
                        lambda ident, pw: {'id': 5, 'role_name': role_name})
    monkeypatch.setattr(auth_mod, 'User', lambda data: _User(data['role_name']))
    monkeypatch.setattr(auth_mod, '_user_json', lambda u: {'id': u.id, 'role_name': u.role_name})
    monkeypatch.setattr(auth_mod, '_generate_tokens',
                        lambda uid: {'access_token': 'A', 'refresh_token': 'R'})
    monkeypatch.setattr(auth_mod._user_repo, 'update_last_login', lambda uid: True)


def test_viewer_phone_returns_tokens(client, monkeypatch):
    _patch(monkeypatch, 'Viewer')
    r = client.post('/api/auth/token', json={'identifier': '0723574040', 'password': 'x'})
    assert r.status_code == 200
    assert r.get_json()['access_token'] == 'A'


def test_admin_phone_rejected(client, monkeypatch):
    _patch(monkeypatch, 'Admin')
    r = client.post('/api/auth/token', json={'identifier': '0723574040', 'password': 'x'})
    assert r.status_code == 403


def test_admin_email_otp_challenge(client, monkeypatch):
    _patch(monkeypatch, 'Admin')

    class _Svc:
        OTP_EXPIRY_MINUTES = 5
        def _generate_otp_code(self): return '123456'
        def _hash_otp(self, c, s): return 'h'
        def generate_and_send_otp(self, *a, **k): return (77, True, None)
        def validate_trusted_device_token(self, *a, **k): return False
    monkeypatch.setattr(auth_mod, 'AuthService', lambda: _Svc())

    class _Dev:
        def get_tokens_for_user_device(self, *a, **k): return []
    monkeypatch.setattr(auth_mod, '_DeviceRepo', lambda: _Dev())

    r = client.post('/api/auth/token', json={'email': 'a@example.com', 'password': 'x'})
    assert r.status_code == 200
    assert r.get_json().get('otp_required') is True
