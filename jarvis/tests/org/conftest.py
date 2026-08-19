"""Seeded Sincron-org fixture for manager_utils tests. localhost/defaultdb only.

Topology:
    company CT (isolated test company)
      users (all company_id=CT): L0, M, A, B, D, X
      company_responsables: (L0, CT)          # L0 sees whole company
      sincron_org_nodes: P (level 1) -> Ch (level 2)
      sincron_org_members: M responsable@P; A,B member@Ch; D member@P;
                           U(unmapped) member@Ch
      X: in company CT but in NO sincron node

    company DZ (SECOND isolated test company; out-of-scope for CT's M/L0)
      user E (company_id=DZ)
      sincron_org_nodes: Z (level 1, company_id=DZ)
      sincron_org_members: E member@Z
"""
import os
import sys
from unittest.mock import MagicMock

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

# ── CI-safe real-psycopg2 bypass + probe (mirrors tests/dept_pulse/conftest.py) ──
# The probe both drops mocked psycopg2* from sys.modules AND mutates the
# already-imported `database` singleton (_db.psycopg2/_db.pool/_db._connection_pool).
# On the failure path (no reachable DB, e.g. CI) BOTH must be restored, or
# `database` is left bound to the real driver with a nulled pool and the next
# get_db() anywhere in the suite raises OperationalError. See dept_pulse's
# _restore_pre_probe_state() — this mirrors it.
REAL_DB_AVAILABLE = False

_MOCK_MODULE_NAMES = ('psycopg2', 'psycopg2.pool', 'psycopg2.extras', 'psycopg2.errors')

# Snapshot the psycopg2* sys.modules entries (root conftest's MagicMocks in CI)
# BEFORE we touch anything, so a failed probe can put them back exactly.
_saved_sys_modules = {name: sys.modules.get(name) for name in _MOCK_MODULE_NAMES}

# Snapshot whether `database` was already imported and, if so, the attrs the
# probe is about to mutate — so the failure path can undo the mutation.
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


def _restore_pre_probe_state():
    """Undo the probe's sys.modules drops AND its `database`-singleton mutation
    so a no-DB run leaves the process exactly as if this conftest never ran."""
    for name in _MOCK_MODULE_NAMES:
        saved = _saved_sys_modules.get(name)
        if saved is not None:
            sys.modules[name] = saved
        else:
            sys.modules.pop(name, None)

    if _db_preexisting:
        _db_mod = sys.modules.get('database')
        if _db_mod is not None and _saved_db_attrs is not None:
            _db_mod.psycopg2 = _saved_db_attrs['psycopg2']
            _db_mod.pool = _saved_db_attrs['pool']
            _db_mod.RealDictCursor = _saved_db_attrs['RealDictCursor']
            _db_mod._connection_pool = _saved_db_attrs['_connection_pool']
    else:
        # `database` was imported by the probe itself and is bound to the real
        # driver — drop it so the next `import database` re-executes cleanly
        # against the just-restored mocks.
        sys.modules.pop('database', None)


def _probe_real_db():
    global REAL_DB_AVAILABLE
    for n in _MOCK_MODULE_NAMES:
        if isinstance(sys.modules.get(n), MagicMock):
            del sys.modules[n]
    try:
        import psycopg2  # noqa: F401  real driver
        import psycopg2.pool, psycopg2.extras, psycopg2.errors  # noqa: F401
        import database as _db
        if isinstance(getattr(_db, 'psycopg2', None), MagicMock) or isinstance(getattr(_db, 'pool', None), MagicMock):
            _db.psycopg2 = sys.modules['psycopg2']
            _db.pool = sys.modules['psycopg2.pool']
            _db._connection_pool = None
        from database import get_db, get_cursor, release_db
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute('SELECT 1')
            cur.fetchone()
            REAL_DB_AVAILABLE = True
        finally:
            release_db(conn)
    except Exception:
        REAL_DB_AVAILABLE = False
        _restore_pre_probe_state()


_probe_real_db()

import pytest
from database import get_db, get_cursor, release_db

_MARK = 'ZZ_ORG_TEST_CO'
_MARK_DZ = 'ZZ_ORG_TEST_DZ'
_MARK_SEED = 'ZZ_SEED_TEST_CO'


@pytest.fixture
def seed_fixture():
    """Isolated company with active sincron_employees carrying a `department`,
    so seed_from_departments() has something to seed. Two employees share
    'Dept Alpha', one is 'Dept Beta'. localhost/defaultdb only.
    """
    if not REAL_DB_AVAILABLE:
        pytest.skip('no real DB available (CI)')
    conn = get_db()
    conn.autocommit = False
    cur = get_cursor(conn)
    ids = {}
    try:
        cur.execute("INSERT INTO companies (company, vat) VALUES (%s, %s) RETURNING id",
                    (_MARK_SEED, 'ZZSEEDTESTVAT'))
        cid = cur.fetchone()['id']
        ids['company_id'] = cid
        ids['company_name'] = _MARK_SEED

        for se_id, dept in (('SEED_1', 'Dept Alpha'), ('SEED_2', 'Dept Alpha'),
                            ('SEED_3', 'Dept Beta')):
            cur.execute("""INSERT INTO sincron_employees
                             (sincron_employee_id, company_name, department,
                              mapped_jarvis_user_id, is_active)
                           VALUES (%s, %s, %s, NULL, TRUE)""", (se_id, _MARK_SEED, dept))
        conn.commit()
        yield ids
    finally:
        cur.execute("DELETE FROM sincron_org_nodes WHERE company_id = %s",
                    (ids.get('company_id'),))  # cascades members
        cur.execute("DELETE FROM sincron_employees WHERE company_name = %s", (_MARK_SEED,))
        cur.execute("DELETE FROM companies WHERE id = %s", (ids.get('company_id'),))
        conn.commit()
        release_db(conn)


