"""Tests for the mobile `_user_json` serializer (Task 4.1):

- New flags: is_superuser, can_access_vouchers, can_access_facturare,
  can_access_controlling, can_access_test_drive
- New mobile-unique route /api/mobile/current-user (+ its OPTIONS preflight)

Mocks `PermissionRepository` at the module level where it's imported inside
`_user_json` (same approach as test_mobile_login_otp.py), to avoid hitting
the real DB.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

import core.mobile.routes._shared as shared_mod
import core.roles.repositories.permission_repository as perm_repo_mod


class FakeUser:
    """Minimal stand-in matching the subset of core.auth.models.User used by _user_json."""

    def __init__(self, **overrides):
        self.id = overrides.get('id', 1)
        self.name = overrides.get('name', 'Test User')
        self.email = overrides.get('email', 'user@example.com')
        self.phone = overrides.get('phone')
        self.company = overrides.get('company')
        self.department = overrides.get('department')
        self.role_name = overrides.get('role_name', 'Admin')
        self.role_id = overrides.get('role_id', 7)
        self.is_hr_manager = overrides.get('is_hr_manager', False)
        self.is_superuser = overrides.get('is_superuser', False)


class FakePermRepo:
    """Stand-in for PermissionRepository used inside _user_json / _current_user."""

    def __init__(self, mod_access=None, mob_access=None, has_view_perm=False):
        self._mod_access = mod_access if mod_access is not None else {
            'vouchers': True,
            'facturare': False,
            'controlling': True,
            'test_drive': True,
        }
        self._mob_access = mob_access or {}
        self._has_view_perm = has_view_perm

    def get_module_access_map(self, role_id):
        return self._mod_access

    def get_mobile_access_map(self, role_id):
        return self._mob_access

    def check_permission_v2(self, role_id, module, entity, action):
        return {'has_permission': self._has_view_perm}


@pytest.fixture(autouse=True)
def patch_perm_repo(monkeypatch):
    monkeypatch.setattr(perm_repo_mod, 'PermissionRepository', FakePermRepo)


def test_user_json_includes_new_flags_with_correct_types():
    user = FakeUser(is_superuser=True)
    result = shared_mod._user_json(user)

    assert 'is_superuser' in result
    assert 'can_access_vouchers' in result
    assert 'can_access_facturare' in result
    assert 'can_access_controlling' in result
    assert 'can_access_test_drive' in result

    assert result['is_superuser'] is True
    assert result['can_access_vouchers'] is True
    assert result['can_access_facturare'] is False
    assert result['can_access_controlling'] is True
    assert result['can_access_test_drive'] is True
    assert isinstance(result['can_access_test_drive'], bool)

    # Mobile first-login bypass fix: EVERY auth response (token/verify-otp/
    # refresh) serializes through _user_json, so both consent-gate keys must
    # ride along here too. Under this test's mocked psycopg2 the real
    # get_status() can't query, so it degrades to the dormant default
    # (complete=True / 0) — the point of this assertion is that the keys are
    # always present with the right primitive types (never `undefined` on the
    # mobile store). See test_consent_user_json.py for the real-value flow.
    assert 'consents_complete' in result
    assert 'pending_consents_count' in result
    assert isinstance(result['consents_complete'], bool)
    assert isinstance(result['pending_consents_count'], int)


def test_user_json_is_superuser_defaults_false_when_absent():
    """If the User instance has no is_superuser attribute at all, it must
    default to False rather than raising."""
    user = FakeUser()
    del user.is_superuser
    result = shared_mod._user_json(user)
    assert result['is_superuser'] is False


def test_user_json_module_flags_fallback_to_false_when_module_absent():
    """vouchers/facturare/controlling/test_drive have no legacy attr fallback (None),
    so an absent module-access-map entry must resolve to False."""
    user = FakeUser()
    with_empty_map = FakePermRepo(mod_access={})
    import core.roles.repositories.permission_repository as m
    m.PermissionRepository = lambda: with_empty_map
    try:
        result = shared_mod._user_json(user)
    finally:
        m.PermissionRepository = FakePermRepo

    assert result['can_access_vouchers'] is False
    assert result['can_access_facturare'] is False
    assert result['can_access_controlling'] is False
    assert result['can_access_test_drive'] is False


# ============== Route registration smoke test ==============

@pytest.fixture
def app():
    from core.mobile import mobile_bp
    # Ensure auth.py routes (including the new v2 route) are registered on
    # the blueprint before we build the app.
    import core.mobile.routes.auth  # noqa: F401
    app = Flask(__name__)
    app.register_blueprint(mobile_bp)
    app.config['TESTING'] = True
    return app


def test_mobile_current_user_v2_route_registered(app):
    rules = {r.rule: r.methods for r in app.url_map.iter_rules()}
    assert '/api/mobile/current-user' in rules
    assert 'GET' in rules['/api/mobile/current-user']


def test_mobile_current_user_v2_options_registered(app):
    client = app.test_client()
    resp = client.options('/api/mobile/current-user')
    assert resp.status_code == 204


def test_mobile_current_user_v2_requires_jwt(app):
    client = app.test_client()
    resp = client.get('/api/mobile/current-user')
    assert resp.status_code == 401


def test_legacy_current_user_route_unchanged(app):
    """Task 4.1 must not alter existing /api/auth/current-user behavior."""
    rules = {r.rule: r.methods for r in app.url_map.iter_rules()}
    assert '/api/auth/current-user' in rules
    client = app.test_client()
    resp = client.get('/api/auth/current-user')
    assert resp.status_code == 401
