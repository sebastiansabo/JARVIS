"""Tests for Task 5.1: wire `can_view_carpark_finance` end-to-end through the
auth pipeline (UserRepository SELECTs -> User model -> /me payload).

Before this fix, the `/api/auth/current-user` ("current user" / "/me")
payload never included `can_view_carpark_finance` because:
  1. UserRepository.get_by_id / get_by_email never selected the column from
     the `roles` join, so it was always absent from user_data.
  2. core.auth.models.User never read it off user_data, so the attribute
     defaulted to False for everyone (including Admin, which has the role
     flag granted in the DB).
  3. core.auth.routes' /api/auth/current-user payload never echoed it back
     to the frontend.

Mock-based (no real DB access), mirroring
jarvis/tests/carpark/test_dispo_routes.py and
jarvis/tests/auth/test_user_json_fields.py: the top-level jarvis/conftest.py
replaces psycopg2 with a MagicMock before database.py is imported, so any
attempt to run real SQL against it returns Mock objects, not rows. Instead we
monkeypatch UserRepository.query_one to capture the SQL text (to prove the
SELECT lists the column) and to return controlled fixture rows (to prove the
User model / route payload reflect it).
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

from core.auth.models import User
from core.auth.repositories.user_repository import UserRepository


# --- 1. User model reads the flag off user_data -----------------------

def test_user_model_reads_can_view_carpark_finance_true():
    user = User({'id': 1, 'email': 'a@b.com', 'name': 'A', 'can_view_carpark_finance': True})
    assert user.can_view_carpark_finance is True


def test_user_model_defaults_can_view_carpark_finance_false_when_absent():
    user = User({'id': 1, 'email': 'a@b.com', 'name': 'A'})
    assert user.can_view_carpark_finance is False


def test_user_model_permission_map_includes_carpark_finance():
    user = User({'id': 1, 'email': 'a@b.com', 'name': 'A', 'can_view_carpark_finance': True})
    assert user.has_permission('carpark.finance') is True
    assert user._permission_map.get('carpark.finance') is True


# --- 2. UserRepository SELECTs actually list the column ----------------

def test_get_by_id_select_lists_can_view_carpark_finance(monkeypatch):
    captured = {}

    def fake_query_one(self, sql, params=None):
        captured['sql'] = sql
        return {'id': 1, 'email': 'a@b.com', 'name': 'A', 'can_view_carpark_finance': True}

    monkeypatch.setattr(UserRepository, 'query_one', fake_query_one)
    repo = UserRepository()
    result = repo.get_by_id(1)

    assert 'r.can_view_carpark_finance' in captured['sql']
    assert result['can_view_carpark_finance'] is True


def test_get_by_email_select_lists_can_view_carpark_finance(monkeypatch):
    captured = {}

    def fake_query_one(self, sql, params=None):
        captured['sql'] = sql
        return {'id': 1, 'email': 'a@b.com', 'name': 'A', 'can_view_carpark_finance': True}

    monkeypatch.setattr(UserRepository, 'query_one', fake_query_one)
    repo = UserRepository()
    result = repo.get_by_email('a@b.com')

    assert 'r.can_view_carpark_finance' in captured['sql']
    assert result['can_view_carpark_finance'] is True


def test_get_by_id_and_get_by_email_selects_stay_in_sync():
    """Both SELECTs enumerate the same can_*_carpark role columns; guard
    against future drift where one gets a new flag and the other doesn't."""
    import inspect
    src = inspect.getsource(UserRepository)
    id_select, email_select = src.split("def get_by_email")
    for col in ('can_access_carpark', 'can_edit_carpark', 'can_delete_carpark',
                'can_access_carpark_mobile', 'can_view_carpark_finance'):
        assert f'r.{col}' in id_select, f'{col} missing from get_by_id SELECT'
        assert f'r.{col}' in email_select, f'{col} missing from get_by_email SELECT'


# --- 3. End-to-end: DB row (simulated) -> User object -> /me payload ---

@pytest.fixture
def app():
    from flask_login import LoginManager
    from core.auth.routes import auth_bp

    app = Flask(__name__)
    app.config['TESTING'] = True
    app.secret_key = 'test-secret'
    app.register_blueprint(auth_bp)

    login_manager = LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def _load_user(user_id):
        # Simulates what UserRepository.get_by_id(...) now returns after
        # the SELECT fix — i.e. a real DB row for an Admin user.
        data = {
            'id': int(user_id), 'email': 'admin@example.com', 'name': 'Admin User',
            'role_id': 1, 'role_name': 'Admin', 'is_active': True,
            'can_view_carpark_finance': True,
        }
        return User(data)

    return app


def test_current_user_payload_includes_can_view_carpark_finance(app, monkeypatch):
    """Log in as a stubbed Admin user and confirm the JSON payload from
    /api/auth/current-user carries can_view_carpark_finance through as
    True (previously always absent/False regardless of role)."""
    import core.roles.repositories.permission_repository as perm_repo_mod

    class _StubPermRepo:
        def get_module_access_map(self, role_id):
            return {}

        def get_all_role_permissions(self, role_id):
            return {}

        def get_all_role_permission_scopes(self, role_id):
            return {}

    monkeypatch.setattr(perm_repo_mod, 'PermissionRepository', _StubPermRepo)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = '1'
        sess['_fresh'] = True

    resp = client.get('/api/auth/current-user')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['authenticated'] is True
    assert 'can_view_carpark_finance' in payload['user']
    assert payload['user']['can_view_carpark_finance'] is True


def test_current_user_payload_reflects_false_when_role_lacks_grant(app, monkeypatch):
    """Sanity check the flag isn't hard-coded True: a non-Admin role without
    the grant must come back False in the same payload path."""
    from flask_login import LoginManager
    from core.auth.routes import auth_bp

    other_app = Flask(__name__)
    other_app.config['TESTING'] = True
    other_app.secret_key = 'test-secret'
    other_app.register_blueprint(auth_bp)

    login_manager = LoginManager()
    login_manager.init_app(other_app)

    @login_manager.user_loader
    def _load_user(user_id):
        data = {
            'id': int(user_id), 'email': 'user@example.com', 'name': 'Regular User',
            'role_id': 3, 'role_name': 'User', 'is_active': True,
            'can_view_carpark_finance': False,
        }
        return User(data)

    import core.roles.repositories.permission_repository as perm_repo_mod

    class _StubPermRepo:
        def get_module_access_map(self, role_id):
            return {}

        def get_all_role_permissions(self, role_id):
            return {}

        def get_all_role_permission_scopes(self, role_id):
            return {}

    monkeypatch.setattr(perm_repo_mod, 'PermissionRepository', _StubPermRepo)

    client = other_app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = '2'
        sess['_fresh'] = True

    resp = client.get('/api/auth/current-user')
    payload = resp.get_json()
    assert payload['user']['can_view_carpark_finance'] is False
