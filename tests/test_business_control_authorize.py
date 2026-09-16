"""Tests for the JARVIS alpha | BUSINESS CONTROL authorization contract
(multi-tenant).

Endpoints:
- GET  /api/integrations/business-control/authorize        -> authz + available tenants
- POST /api/integrations/business-control/authorize        -> select one tenant (server-verified)
- GET  /api/integrations/business-control/admin/users/<id>/access  -> admin read-only view

Tenant model (uses the existing JARVIS company structure):
- admin (can_access_settings)      -> ALL active companies
- non-admin with the permission    -> ONLY their registered company (users.company_id), if active

Auth gate is the existing `business_control.access` permission (role grant or admin
bypass) — never a hard-coded role name. Company reads come from IntegrationsRepository
(the `companies` table); no parallel membership store.

Follows the repo convention (tests/conftest.py mocks psycopg2); patches
current_user + the repositories the same way tests/test_permissions.py does, so no
live database is required.
"""
import os
import sys
import json
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

_ROUTES = 'core.integrations.routes'
_HELPERS = 'core.utils.api_helpers'


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    from core.integrations import routes as bc
    bc._rate_limiter._requests.clear()
    yield
    bc._rate_limiter._requests.clear()


def _app():
    app = Flask(__name__)
    app.secret_key = 'test'
    return app


