"""Real-DB harness for the consent-documents-gate schema tests. localhost/defaultdb only.

jarvis/conftest.py installs a MagicMock for psycopg2 (and .pool/.extras/.errors)
in sys.modules at collection time so the rest of the suite can run without a
real DB. This package's tests are DB-backed (Task 1), so they need the real
driver — but CI (`.github/workflows/ci.yml`) runs the suite with a placeholder
DATABASE_URL and NO Postgres service container. Blindly dropping the mock and
rebinding `database` to the real driver unconditionally would make the very
first `get_db()` raise `OperationalError: connection refused` in CI.

The fix, mirroring the idiom in jarvis/tests/dept_pulse/conftest.py,
jarvis/tests/org/conftest.py and jarvis/tests/hr_events/conftest.py
(itself modeled on tests/foi_parcurs/test_session_lifecycle_tz.py's
`_real_repo_or_skip`):
  1. PROBE once, here, at collection time: attempt the mock-drop/rebind, then
     a real `get_db()` → `SELECT 1` → release. Success sets
     `REAL_DB_AVAILABLE = True`; any failure (refused connection, missing DB,
     still mocked, psycopg2 not importable, ...) sets it False.
  2. On failure, RESTORE the exact sys.modules / `database`-module state that
     existed before we touched anything, so a no-DB run doesn't leave the
     process nudged into "real driver" mode for any other test package
     collected in the same pytest session (rebinding is otherwise
     process-global, since `database` is a singleton module).
  3. test_consent_schema.py's `ensure_migrated` fixture checks
     `REAL_DB_AVAILABLE` and `pytest.skip(...)` when it's False.
"""
import os
import sys
from unittest.mock import MagicMock

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest

_MOCK_MODULE_NAMES = ('psycopg2', 'psycopg2.pool', 'psycopg2.extras', 'psycopg2.errors')

# Snapshot exactly what's in sys.modules for these names *before* we touch
# anything (the root conftest.py's MagicMocks, in the common case) so a failed
# probe can put things back exactly as they were.
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
        _db_mod._connection_pool = None  # drop mock pool → next get_db() builds a real one


def _restore_pre_probe_state():
    """Undo `_drop_mocks_and_bind_real_driver()` so a no-DB run leaves the
    process exactly as it would have been if this package's conftest never
    ran — no other test package collected in the same session gets flipped
    into real-DB-mode.
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
