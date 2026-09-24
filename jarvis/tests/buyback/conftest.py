"""Real-DB probe + Flask client + auth fixtures for buyback backend tests.
localhost/defaultdb only. Task 0 of the buyback backend build: this is the
harness every later buyback task's tests depend on. No buyback product code
is imported here (none exists yet) and no buyback schema is created here —
Task 1 adds a session-scoped `_ensure_buyback_schema` autouse fixture to this
same file.

jarvis/conftest.py installs a MagicMock for psycopg2 (and .pool/.extras/.errors)
in sys.modules at collection time so the rest of the suite can run without a
real DB. Some buyback tests will be DB-backed (exercising real SQL against
buyback repositories), so this package needs the real driver against
localhost/defaultdb when it's reachable.

This mirrors the probe/restore idiom already used by
jarvis/tests/carpark/conftest.py, jarvis/tests/dept_pulse/conftest.py,
jarvis/tests/org/conftest.py and jarvis/tests/cost_centers/conftest.py — the
probe/restore block below is copied VERBATIM from tests/carpark/conftest.py
so the idempotent probe/restore dance stays identical across suites:

  1. PROBE once, here, at collection time: drop the mocked psycopg2* modules
     from sys.modules, rebind the already-imported `database` singleton onto
     the real driver, then attempt a real get_db() -> SELECT 1 -> release.
     Success sets REAL_DB_AVAILABLE = True.
  2. ANY failure (connection refused, DB missing, psycopg2 not importable,
     still mocked, ...) restores the EXACT pre-probe sys.modules/`database`
     state and sets REAL_DB_AVAILABLE = False, so a no-DB run (e.g. CI) isn't
     left with `database` nudged into "real driver" mode with a nulled pool.
  3. DB-backed fixtures/tests check REAL_DB_AVAILABLE and pytest.skip(...)
     when it's False.

The probe/restore dance is idempotent: re-running it in the same process is
a strict no-op once the real driver is already bound (e.g. because another
suite already flipped it), and a strict no-op restore when nothing was ever
mocked to begin with.
"""
import os
import sys
from unittest.mock import MagicMock

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest  # noqa: E402

_MOCK_MODULE_NAMES = ('psycopg2', 'psycopg2.pool', 'psycopg2.extras', 'psycopg2.errors')

# Snapshot exactly what's in sys.modules for these names *before* we touch
# anything (the root conftest.py's MagicMocks, in the common case) so a
# failed probe can put things back exactly as they were.
_saved_sys_modules = {name: sys.modules.get(name) for name in _MOCK_MODULE_NAMES}

# Snapshot whether `database` was already imported, and if so, the attributes
# it captured at its own import time (possibly mocks, possibly already-real).
_db_preexisting = 'database' in sys.modules
_saved_db_attrs = None
if _db_preexisting:
    _db_mod = sys.modules['database']
    _saved_db_attrs = {
        'psycopg2': getattr(_db_mod, 'psycopg2', None),
        'pool': getattr(_db_mod, 'pool', None),
        'RealDictCursor': getattr(_db_mod, 'RealDictCursor', None),
        '_connection_pool': getattr(_db_mod, '_connection_pool', None),
    }


def _drop_mocks_and_bind_real_driver():
    """Drop mocked psycopg2* from sys.modules and rebind an already-imported
    `database` module onto the real driver. Gated on isinstance(..., MagicMock)
    throughout, so it's a no-op once the real driver is already bound.
    """
    for _name in _MOCK_MODULE_NAMES:
        if isinstance(sys.modules.get(_name), MagicMock):
            del sys.modules[_name]

    import psycopg2 as _psycopg2
    import psycopg2.pool as _psycopg2_pool
    from psycopg2.extras import RealDictCursor as _RealDictCursor

    _db_mod = sys.modules.get('database')
    if _db_mod is not None and (
        isinstance(getattr(_db_mod, 'psycopg2', None), MagicMock)
        or isinstance(getattr(_db_mod, 'pool', None), MagicMock)
    ):
        _db_mod.psycopg2 = _psycopg2
        _db_mod.pool = _psycopg2_pool
        _db_mod.RealDictCursor = _RealDictCursor
        _db_mod._connection_pool = None  # drop mock pool -> next get_db() builds a real one


def _restore_pre_probe_state():
    """Undo _drop_mocks_and_bind_real_driver() (and any `database` import
    triggered by the probe itself) so a no-DB run leaves the process exactly
    as it would have been if this conftest never ran.
    """
    for _name in _MOCK_MODULE_NAMES:
        _saved = _saved_sys_modules.get(_name)
        if _saved is not None:
            sys.modules[_name] = _saved
        else:
            sys.modules.pop(_name, None)

    if _db_preexisting:
        _db_mod = sys.modules.get('database')
        if _db_mod is not None and _saved_db_attrs is not None:
            _db_mod.psycopg2 = _saved_db_attrs['psycopg2']
            _db_mod.pool = _saved_db_attrs['pool']
            _db_mod.RealDictCursor = _saved_db_attrs['RealDictCursor']
            _db_mod._connection_pool = _saved_db_attrs['_connection_pool']
    else:
        sys.modules.pop('database', None)


