"""Email is optional only for Viewer-role users (who then need a phone);
every other role still requires an email. Covers /api/users create + update
validation and the repository's empty-email -> NULL conversion."""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask
from flask_login import LoginManager

from core.auth import auth_bp
from core.auth.models import User
import core.auth.routes as auth_routes


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.secret_key = 'test-secret'
    lm = LoginManager()
    lm.init_app(app)

    @lm.user_loader
    def _load(uid):
        # Admin with settings access — satisfies @admin_required.
        return User({'id': 1, 'email': 'admin@x.com', 'name': 'Admin',
                     'can_access_settings': True, 'is_active': True})

    app.register_blueprint(auth_bp)
    # Mock the ROLE REPO (not _role_is_viewer) so the real _role_is_viewer runs
    # through the route — this exercises the actual RoleRepository method name.
    monkeypatch.setattr(
        auth_routes._role_repo, 'get',
        lambda rid: {'id': rid, 'name': 'Viewer' if str(rid) == '4' else 'Manager'})

    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = '1'
    return c


# ---- create ----

def test_create_viewer_no_email_with_phone_ok(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(auth_routes._user_repo, 'save', lambda **kw: captured.update(kw) or 123)
    r = client.post('/api/users', json={'name': 'V', 'role_id': 4, 'phone': '0728889813'})
    assert r.status_code == 200
    assert r.get_json()['success'] is True
    assert captured['email'] is None            # empty email stored as NULL
    assert captured['phone'] == '0728889813'


def test_create_viewer_no_email_no_phone_rejected(client):
    r = client.post('/api/users', json={'name': 'V', 'role_id': 4})
    assert r.status_code == 400
    assert 'viewer' in r.get_json()['error'].lower()


def test_create_nonviewer_no_email_rejected(client):
    r = client.post('/api/users', json={'name': 'X', 'role_id': 2})
    assert r.status_code == 400
    assert 'email' in r.get_json()['error'].lower()


def test_create_nonviewer_with_email_ok(client, monkeypatch):
    monkeypatch.setattr(auth_routes._user_repo, 'save', lambda **kw: 5)
    r = client.post('/api/users', json={'name': 'X', 'role_id': 2, 'email': 'x@y.com'})
    assert r.status_code == 200


# ---- update ----

def test_update_viewer_clear_email_with_phone_ok(client, monkeypatch):
    monkeypatch.setattr(auth_routes._user_repo, 'get_by_id',
                        lambda uid: {'id': 7, 'role_id': 4, 'email': 'old@x.com', 'phone': '0728889813'})
    seen = {}
    monkeypatch.setattr(auth_routes._user_repo, 'update', lambda **kw: seen.update(kw) or True)
    r = client.put('/api/users/7', json={'name': 'V', 'role_id': 4, 'email': '', 'phone': '0728889813'})
    assert r.status_code == 200
    assert seen['email'] == ''                  # repo layer converts '' -> NULL


def test_update_nonviewer_clear_email_rejected(client, monkeypatch):
    monkeypatch.setattr(auth_routes._user_repo, 'get_by_id',
                        lambda uid: {'id': 8, 'role_id': 2, 'email': 'old@x.com', 'phone': None})
    r = client.put('/api/users/8', json={'name': 'X', 'role_id': 2, 'email': ''})
    assert r.status_code == 400
    assert 'email' in r.get_json()['error'].lower()


# ---- helpers (regression guards) ----

def test_role_is_viewer_uses_real_role_repo(monkeypatch):
    # Must call the real RoleRepository method (.get) — a wrong method name
    # would AttributeError and 500 every /api/users request.
    monkeypatch.setattr(auth_routes._role_repo, 'get',
                        lambda rid: {'id': rid, 'name': 'Viewer'})
    assert auth_routes._role_is_viewer(4) is True
    monkeypatch.setattr(auth_routes._role_repo, 'get',
                        lambda rid: {'id': rid, 'name': 'Admin'})
    assert auth_routes._role_is_viewer(2) is False
    assert auth_routes._role_is_viewer(None) is False


def test_is_superadmin_tolerates_null_email(monkeypatch):
    # A Viewer with email=None must not crash the superadmin check
    # (called on every update/delete/bulk op).
    monkeypatch.setattr(auth_routes._user_repo, 'get_by_id',
                        lambda uid: {'id': uid, 'email': None})
    assert auth_routes._is_superadmin(9) is False


# ---- repository: empty email -> NULL ----

def test_repo_update_blank_email_becomes_null(monkeypatch):
    from core.auth.repositories.user_repository import UserRepository
    repo = UserRepository()
    seen = {}
    monkeypatch.setattr(repo, 'execute', lambda sql, params: seen.update({'params': list(params)}) or 1)
    repo.update(1, email='   ')
    assert None in seen['params']               # blank -> NULL
    assert '   ' not in seen['params']
