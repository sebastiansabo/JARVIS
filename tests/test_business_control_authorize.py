"""Tests for the JARVIS alpha | BUSINESS CONTROL authorization contract.

Endpoint: GET /api/integrations/business-control/authorize

Covers every branch of the cross-application authorization contract that lets
JARVIS alpha authenticate users through JARVIS and authorize them through
JARVIS's existing permissions_v2 model:

- authenticated user WITH business_control.access            -> 200 authorized
- authenticated user WITHOUT it                              -> 403
- unauthenticated request                                    -> 401
- inactive / disabled account                                -> denied (403)
- Manager role holding the grant                             -> 200 authorized
- Admin role holding the grant                               -> 200 authorized
- superadmin behavior (explicit decision: JARVIS admin
  bypass is honored — an admin without an explicit grant is
  still authorized, matching JARVIS's documented behavior)   -> 200 authorized
- tenant/company isolation (scope reflects the caller only)
- response never leaks password hashes / secrets / unrelated PII

The suite follows the repo convention (tests/conftest.py mocks psycopg2) and
patches ``current_user`` + ``PermissionRepository`` the same way
tests/test_permissions.py does, so no live database is required.
"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

_ROUTES = 'core.integrations.routes'


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """The endpoint's RateLimiter is module-level (per-worker) state; reset it so
    tests are order-independent."""
    from core.integrations import routes as bc_routes
    bc_routes._rate_limiter._requests.clear()
    yield
    bc_routes._rate_limiter._requests.clear()


def _app():
    app = Flask(__name__)
    app.secret_key = 'test'
    return app


def _make_user(**overrides):
    """Build a fake authenticated principal.

    Deliberately carries sensitive fields (password_hash, cnp, phone, ...) so the
    leak test can prove they never reach the response.
    """
    data = {
        'is_authenticated': True,
        'id': 42,
        'email': 'user@example.com',
        'name': 'Ada Lovelace',
        'is_active': True,
        'role_id': 7,
        'can_access_settings': False,
        'company': 'DWA',
        'company_id': 2,
        # sensitive / unrelated fields that MUST NOT be serialized:
        'password_hash': 'pbkdf2:sha256:SECRET_HASH_DO_NOT_LEAK',
        'cnp': '1900101000000',
        'phone': '+40700000000',
        'brand': 'BT',
        'department': 'Finance',
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _call(user, perm_result=None):
    """Invoke the endpoint with ``current_user`` patched to ``user``.

    ``perm_result`` is what PermissionRepository.check_permission_v2 returns
    (None => the mock is asserted to be never called, e.g. admin bypass paths).
    Returns (status_code, json_body).
    """
    from core.integrations import routes as bc_routes

    perm_repo = MagicMock()
    if perm_result is not None:
        perm_repo.return_value.check_permission_v2.return_value = perm_result

    app = _app()
    with app.test_request_context('/api/integrations/business-control/authorize'):
        with patch(f'{_ROUTES}.current_user', user), \
             patch(f'{_ROUTES}.PermissionRepository', perm_repo), \
             patch(f'{_ROUTES}._audit'):
            rv = bc_routes.business_control_authorize()

    # Normalize Flask return (Response | (Response, status)).
    if isinstance(rv, tuple):
        resp, code = rv[0], rv[1]
    else:
        resp, code = rv, rv.status_code
    return code, resp.get_json(), perm_repo


# ── Core contract ──────────────────────────────────────────────────────────

def test_authenticated_with_permission_is_authorized():
    user = _make_user(role_id=7, can_access_settings=False)
    code, body, _ = _call(user, perm_result={'has_permission': True, 'scope': 'all'})

    assert code == 200
    assert body['authorized'] is True
    assert body['permission'] == 'business_control.access'
    assert body['user'] == {'id': 42, 'email': 'user@example.com', 'full_name': 'Ada Lovelace'}


def test_authenticated_without_permission_is_forbidden():
    user = _make_user(role_id=7, can_access_settings=False)
    code, body, _ = _call(user, perm_result={'has_permission': False, 'scope': 'deny'})

    assert code == 403
    assert body['success'] is False
    assert 'authorized' not in body


def test_unauthenticated_is_401():
    user = _make_user(is_authenticated=False)
    code, body, perm_repo = _call(user, perm_result={'has_permission': True, 'scope': 'all'})

    assert code == 401
    assert body['success'] is False
    # No permission lookup should happen for an unauthenticated caller.
    perm_repo.return_value.check_permission_v2.assert_not_called()


def test_inactive_user_is_denied():
    user = _make_user(is_active=False, role_id=7, can_access_settings=False)
    code, body, _ = _call(user, perm_result={'has_permission': True, 'scope': 'all'})

    # A disabled account is denied even though the role holds the grant.
    assert code == 403
    assert body['success'] is False
    assert body.get('authorized') is not True


# ── Role coverage ──────────────────────────────────────────────────────────

def test_manager_with_permission_is_authorized():
    # Manager is a normal (non-admin) role; authorization must come from the grant.
    manager = _make_user(role_id=3, can_access_settings=False, company_id=5, company='AWH')
    code, body, perm_repo = _call(manager, perm_result={'has_permission': True, 'scope': 'all'})

    assert code == 200
    assert body['authorized'] is True
    perm_repo.return_value.check_permission_v2.assert_called_once_with(
        3, 'business_control', 'module', 'access')


def test_admin_with_permission_is_authorized():
    admin = _make_user(role_id=1, can_access_settings=True)
    code, body, _ = _call(admin, perm_result={'has_permission': True, 'scope': 'all'})

    assert code == 200
    assert body['authorized'] is True


# ── Superadmin behavior (explicit decision) ────────────────────────────────

def test_superadmin_bypass_authorizes_without_explicit_grant():
    """Explicit decision: JARVIS's documented admin bypass is honored.

    An admin (can_access_settings) is authorized even with NO explicit
    business_control.access grant, and the permission lookup is short-circuited.
    """
    admin = _make_user(role_id=1, can_access_settings=True)
    code, body, perm_repo = _call(admin, perm_result={'has_permission': False, 'scope': 'deny'})

    assert code == 200
    assert body['authorized'] is True
    perm_repo.return_value.check_permission_v2.assert_not_called()


def test_non_admin_without_role_is_forbidden():
    user = _make_user(role_id=None, can_access_settings=False)
    code, body, _ = _call(user, perm_result={'has_permission': False, 'scope': 'deny'})

    assert code == 403
    assert body['success'] is False


def test_inactive_admin_is_denied_before_bypass():
    """The active check must run BEFORE the admin bypass: a disabled admin is
    denied and never short-circuits to authorized."""
    admin = _make_user(is_active=False, role_id=1, can_access_settings=True)
    code, body, perm_repo = _call(admin, perm_result={'has_permission': True, 'scope': 'all'})

    assert code == 403
    assert body.get('authorized') is not True
    perm_repo.return_value.check_permission_v2.assert_not_called()


# ── Rate limiting ──────────────────────────────────────────────────────────

def test_rate_limit_returns_429_with_retry_after():
    from core.integrations import routes as bc_routes

    user = _make_user(role_id=7, can_access_settings=False)
    perm_repo = MagicMock()
    perm_repo.return_value.check_permission_v2.return_value = {'has_permission': True, 'scope': 'all'}

    app = _app()
    last = None
    with app.test_request_context('/api/integrations/business-control/authorize'):
        with patch(f'{_ROUTES}.current_user', user), \
             patch(f'{_ROUTES}.PermissionRepository', perm_repo), \
             patch(f'{_ROUTES}._audit'):
            for _ in range(bc_routes._RATE_MAX_REQUESTS + 5):
                last = bc_routes.business_control_authorize()

    # Once the per-principal window budget is exhausted -> 429 with Retry-After.
    assert isinstance(last, tuple)
    resp, code = last[0], last[1]
    assert code == 429
    assert resp.headers.get('Retry-After') is not None


# ── Tenant / company isolation ─────────────────────────────────────────────

def test_scope_reflects_the_calling_user_company_only():
    user_a = _make_user(id=10, email='a@x.com', company_id=1, company='DWA')
    user_b = _make_user(id=20, email='b@x.com', company_id=2, company='AWH')

    _, body_a, _ = _call(user_a, perm_result={'has_permission': True, 'scope': 'all'})
    _, body_b, _ = _call(user_b, perm_result={'has_permission': True, 'scope': 'all'})

    assert body_a['scope']['company_id'] == 1
    assert body_a['scope']['company'] == 'DWA'
    assert body_b['scope']['company_id'] == 2
    assert body_b['scope']['company'] == 'AWH'
    # JARVIS has no tenant tier; the company is the isolation boundary.
    assert body_a['scope']['tenant_id'] is None
    assert body_b['scope']['tenant_id'] is None
    # A caller never sees another company's id.
    assert body_a['scope']['company_id'] != body_b['scope']['company_id']


# ── No sensitive-data leakage ──────────────────────────────────────────────

def test_response_does_not_leak_hashes_secrets_or_unrelated_pii():
    import json

    user = _make_user(role_id=7, can_access_settings=False)
    code, body, _ = _call(user, perm_result={'has_permission': True, 'scope': 'all'})
    assert code == 200

    raw = json.dumps(body).lower()
    for forbidden in [
        'secret_hash_do_not_leak',  # the fake password_hash sentinel
        'password', 'hash', 'pbkdf2', 'secret', 'token', 'session',
        user.cnp,                    # national id
        user.phone.lower(),         # unrelated PII
    ]:
        assert forbidden.lower() not in raw, f'response leaked: {forbidden}'

    # Only the whitelisted fields are present.
    assert set(body.keys()) == {'authorized', 'user', 'scope', 'permission'}
    assert set(body['user'].keys()) == {'id', 'email', 'full_name'}
    assert set(body['scope'].keys()) == {'tenant_id', 'company_id', 'company'}


# ── Migration seed: default role grants (locks the Admin+Manager decision) ──

class TestBusinessControlSeed:
    """Characterize the permission seed so the default grants can't silently drift.

    The security-relevant behavior: Admin + Manager are granted, User + Viewer are
    explicitly denied (not left ungranted, which the sidebar sweep would widen to
    User='own').
    """

    def _run_seed(self):
        from migrations.domains import schema_roles
        cursor, conn = MagicMock(), MagicMock()
        schema_roles._seed_business_control_permissions_v2(cursor, conn)
        return cursor, conn

    def _role_grants(self, cursor):
        """Extract {role_name: (scope, granted)} from the role_permissions_v2 inserts."""
        grants = {}
        for call in cursor.execute.call_args_list:
            sql = call.args[0]
            if 'INSERT INTO role_permissions_v2' in sql and len(call.args) > 1:
                scope, granted, role_name = call.args[1]
                grants[role_name] = (scope, granted)
        return grants

    def test_permission_row_inserted_with_business_control_triple(self):
        cursor, _ = self._run_seed()
        perm_inserts = [
            c.args[0] for c in cursor.execute.call_args_list
            if 'INSERT INTO permissions_v2' in c.args[0]
        ]
        assert len(perm_inserts) == 1
        sql = perm_inserts[0]
        assert "'business_control'" in sql
        assert "'module'" in sql and "'access'" in sql
        assert 'JARVIS alpha | BUSINESS CONTROL' in sql

    def test_admin_and_manager_are_granted(self):
        cursor, _ = self._run_seed()
        grants = self._role_grants(cursor)
        assert grants['Admin'] == ('all', True)
        assert grants['Manager'] == ('all', True)

    def test_user_and_viewer_are_explicitly_denied(self):
        cursor, _ = self._run_seed()
        grants = self._role_grants(cursor)
        # Explicit deny rows (not absent) — this is what blocks the sidebar sweep
        # from widening the permission to User='own'.
        assert grants['User'] == ('deny', False)
        assert grants['Viewer'] == ('deny', False)

    def test_seed_commits(self):
        _, conn = self._run_seed()
        conn.commit.assert_called_once()
