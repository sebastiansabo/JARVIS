"""Tests for the independent "Mașini de curtoazie" (courtesy-car) access flag.

The Hub courtesy-car tile used to share the CarPark switch (`can_access_carpark`).
This wires a dedicated `can_access_courtesy` into the `/api/auth/current-user`
payload, resolved by the v2 permission matrix module `courtesy`. Its per-role
grants are seeded to mirror each role's carpark grant (see
`_seed_sidebar_permissions_v2` section 6b), so any role with CarPark today keeps
the courtesy tile until an admin explicitly toggles the new permission — no
regression. The `_access()` closure's `can_access_carpark` fallback additionally
covers the transient pre-migration window.

Mock-based (no real DB) — mirrors jarvis/tests/auth/test_carpark_finance_flag.py:
the top-level jarvis/conftest.py replaces psycopg2 with a MagicMock, and we
stub PermissionRepository.get_module_access_map to control the v2 module map.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

from core.auth.models import User
from core.auth.routes import auth_bp


def _build_app(user_data, module_access_map):
    """A Flask app with auth_bp + a stubbed login returning `user_data`, and a
    PermissionRepository whose get_module_access_map returns `module_access_map`."""
    from flask_login import LoginManager

    app = Flask(__name__)
    app.config['TESTING'] = True
    app.secret_key = 'test-secret'
    app.register_blueprint(auth_bp)

    login_manager = LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def _load_user(user_id):
        return User({'id': int(user_id), 'is_active': True, **user_data})

    return app


@pytest.fixture(autouse=True)
def stub_perm_repo(monkeypatch, request):
    """Each test sets `request.module._MOD_MAP` before building its client."""
    import core.roles.repositories.permission_repository as perm_repo_mod

    class _StubPermRepo:
        def get_module_access_map(self, role_id):
            return getattr(request.module, '_MOD_MAP', {})

        def get_all_role_permissions(self, role_id):
            return {}

        def get_all_role_permission_scopes(self, role_id):
            return {}

    monkeypatch.setattr(perm_repo_mod, 'PermissionRepository', _StubPermRepo)


def _get_payload(app):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = '1'
        sess['_fresh'] = True
    resp = client.get('/api/auth/current-user')
    assert resp.status_code == 200
    return resp.get_json()['user']


def test_courtesy_inherits_carpark_when_no_v2_grant():
    """No `courtesy` row in the module map → falls back to can_access_carpark
    (the transient pre-migration window)."""
    global _MOD_MAP
    _MOD_MAP = {}  # no explicit courtesy grant
    app = _build_app(
        {'email': 'a@b.com', 'name': 'A', 'role_id': 1, 'role_name': 'Admin',
         'can_access_carpark': True},
        _MOD_MAP,
    )
    user = _get_payload(app)
    assert 'can_access_courtesy' in user
    assert user['can_access_courtesy'] is True   # inherited from carpark


def test_courtesy_explicit_grant_overrides_carpark_off():
    """An explicit v2 `courtesy` grant wins even when carpark is off."""
    global _MOD_MAP
    _MOD_MAP = {'courtesy': True}
    app = _build_app(
        {'email': 'a@b.com', 'name': 'A', 'role_id': 2, 'role_name': 'User',
         'can_access_carpark': False},
        _MOD_MAP,
    )
    user = _get_payload(app)
    assert user['can_access_courtesy'] is True


def test_courtesy_false_when_no_carpark_and_no_grant():
    """No carpark and no courtesy grant → tile hidden."""
    global _MOD_MAP
    _MOD_MAP = {}
    app = _build_app(
        {'email': 'a@b.com', 'name': 'A', 'role_id': 3, 'role_name': 'User',
         'can_access_carpark': False},
        _MOD_MAP,
    )
    user = _get_payload(app)
    assert user['can_access_courtesy'] is False


def test_courtesy_explicit_off_while_carpark_on():
    """Admin can revoke courtesy independently: explicit courtesy=False beats
    carpark=True (the whole point of the separate permission)."""
    global _MOD_MAP
    _MOD_MAP = {'courtesy': False}
    app = _build_app(
        {'email': 'a@b.com', 'name': 'A', 'role_id': 4, 'role_name': 'User',
         'can_access_carpark': True},
        _MOD_MAP,
    )
    user = _get_payload(app)
    assert user['can_access_courtesy'] is False
    # driving/carpark itself stays on — proves independence
    assert user['can_access_carpark'] is True
