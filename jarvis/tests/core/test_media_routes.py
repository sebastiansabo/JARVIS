"""Tests for the login-gated /api/media/<key> proxy for private Spaces objects.

Uses the real Flask app (`app.py`) so the actual Flask-Login wiring is
exercised end-to-end. Under pytest, the top-level conftest.py mocks
psycopg2 before `app` is imported, so the real `UserRepository.get_by_id`
call made by Flask-Login's user_loader returns `{}` (an empty-but-truthy
cursor row coerced to an empty dict) instead of a real user — which is
falsy and would make every "logged in" session silently fail to
authenticate. We patch `app._user_repo.get_by_id` (the module-level
repository instance app.py's user_loader calls) to return a real user
dict so the session-based login in `_login()` actually authenticates.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from unittest import mock
import pytest

import app as app_module
from app import app as flask_app


@pytest.fixture
def client(monkeypatch):
    flask_app.config['TESTING'] = True
    # Make Flask-Login's user_loader (app.py's load_user) succeed for any
    # uid so that a session-only login (see _login below) is honored.
    monkeypatch.setattr(
        app_module._user_repo, 'get_by_id',
        lambda uid: {'id': int(uid), 'email': 'test@example.com', 'name': 'Test User'}
    )
    return flask_app.test_client()


def _login(client):
    # Match Flask-Login's actual session key (session['_user_id']), which
    # is what LoginManager._load_user() reads — not a custom app key.
    with client.session_transaction() as sess:
        sess['_user_id'] = '1'


def test_media_requires_auth(client):
    r = client.get('/api/media/private/carpark/1/01.jpg')
    assert r.status_code in (401, 302)


def test_media_rejects_disallowed_prefix(client):
    _login(client)
    r = client.get('/api/media/private/signatures/user-1.png')
    assert r.status_code == 403


def test_media_rejects_license_prefix(client):
    # Driver-license images must never be served via this generic proxy.
    _login(client)
    r = client.get('/api/media/private/foi-parcurs/license/abc.png')
    assert r.status_code == 403


def test_media_streams_allowed_key(client):
    _login(client)
    with mock.patch('core.media.routes.spaces_service.fetch',
                    return_value=(b'JPEGDATA', 'image/jpeg')):
        r = client.get('/api/media/private/carpark/18/01.jpg')
    assert r.status_code == 200
    assert r.data == b'JPEGDATA'
    assert r.headers['Content-Type'] == 'image/jpeg'
    assert 'max-age' in r.headers.get('Cache-Control', '')


def test_media_image_sets_security_headers(client):
    # Every response — including a legitimate inline image — must carry the
    # anti-sniff + locked-down CSP defense-in-depth headers.
    _login(client)
    with mock.patch('core.media.routes.spaces_service.fetch',
                    return_value=(b'PNGDATA', 'image/png')):
        r = client.get('/api/media/private/logos/co16.png')
    assert r.status_code == 200
    assert r.headers['Content-Type'] == 'image/png'
    assert r.headers.get('X-Content-Type-Options') == 'nosniff'
    csp = r.headers.get('Content-Security-Policy', '')
    assert "default-src 'none'" in csp
    assert 'sandbox' in csp


def test_media_svg_forced_to_download(client):
    # image/svg+xml can carry inline script → must NEVER be served inline
    # from our origin. Force an octet-stream attachment download instead.
    _login(client)
    with mock.patch('core.media.routes.spaces_service.fetch',
                    return_value=(b'<svg onload="alert(1)"/>', 'image/svg+xml')):
        r = client.get('/api/media/private/carpark/18/evil.svg')
    assert r.status_code == 200
    assert r.headers['Content-Type'] == 'application/octet-stream'
    assert 'attachment' in r.headers.get('Content-Disposition', '')
    assert 'evil.svg' in r.headers.get('Content-Disposition', '')
    # Security headers still present on the forced-download path.
    assert r.headers.get('X-Content-Type-Options') == 'nosniff'
    assert "default-src 'none'" in r.headers.get('Content-Security-Policy', '')


def test_media_html_forced_to_download(client):
    # A stored text/html object must not render inline (stored XSS vector).
    _login(client)
    with mock.patch('core.media.routes.spaces_service.fetch',
                    return_value=(b'<script>alert(1)</script>', 'text/html')):
        r = client.get('/api/media/private/carpark/18/evil.html')
    assert r.status_code == 200
    assert r.headers['Content-Type'] == 'application/octet-stream'
    assert 'attachment' in r.headers.get('Content-Disposition', '')


def test_media_404_when_missing(client):
    _login(client)
    with mock.patch('core.media.routes.spaces_service.fetch',
                    side_effect=Exception('NoSuchKey')):
        r = client.get('/api/media/private/carpark/18/99.jpg')
    assert r.status_code == 404
