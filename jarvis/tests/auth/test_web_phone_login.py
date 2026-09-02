"""Web /login: Viewer single-factor (phone or email), non-viewer phone reject,
non-viewer email still routed to OTP."""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
import core.auth.routes as auth_routes


@pytest.fixture
def client(monkeypatch):
    from flask import Flask
    from flask_login import LoginManager
    from core.auth import auth_bp

    # Stub render_template so the test never depends on the real Jinja2
    # login page (which references many app endpoints/static assets).
    monkeypatch.setattr(auth_routes, 'render_template', lambda *a, **k: 'LOGIN_PAGE')

    # Stub the audit-log helper: it hits _event_repo → the suite-wide mocked
    # psycopg2 cursor, whose unconfigured fetchone() breaks RETURNING id.
    # Audit logging is orthogonal to the login-routing behavior under test.
    monkeypatch.setattr(auth_routes, '_log_event', lambda *a, **k: None)

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
    return app.test_client()


def _viewer():
    return {'id': 10, 'name': 'V', 'email': 'v@example.com', 'role_name': 'Viewer',
            'is_active': True}


def _admin():
    return {'id': 11, 'name': 'A', 'email': 'a@example.com', 'role_name': 'Admin',
            'is_active': True}


def test_viewer_phone_login_skips_otp(client, monkeypatch):
    monkeypatch.setattr(auth_routes._user_repo, 'authenticate_identifier',
                        lambda ident, pw: _viewer())
    monkeypatch.setattr(auth_routes._user_repo, 'update_last_login', lambda uid: True)
    resp = client.post('/login', data={'email': '0723574040', 'password': 'x'},
                       follow_redirects=False)
    # Logged in → redirect to index, NOT to /login/verify
    assert resp.status_code == 302
    assert '/login/verify' not in resp.headers['Location']


def test_admin_phone_login_rejected(client, monkeypatch):
    monkeypatch.setattr(auth_routes._user_repo, 'authenticate_identifier',
                        lambda ident, pw: _admin())
    resp = client.post('/login', data={'email': '0723574040', 'password': 'x'},
                       follow_redirects=False)
    # Rejected → re-renders login page (200), NOT a redirect (auth succeeded
    # but phone is not allowed for a non-viewer, so it must not log in).
    assert resp.status_code == 200
    assert resp.data == b'LOGIN_PAGE'


def test_admin_email_login_goes_to_otp(client, monkeypatch):
    monkeypatch.setattr(auth_routes._user_repo, 'authenticate_identifier',
                        lambda ident, pw: _admin())

    class _Svc:
        TRUSTED_COOKIE_NAME = 'jarvis_trusted_device'
        def validate_trusted_device_cookie(self, *a, **k):
            return False
        def generate_and_send_otp(self, *a, **k):
            return (999, True, None)
    monkeypatch.setattr(auth_routes, '_get_auth_service', lambda: _Svc())
    resp = client.post('/login', data={'email': 'a@example.com', 'password': 'x'},
                       follow_redirects=False)
    assert resp.status_code == 302
    assert '/login/verify' in resp.headers['Location']