@pytest.fixture
def org_fixture():
    if not REAL_DB_AVAILABLE:
        pytest.skip('no real DB available (CI)')
    conn = get_db()
    conn.autocommit = False
    cur = get_cursor(conn)
    ids = {}
    try:
        cur.execute("INSERT INTO companies (company, vat) VALUES (%s, %s) RETURNING id",
                    (_MARK, 'ZZORGTESTVAT'))
        ids['company_id'] = cur.fetchone()['id']
        cid = ids['company_id']

        for key in ('L0', 'M', 'A', 'B', 'D', 'X'):
            cur.execute(
                "INSERT INTO users (name, email, company_id, is_active) VALUES (%s, %s, %s, TRUE) RETURNING id",
                (f'Org {key}', f'org_{key.lower()}@example.invalid', cid),
            )
            ids[f'user_{key}'] = cur.fetchone()['id']

        cur.execute("INSERT INTO company_responsables (user_id, company_id) VALUES (%s, %s)",
                    (ids['user_L0'], cid))

        cur.execute("""INSERT INTO sincron_org_nodes (company_id, parent_id, name, node_type, level)
                       VALUES (%s, NULL, 'Org P', 'department', 1) RETURNING id""", (cid,))
        ids['node_P'] = cur.fetchone()['id']
        cur.execute("""INSERT INTO sincron_org_nodes (company_id, parent_id, name, node_type, level)
                       VALUES (%s, %s, 'Org Ch', 'team', 2) RETURNING id""", (cid, ids['node_P']))
        ids['node_Ch'] = cur.fetchone()['id']

        # sincron_employees mapping (M,A,B,D mapped; U unmapped) + org members
        def emp(se_id, mapped):
            cur.execute("""INSERT INTO sincron_employees
                             (sincron_employee_id, company_name, mapped_jarvis_user_id, is_active)
                           VALUES (%s, %s, %s, TRUE)""", (se_id, _MARK, mapped))

        emp('ORG_M', ids['user_M']); emp('ORG_A', ids['user_A'])
        emp('ORG_B', ids['user_B']); emp('ORG_D', ids['user_D'])
        emp('ORG_U', None)  # unmapped

        def mem(node, se_id, role):
            cur.execute("""INSERT INTO sincron_org_members (node_id, sincron_employee_id, company_name, role)
                           VALUES (%s, %s, %s, %s)""", (node, se_id, _MARK, role))

        mem(ids['node_P'], 'ORG_M', 'responsable')
        mem(ids['node_Ch'], 'ORG_A', 'member')
        mem(ids['node_Ch'], 'ORG_B', 'member')
        mem(ids['node_P'], 'ORG_D', 'member')
        mem(ids['node_Ch'], 'ORG_U', 'member')  # unmapped

        # ── Second isolated company (DZ) — out-of-scope node for CT's M/L0 ──
        cur.execute("INSERT INTO companies (company, vat) VALUES (%s, %s) RETURNING id",
                    (_MARK_DZ, 'ZZORGTESTVATDZ'))
        ids['company_dz'] = cur.fetchone()['id']
        cid_dz = ids['company_dz']

        cur.execute(
            "INSERT INTO users (name, email, company_id, is_active) VALUES (%s, %s, %s, TRUE) RETURNING id",
            ('Org E', 'org_e@example.invalid', cid_dz),
        )
        ids['user_E'] = cur.fetchone()['id']

        cur.execute("""INSERT INTO sincron_employees
                         (sincron_employee_id, company_name, mapped_jarvis_user_id, is_active)
                       VALUES (%s, %s, %s, TRUE)""", ('ORG_E', _MARK_DZ, ids['user_E']))

        cur.execute("""INSERT INTO sincron_org_nodes (company_id, parent_id, name, node_type, level)
                       VALUES (%s, NULL, 'Org Z', 'department', 1) RETURNING id""", (cid_dz,))
        ids['node_Z'] = cur.fetchone()['id']

        cur.execute("""INSERT INTO sincron_org_members (node_id, sincron_employee_id, company_name, role)
                       VALUES (%s, %s, %s, %s)""", (ids['node_Z'], 'ORG_E', _MARK_DZ, 'member'))

        conn.commit()
        yield ids
    finally:
        cur.execute("DELETE FROM sincron_org_nodes WHERE id = %s", (ids.get('node_Z'),))  # cascades its member
        cur.execute("DELETE FROM sincron_employees WHERE company_name = %s", (_MARK_DZ,))
        cur.execute("DELETE FROM users WHERE id = %s", (ids.get('user_E'),))
        cur.execute("DELETE FROM companies WHERE id = %s", (ids.get('company_dz'),))

        cur.execute("DELETE FROM sincron_org_nodes WHERE id IN (%s, %s)",
                    (ids.get('node_Ch'), ids.get('node_P')))  # cascades to members
        cur.execute("DELETE FROM sincron_employees WHERE company_name = %s", (_MARK,))
        cur.execute("DELETE FROM company_responsables WHERE company_id = %s", (ids.get('company_id'),))
        cur.execute("DELETE FROM users WHERE id = ANY(%s)",
                    ([v for k, v in ids.items() if k.startswith('user_') and k != 'user_E'],))
        cur.execute("DELETE FROM companies WHERE id = %s", (ids.get('company_id'),))
        conn.commit()
        release_db(conn)
