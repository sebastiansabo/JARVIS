"""Seeded Sincron-org fixture for department-pulse tests. localhost/defaultdb only.

Topology:
    Node P (level 1)  ── responsable: user M
      └─ Node C (level 2, parent=P) ── members: users A, B, C

Eligibility consequences the tests rely on:
  - M (responsable of P) is eligible for P and its descendant C.
  - A/B/C (members of C) are eligible for C only — NOT for parent P.

CI-safety (final-review fix):
jarvis/conftest.py installs a MagicMock for psycopg2 (and .pool/.extras/.errors)
in sys.modules at collection time so the rest of the suite can run without a
real DB. This package's tests are DB-backed (Task 1/2), so they need the real
driver — but CI (`.github/workflows/ci.yml`) runs `pytest tests/ -x -q` with a
placeholder DATABASE_URL and NO Postgres service container. Blindly dropping
the mock and rebinding `database` to the real driver (as this file used to do,
unconditionally) makes the very first `get_db()` raise
`OperationalError: connection refused` in CI, and with `-x` that halts the
whole run.

The fix, mirroring the skip-guard idiom in
tests/foi_parcurs/test_session_lifecycle_tz.py (`_real_repo_or_skip`):
  1. PROBE once, here, at collection time: attempt the mock-drop/rebind, then
     a real `get_db()` → `SELECT 1` → release. Success sets
     `REAL_DB_AVAILABLE = True`; any failure (refused connection, missing DB,
     still mocked, psycopg2 not importable, ...) sets it False.
  2. On failure, RESTORE the exact sys.modules / `database`-module state that
     existed before we touched anything, so a no-DB run doesn't leave the
     process nudged into "real driver" mode for any other test package
     collected in the same pytest session (rebinding is otherwise
     process-global, since `database` is a singleton module).
  3. DB-dependent tests (this file's `pulse_org` fixture, and
     test_dept_pulse_schema.py's `ensure_migrated` fixture) check
     `REAL_DB_AVAILABLE` and `pytest.skip(...)` when it's False.
     test_dept_pulse_routes.py monkeypatches every repository method and never
     touches the DB, so it does not consult this flag and keeps running.

The probe/restore dance is idempotent: re-running it in the same process (or
in an isolated dept_pulse-only invocation) is a strict no-op once the real
driver is already bound, and a strict no-op restore when nothing was ever
mocked to begin with.
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
    `database` module onto the real driver (see module docstring for why the
    rebind of an already-imported `database` is necessary in a full-suite
    run). Gated on isinstance(..., MagicMock) throughout, so it's a no-op once
    the real driver is already bound.
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
    """Undo `_drop_mocks_and_bind_real_driver()` (and any `database` import
    triggered by the probe itself) so a no-DB run leaves the process exactly
    as it would have been if this package's conftest never ran — no other
    test package collected in the same session gets flipped into
    real-DB-mode.
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
        # `database` was not imported before our probe touched anything, so
        # any `database` module now in sys.modules was imported *by* the
        # probe and is bound to the real driver. Drop it entirely so the next
        # `import database` (by this package or any other) re-executes
        # cleanly against the just-restored mocks.
        sys.modules.pop('database', None)


def _probe_real_db():
    """Attempt the rebind + a real `SELECT 1`. Returns True iff a genuine,
    reachable Postgres answered. On ANY failure — connection refused, DB
    missing, still mocked (defensive: the value check below catches a
    MagicMock row degrading to a non-{'one': 1} result even if the rebind
    somehow didn't take), psycopg2 not importable, etc. — restores the
    pre-probe state and returns False.
    """
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

from database import get_db, get_cursor, release_db

_MARK = 'PULSE_TEST_CO'  # sincron_employees.company_name marker for cleanup


def _ensure_table(cur):
    """Idempotent bootstrap so tests run even on a fresh DB (matches migration)."""
    cur.execute('''
        CREATE TABLE IF NOT EXISTS hr_dept_pulse_votes (
            id SERIAL PRIMARY KEY,
            voter_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            department_node_id INTEGER NOT NULL REFERENCES sincron_org_nodes(id) ON DELETE CASCADE,
            perspective VARCHAR(20) NOT NULL,
            competency_key VARCHAR(40) NOT NULL,
            rating SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE (voter_user_id, department_node_id, perspective, competency_key)
        )
    ''')


@pytest.fixture
def pulse_org():
    if not REAL_DB_AVAILABLE:
        pytest.skip(
            'Real Postgres not available (DATABASE_URL unreachable or psycopg2 '
            'mocked) — skipping dept_pulse DB-backed test'
        )

    conn = get_db()
    conn.autocommit = False
    cur = get_cursor(conn)
    _ensure_table(cur)

    cur.execute("SELECT id FROM companies ORDER BY id LIMIT 1")
    company_id = cur.fetchone()['id']

    ids = {}
    try:
        # 4 throwaway users (users requires only name + unique email)
        for key in ('M', 'A', 'B', 'C'):
            cur.execute(
                "INSERT INTO users (name, email) VALUES (%s, %s) RETURNING id",
                (f'Pulse {key}', f'pulse_{key.lower()}@example.invalid'),
            )
            ids[f'user_{key}'] = cur.fetchone()['id']

        # sincron_employees mapping each user (company_name = marker)
        for key in ('M', 'A', 'B', 'C'):
            cur.execute(
                """INSERT INTO sincron_employees
                       (sincron_employee_id, company_name, mapped_jarvis_user_id, is_active)
                   VALUES (%s, %s, %s, TRUE)""",
                (f'PT_{key}', _MARK, ids[f'user_{key}']),
            )

        # org nodes P (level 1) and C (level 2, child of P)
        cur.execute(
            """INSERT INTO sincron_org_nodes (company_id, parent_id, name, node_type, level)
               VALUES (%s, NULL, 'Pulse P', 'department', 1) RETURNING id""",
            (company_id,),
        )
        ids['node_P'] = cur.fetchone()['id']
        cur.execute(
            """INSERT INTO sincron_org_nodes (company_id, parent_id, name, node_type, level)
               VALUES (%s, %s, 'Pulse C', 'team', 2) RETURNING id""",
            (company_id, ids['node_P']),
        )
        ids['node_C'] = cur.fetchone()['id']

        # members: M responsable of P; A,B,C members of C
        cur.execute(
            """INSERT INTO sincron_org_members (node_id, sincron_employee_id, company_name, role)
               VALUES (%s, 'PT_M', %s, 'responsable')""",
            (ids['node_P'], _MARK),
        )
        for key in ('A', 'B', 'C'):
            cur.execute(
                """INSERT INTO sincron_org_members (node_id, sincron_employee_id, company_name, role)
                   VALUES (%s, %s, %s, 'member')""",
                (ids['node_C'], f'PT_{key}', _MARK),
            )
        conn.commit()
        yield ids
    finally:
        # Teardown — nodes/users cascade to members+votes, but be explicit.
        cur.execute("DELETE FROM hr_dept_pulse_votes WHERE department_node_id IN (%s, %s)",
                    (ids.get('node_C'), ids.get('node_P')))
        cur.execute("DELETE FROM sincron_org_nodes WHERE id IN (%s, %s)",
                    (ids.get('node_C'), ids.get('node_P')))
        cur.execute("DELETE FROM sincron_employees WHERE company_name = %s", (_MARK,))
        cur.execute("DELETE FROM users WHERE id = ANY(%s)",
                    ([v for k, v in ids.items() if k.startswith('user_')],))
        conn.commit()
        release_db(conn)