def _probe_real_db():
    try:
        _drop_mocks_and_bind_real_driver()
        from database import get_db, get_cursor, release_db
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute('SELECT 1 AS one')
            row = cur.fetchone()
            if not row or row.get('one') != 1:
                raise RuntimeError('probe query did not return a real row (mocked cursor?)')
        finally:
            release_db(conn)
        return True
    except Exception:
        _restore_pre_probe_state()
        return False


REAL_DB_AVAILABLE = _probe_real_db()

from database import get_db, get_cursor, release_db  # noqa: E402


@pytest.fixture
def require_real_db():
    """Skip the test if no real Postgres connection is available."""
    if not REAL_DB_AVAILABLE:
        pytest.skip(
            'Real Postgres not available (DATABASE_URL unreachable or psycopg2 '
            'mocked) — skipping buyback DB-backed test'
        )


# ---------------------------------------------------------------------------
# Flask test client
# ---------------------------------------------------------------------------

# Imported at module scope (mirrors tests/carpark/test_finance_gate.py /
# test_company_scope.py and tests/cost_centers/test_routes.py): this is the
# module-level `app` instance created at app.py import time
# (`app = create_app()`), not a fresh app built per-test. By the time this
# import runs, the probe above has already dropped any mocked psycopg2*
# modules from sys.modules (when a real DB was reachable), so app.py's own
# `from database import ...` chain binds to the real driver too.
import app as _app_module  # noqa: E402
from app import app as flask_app  # noqa: E402


@pytest.fixture
def client():
    """Flask test client for the real app (`from app import app`)."""
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Auth fixture: as_role(role_name, company_id=None)
# ---------------------------------------------------------------------------

import itertools  # noqa: E402

# Fresh uid per as_role() call, drawn from a block not claimed by any other
# suite's hardcoded login uids (tests/carpark uses 90000-96004, 990001+;
# tests/cost_centers etc use other 6-digit blocks) — app.py's Flask-Login
# user_loader caches loaded User objects per-process for 60s, keyed by
# int(user_id) (see tests/carpark/test_finance_gate.py's module docstring),
# so reusing a uid claimed elsewhere in the same pytest run could silently
# read a stale cached user instead of the one this fixture just registered.
_uid_counter = itertools.count(980001)


@pytest.fixture
def as_role(client, monkeypatch):
    """Log a user into `client`'s session so `@login_required` and
    `@v2_permission_required` (core/roles/decorators.py) pass.

    Returns a callable `as_role(role_name, company_id=None) -> uid`:

      as_role('Admin')                     # admin bypass: g.permission_scope = 'all'
      as_role('User', company_id=42)       # non-admin role scoped to company_id=42

    `role_name` is looked up (get-or-create) against the REAL `roles` table
    so `role_id` is genuine and `PermissionRepository.check_permission_v2`
    resolves against real `role_permissions_v2` rows a later task may seed
    for the buyback module. The role row's legacy boolean permission columns
    (can_access_settings, can_add_invoices, ...) seed the fake user dict
    directly, so e.g. the seeded 'Admin' role (can_access_settings=TRUE)
    naturally trips the admin bypass in v2_permission_required:

        if getattr(current_user, 'is_admin', False) or \\
           getattr(current_user, 'can_access_settings', False):
            g.permission_scope = 'all'

    Each call mints its own uid and patches `app._user_repo.get_by_id` to
    resolve any uid registered so far (a dict keyed by uid, not a single
    fixed user), so multiple as_role() calls in one test — e.g. logging in
    as two different companies' users to probe cross-company IDOR — resolve
    to the right user for whichever session cookie is active for that
    request. Mirrors the `_login(client, monkeypatch, uid, ...)` helper
    pattern in tests/carpark/test_finance_gate.py and
    tests/carpark/test_company_scope.py, generalized to accept a role name
    + company_id instead of hardcoded boolean kwargs.

    Skips the test if no real Postgres connection is available.
    """
    if not REAL_DB_AVAILABLE:
        pytest.skip(
            'Real Postgres not available (DATABASE_URL unreachable or psycopg2 '
            'mocked) — skipping buyback DB-backed test'
        )

    _users_by_uid = {}
    monkeypatch.setattr(
        _app_module._user_repo, 'get_by_id',
        lambda uid: _users_by_uid.get(int(uid))
    )

    def _get_or_create_role(role_name):
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute('SELECT * FROM roles WHERE name = %s', (role_name,))
            role = cur.fetchone()
            if role is None:
                cur.execute(
                    "INSERT INTO roles (name, description) VALUES (%s, %s) "
                    "ON CONFLICT (name) DO NOTHING",
                    (role_name, f'buyback test harness role: {role_name}')
                )
                conn.commit()
                cur.execute('SELECT * FROM roles WHERE name = %s', (role_name,))
                role = cur.fetchone()
            return dict(role)
        finally:
            release_db(conn)

    def _as_role(role_name, company_id=None):
        role = _get_or_create_role(role_name)
        uid = next(_uid_counter)

        user = dict(role)
        user.pop('name', None)
        user.pop('description', None)
        user.pop('created_at', None)
        user['id'] = uid
        user['email'] = f'buyback-harness-{uid}@x.com'
        user['name'] = f'Buyback Test {role_name} {uid}'
        user['role_id'] = role['id']
        user['role_name'] = role_name
        user['company_id'] = company_id
        user['is_active'] = True

        _users_by_uid[uid] = user

        with client.session_transaction() as sess:
            sess['_user_id'] = str(uid)

        return uid

    return _as_role
