"""Coverage for the WEB audit changes + the real classify_login_failure body
(the mobile suite stubs classify_login_failure, so its logic is pinned here)."""
import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest

from core.auth.repositories.user_repository import UserRepository
import core.auth.routes as auth_routes


# ── classify_login_failure (unit) ────────────────────────────────

@pytest.fixture
def repo():
    return UserRepository()


def test_classify_empty_identifier(repo):
    assert repo.classify_login_failure('') == 'empty_identifier'
    assert repo.classify_login_failure('   ') == 'empty_identifier'


def test_classify_unknown_account(repo, monkeypatch):
    monkeypatch.setattr(repo, 'get_by_email', lambda e: None)
    assert repo.classify_login_failure('nobody@example.com') == 'unknown_account'


def test_classify_inactive_account(repo, monkeypatch):
    monkeypatch.setattr(repo, 'get_by_email', lambda e: {'is_active': False, 'password_hash': 'x'})
    assert repo.classify_login_failure('gone@example.com') == 'inactive_account'


def test_classify_no_password(repo, monkeypatch):
    monkeypatch.setattr(repo, 'get_by_email', lambda e: {'is_active': True, 'password_hash': None})
    assert repo.classify_login_failure('new@example.com') == 'no_password'


def test_classify_bad_password(repo, monkeypatch):
    monkeypatch.setattr(repo, 'get_by_email', lambda e: {'is_active': True, 'password_hash': 'hash'})
    assert repo.classify_login_failure('user@example.com') == 'bad_password'


def test_classify_phone_path_uses_get_by_phone(repo, monkeypatch):
    seen = {}
    monkeypatch.setattr(repo, 'get_by_phone', lambda p: seen.setdefault('p', p) and None or None)
    assert repo.classify_login_failure('0712345678') == 'unknown_account'
    assert seen['p'] == '0712345678'


def test_classify_swallows_lookup_errors(repo, monkeypatch):
    def boom(_):
        raise RuntimeError('db down')
    monkeypatch.setattr(repo, 'get_by_email', boom)
    assert repo.classify_login_failure('user@example.com') == 'unknown'


# ── web /login/verify → login_otp_failed ─────────────────────────

@pytest.fixture
def web_client(monkeypatch):
    from flask import Flask
    from flask_login import LoginManager
    from core.auth import auth_bp

    monkeypatch.setattr(auth_routes, 'render_template', lambda *a, **k: 'VERIFY_PAGE')

    app = Flask(__name__)
    app.secret_key = 'test-secret'
    app.config['WTF_CSRF_ENABLED'] = False

    lm = LoginManager()
    lm.init_app(app)

    @lm.user_loader
    def _load(uid):
        return None

    @app.route('/')
    def index():
        return 'HOME'

    app.register_blueprint(auth_bp)
    return app


def test_web_otp_failure_logs_login_otp_failed(web_client, monkeypatch):
    events = []

    class FakeEventRepo:
        def log_event(self, **kwargs):
            events.append(kwargs)
            return 1

    monkeypatch.setattr(auth_routes, '_event_repo', FakeEventRepo())

    # OTP row for the _render_verify_page countdown lookup.
    monkeypatch.setattr(auth_routes._user_repo, 'get_otp',
                        lambda oid: {'used_at': None,
                                     'expires_at': datetime.now(timezone.utc) + timedelta(minutes=4)})

    class _Svc:
        def verify_otp(self, otp_id, code, secret):
            return False, 'Invalid code. 2 attempts remaining.'
    monkeypatch.setattr(auth_routes, '_get_auth_service', lambda: _Svc())

    client = web_client.test_client()
    with client.session_transaction() as sess:
        import time as _t
        sess['otp_pending'] = {'user_id': 42, 'otp_id': 7, 'remember': False,
                               'next_page': None, 'created_at': _t.time()}

    resp = client.post('/login/verify', data={'otp_code': '000000'}, follow_redirects=False)
    assert resp.status_code == 200  # re-renders verify page, not a redirect

    fails = [e for e in events if e['event_type'] == 'login_otp_failed']
    assert len(fails) == 1
    assert fails[0]['details']['platform'] == 'web'
    assert fails[0]['details']['reason'] == 'otp_failed'
    assert fails[0]['details']['user_id'] == 42