def _make_user(**overrides):
    """A fake authenticated principal. Carries sensitive fields so the leak test
    can prove they never reach the response."""
    data = {
        'is_authenticated': True,
        'id': 123,
        'email': 'user@example.com',
        'name': 'Nume Utilizator',
        'role_name': 'Manager',
        'is_active': True,
        'role_id': 7,
        'can_access_settings': False,   # non-admin by default
        'company': 'Autoworld SRL',
        'company_id': 101,
        # sensitive / unrelated — MUST NOT be serialized:
        'password_hash': 'pbkdf2:sha256:SECRET_HASH_DO_NOT_LEAK',
        'cnp': '1900101000000',
        'phone': '+40700000000',
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _repo_mock(companies):
    """companies: list of {'id','company','active'?}. Returns a MagicMock class
    whose instances answer list_active_companies / get_active_company."""
    active = [{'id': c['id'], 'company': c['company']} for c in companies if c.get('active', True)]
    # Mirror the real repository's SQL `ORDER BY company` so tests don't depend on
    # input order.
    active.sort(key=lambda c: c['company'])
    repo_cls = MagicMock()
    inst = repo_cls.return_value
    inst.list_active_companies.return_value = list(active)

    def _get(cid):
        return next((c for c in active if c['id'] == cid), None)
    inst.get_active_company.side_effect = _get
    return repo_cls


def _perm_mock(has_permission):
    repo = MagicMock()
    repo.return_value.check_permission_v2.return_value = {
        'has_permission': has_permission,
        'scope': 'all' if has_permission else 'deny',
    }
    return repo


def _normalize(rv):
    if isinstance(rv, tuple):
        resp, code = rv[0], rv[1]
    else:
        resp, code = rv, rv.status_code
    return code, resp.get_json()


def _call_get(user, has_permission=True, companies=None):
    from core.integrations import routes as bc
    companies = companies if companies is not None else [{'id': 101, 'company': 'Autoworld SRL'}]
    perm, repo = _perm_mock(has_permission), _repo_mock(companies)
    app = _app()
    with app.test_request_context('/api/integrations/business-control/authorize'):
        with patch(f'{_ROUTES}.current_user', user), \
             patch(f'{_ROUTES}.PermissionRepository', perm), \
             patch(f'{_ROUTES}.IntegrationsRepository', repo), \
             patch(f'{_ROUTES}._audit'):
            rv = bc.business_control_authorize()
    return _normalize(rv) + (perm,)


def _call_post(user, body, has_permission=True, companies=None):
    from core.integrations import routes as bc
    companies = companies if companies is not None else [{'id': 101, 'company': 'Autoworld SRL'}]
    perm, repo = _perm_mock(has_permission), _repo_mock(companies)
    app = _app()
    with app.test_request_context(
        '/api/integrations/business-control/authorize', method='POST', json=body
    ):
        with patch(f'{_ROUTES}.current_user', user), \
             patch(f'{_ROUTES}.PermissionRepository', perm), \
             patch(f'{_ROUTES}.IntegrationsRepository', repo), \
             patch(f'{_ROUTES}._audit'):
            rv = bc.business_control_select_tenant()
    return _normalize(rv)


# ═══════════════════════════════ GET — auth gate ═══════════════════════════════

def test_get_unauthenticated_is_401():
    code, body, perm = _call_get(_make_user(is_authenticated=False))
    assert code == 401
    assert body['success'] is False
    perm.return_value.check_permission_v2.assert_not_called()


def test_get_inactive_account_denied():
    code, body, _ = _call_get(_make_user(is_active=False))
    assert code == 403
    assert body['success'] is False
    assert body.get('authorized') is not True


def test_get_missing_permission_forbidden():
    code, body, _ = _call_get(_make_user(role_id=7, can_access_settings=False), has_permission=False)
    assert code == 403
    assert body['success'] is False


def test_get_zero_eligible_companies_forbidden():
    # Has the permission, but the registered company is inactive => no tenants => 403.
    user = _make_user(company_id=101)
    code, body, _ = _call_get(user, has_permission=True,
                              companies=[{'id': 101, 'company': 'Autoworld SRL', 'active': False}])
    assert code == 403
    assert body['success'] is False


# ═══════════════════════════ GET — single tenant (non-admin) ═══════════════════

def test_get_single_tenant_non_admin():
    user = _make_user(role_name='Manager', can_access_settings=False, company_id=101)
    code, body, perm = _call_get(user, has_permission=True,
                                 companies=[{'id': 101, 'company': 'Autoworld SRL'},
                                            {'id': 205, 'company': 'Compania B SRL'}])
    assert code == 200
    assert body['success'] is True
    assert body['authorized'] is True
    assert body['permission'] == 'business_control.access'
    assert body['user'] == {'id': 123, 'email': 'user@example.com',
                            'full_name': 'Nume Utilizator', 'role': 'Manager'}
    # Non-admin sees ONLY their registered company, even though co 205 exists.
    assert body['tenant_selection_required'] is False
    assert body['default_company_id'] == 101
    assert len(body['available_tenants']) == 1
    t = body['available_tenants'][0]
    assert t['company_id'] == 101 and t['is_default'] is True
    assert t['company_name'] == 'Autoworld SRL'
    # permission was actually checked (non-admin path)
    perm.return_value.check_permission_v2.assert_called_once_with(
        7, 'business_control', 'module', 'access')


# ═══════════════════════════ GET — multi tenant (admin) ════════════════════════

def test_get_multi_tenant_admin_sees_all_active():
    admin = _make_user(role_name='Admin', can_access_settings=True, company_id=101)
    code, body, perm = _call_get(admin, has_permission=False,  # admin bypass -> permission not required
                                 companies=[{'id': 101, 'company': 'Autoworld SRL'},
                                            {'id': 205, 'company': 'Compania B SRL'},
                                            {'id': 300, 'company': 'Inactiva SRL', 'active': False}])
    assert code == 200
    assert body['tenant_selection_required'] is True
    ids = {t['company_id'] for t in body['available_tenants']}
    assert ids == {101, 205}            # inactive 300 excluded
    assert body['default_company_id'] == 101   # admin's registered company
    defaults = [t for t in body['available_tenants'] if t['is_default']]
    assert len(defaults) == 1 and defaults[0]['company_id'] == 101
    # admin bypass => no explicit permission lookup
    perm.return_value.check_permission_v2.assert_not_called()


def test_get_admin_with_single_active_company_no_selection():
    admin = _make_user(can_access_settings=True, company_id=101)
    code, body, _ = _call_get(admin, companies=[{'id': 101, 'company': 'Autoworld SRL'}])
    assert code == 200
    assert body['tenant_selection_required'] is False


def test_get_admin_default_falls_back_when_home_company_inactive():
    # Admin registered on an inactive company -> default is the first active company.
    admin = _make_user(can_access_settings=True, company_id=999)
    code, body, _ = _call_get(admin, companies=[{'id': 205, 'company': 'Compania B SRL'},
                                                {'id': 101, 'company': 'Autoworld SRL'}])
    assert code == 200
    # ordered by name -> 'Autoworld SRL'(101) first
    assert body['default_company_id'] == 101


def test_get_superadmin_equiv_is_admin_sees_all():
    # JARVIS has no superuser type; 'superadmin' == admin (can_access_settings).
    admin = _make_user(role_name='Admin', can_access_settings=True, company_id=101)
    code, body, _ = _call_get(admin, has_permission=False,
                              companies=[{'id': 101, 'company': 'A SRL'}, {'id': 205, 'company': 'B SRL'}])
    assert code == 200
    assert {t['company_id'] for t in body['available_tenants']} == {101, 205}


def test_get_company_code_is_derived_from_name():
    user = _make_user(company_id=101)
    _, body, _ = _call_get(user, companies=[{'id': 101, 'company': 'Autoworld SRL'}])
    assert body['available_tenants'][0]['company_code'] == 'AUTOWORLD'


def test_get_role_is_the_jarvis_role_name():
    user = _make_user(role_name='Manager', company_id=101)
    _, body, _ = _call_get(user)
    assert body['user']['role'] == 'Manager'


def test_get_does_not_leak_sensitive_data():
    user = _make_user(company_id=101)
    code, body, _ = _call_get(user)
    assert code == 200
    raw = json.dumps(body).lower()
    for bad in ['secret_hash_do_not_leak', 'password', 'hash', 'pbkdf2', 'token',
                'session', user.cnp, user.phone.lower()]:
        assert bad.lower() not in raw, f'leaked: {bad}'
    assert set(body['user'].keys()) == {'id', 'email', 'full_name', 'role'}


def test_get_bearer_and_session_use_same_current_user_path():
    # The endpoint reads flask_login.current_user, which is populated for BOTH a
    # session cookie AND a Bearer JWT (the global _jwt_session_bridge). So the
    # authorization logic is identical regardless of how the caller authenticated.
    for label in ('session', 'bearer'):
        user = _make_user(company_id=101)
        code, body, _ = _call_get(user)
        assert code == 200, label
        assert body['authorized'] is True


# ═══════════════════════════ POST — tenant selection ═══════════════════════════

def test_post_select_allowed_tenant_non_admin():
    user = _make_user(role_name='Manager', can_access_settings=False, company_id=101)
    code, body = _call_post(user, {'company_id': 101},
                            companies=[{'id': 101, 'company': 'Autoworld SRL'}])
    assert code == 200
    assert body['success'] is True and body['authorized'] is True
    assert body['scope'] == {'tenant_id': 101, 'company_id': 101, 'company': 'Autoworld SRL'}
    assert body['user']['role'] == 'Manager'
    assert body['permission'] == 'business_control.access'


def test_post_select_allowed_tenant_admin():
    admin = _make_user(can_access_settings=True, company_id=101)
    code, body = _call_post(admin, {'company_id': 205}, has_permission=False,
                            companies=[{'id': 101, 'company': 'Autoworld SRL'},
                                       {'id': 205, 'company': 'Compania B SRL'}])
    assert code == 200
    assert body['scope']['company_id'] == 205
    assert body['scope']['tenant_id'] == 205
    assert body['scope']['company'] == 'Compania B SRL'


def test_post_select_disallowed_tenant_is_403_no_leak():
    # Non-admin tries to select a company they are NOT registered on.
    user = _make_user(role_name='Manager', can_access_settings=False, company_id=101)
    code, body = _call_post(user, {'company_id': 205},
                            companies=[{'id': 101, 'company': 'Autoworld SRL'},
                                       {'id': 205, 'company': 'Compania B SRL'}])
    assert code == 403
    assert body == {'success': False, 'authorized': False, 'error': 'Tenant access denied'}
    # no leak about company 205 existing / its name
    assert 'compania b' not in json.dumps(body).lower()


def test_post_select_inactive_company_is_403():
    admin = _make_user(can_access_settings=True, company_id=101)
    code, body = _call_post(admin, {'company_id': 300}, has_permission=False,
                            companies=[{'id': 101, 'company': 'Autoworld SRL'},
                                       {'id': 300, 'company': 'Inactiva SRL', 'active': False}])
    assert code == 403
    assert body['error'] == 'Tenant access denied'


def test_post_cannot_forge_company_id():
    # A company_id that does not exist at all -> denied, no leak.
    user = _make_user(can_access_settings=False, company_id=101)
    code, body = _call_post(user, {'company_id': 999999},
                            companies=[{'id': 101, 'company': 'Autoworld SRL'}])
    assert code == 403
    assert body == {'success': False, 'authorized': False, 'error': 'Tenant access denied'}


def test_post_missing_permission_is_403():
    user = _make_user(can_access_settings=False, company_id=101)
    code, body = _call_post(user, {'company_id': 101}, has_permission=False)
    assert code == 403
    assert body['authorized'] is False


def test_post_inactive_account_is_403():
    user = _make_user(is_active=False, can_access_settings=False, company_id=101)
    code, body = _call_post(user, {'company_id': 101})
    assert code == 403
    assert body['error'] == 'Tenant access denied'


def test_post_unauthenticated_is_401():
    code, body = _call_post(_make_user(is_authenticated=False), {'company_id': 101})
    assert code == 401
    assert body['success'] is False


def test_post_missing_company_id_is_400():
    user = _make_user(company_id=101)
    code, body = _call_post(user, {})
    assert code == 400
    assert body['success'] is False


def test_post_non_integer_company_id_is_400():
    user = _make_user(company_id=101)
    code, body = _call_post(user, {'company_id': 'abc'})
    assert code == 400


# ═══════════════════════════ Admin read-only view ═════════════════════════════

def _call_admin(caller, target_user_data, has_permission=False):
    from core.integrations import routes as bc
    user_repo = MagicMock()
    user_repo.return_value.get_by_id.return_value = target_user_data
    perm = _perm_mock(has_permission)
    app = _app()
    with app.test_request_context('/api/integrations/business-control/admin/users/5/access'):
        with patch(f'{_HELPERS}.current_user', caller), \
             patch(f'{_ROUTES}.current_user', caller), \
             patch(f'{_ROUTES}.UserRepository', user_repo), \
             patch(f'{_ROUTES}.PermissionRepository', perm):
            rv = bc.bc_admin_user_access(5)
    return _normalize(rv)


def test_admin_view_shows_access_and_company():
    caller = _make_user(can_access_settings=True)
    # The real UserRepository.get_by_id does `SELECT u.*` — include sensitive
    # columns to prove the route rebuilds the body from whitelisted keys only.
    target = {'id': 5, 'email': 't@x.com', 'name': 'Ținta', 'role_name': 'Manager',
              'role_id': 7, 'can_access_settings': False, 'company_id': 101, 'company': 'Autoworld SRL',
              'password_hash': 'pbkdf2:sha256:SECRET_HASH_DO_NOT_LEAK', 'cnp': '1900101000000'}
    code, body = _call_admin(caller, target, has_permission=True)
    assert code == 200
    assert body['success'] is True
    assert body['user'] == {'id': 5, 'email': 't@x.com', 'full_name': 'Ținta', 'role': 'Manager'}
    assert body['has_business_control_access'] is True
    assert body['sees_all_companies'] is False
    assert body['registered_company'] == {'company_id': 101, 'company_name': 'Autoworld SRL'}
    raw = json.dumps(body).lower()
    for bad in ['secret_hash_do_not_leak', 'password', 'hash', 'pbkdf2', '1900101000000']:
        assert bad not in raw, f'admin view leaked: {bad}'


def test_admin_view_inactive_caller_denied():
    # A disabled admin holding a live cookie must not reach the enumeration body.
    caller = _make_user(can_access_settings=True, is_active=False)
    target = {'id': 5, 'email': 't@x.com', 'name': 'T', 'role_id': 7, 'company_id': 101}
    code, body = _call_admin(caller, target)
    assert code == 403


def test_admin_view_non_admin_caller_forbidden():
    caller = _make_user(can_access_settings=False)
    target = {'id': 5, 'email': 't@x.com', 'name': 'T', 'role_id': 7, 'company_id': 101}
    code, body = _call_admin(caller, target)
    assert code == 403


def test_admin_view_unauthenticated_401():
    caller = _make_user(is_authenticated=False)
    code, body = _call_admin(caller, {'id': 5})
    assert code == 401


# ═══════════════ Migration seed: default grants (unchanged behavior) ═══════════

class TestBusinessControlSeed:
    """Characterize the permission seed so default grants can't silently drift."""

    def _run_seed(self):
        from migrations.domains import schema_roles
        cursor, conn = MagicMock(), MagicMock()
        schema_roles._seed_business_control_permissions_v2(cursor, conn)
        return cursor, conn

    def _role_grants(self, cursor):
        grants = {}
        for call in cursor.execute.call_args_list:
            sql = call.args[0]
            if 'INSERT INTO role_permissions_v2' in sql and len(call.args) > 1:
                scope, granted, role_name = call.args[1]
                grants[role_name] = (scope, granted)
        return grants

    def test_admin_and_manager_granted_user_viewer_denied(self):
        cursor, _ = self._run_seed()
        grants = self._role_grants(cursor)
        assert grants['Admin'] == ('all', True)
        assert grants['Manager'] == ('all', True)
        assert grants['User'] == ('deny', False)
        assert grants['Viewer'] == ('deny', False)
