"""Seeded Sincron-org fixture for manager_utils tests. localhost/defaultdb only.

Topology:
    company CT (isolated test company)
      users (all company_id=CT): L0, M, A, B, D, X
      company_responsables: (L0, CT)          # L0 sees whole company
      sincron_org_nodes: P (level 1) -> Ch (level 2)
      sincron_org_members: M responsable@P; A,B member@Ch; D member@P;
                           U(unmapped) member@Ch
      X: in company CT but in NO sincron node
"""
import os
import sys
import importlib
from unittest.mock import MagicMock

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

# ── CI-safe real-psycopg2 bypass + probe (mirrors tests/dept_pulse/conftest.py) ──
_SAVED = {}
REAL_DB_AVAILABLE = False


def _restore():
    for name, mod in _SAVED.items():
        if mod is not None:
            sys.modules[name] = mod


def _probe_real_db():
    global REAL_DB_AVAILABLE
    names = ('psycopg2', 'psycopg2.pool', 'psycopg2.extras', 'psycopg2.errors')
    for n in names:
        _SAVED[n] = sys.modules.get(n)
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
        _restore()


_probe_real_db()

import pytest
from database import get_db, get_cursor, release_db

_MARK = 'ZZ_ORG_TEST_CO'


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
        conn.commit()
        yield ids
    finally:
        cur.execute("DELETE FROM sincron_org_nodes WHERE id IN (%s, %s)",
                    (ids.get('node_Ch'), ids.get('node_P')))  # cascades to members
        cur.execute("DELETE FROM sincron_employees WHERE company_name = %s", (_MARK,))
        cur.execute("DELETE FROM company_responsables WHERE company_id = %s", (ids.get('company_id'),))
        cur.execute("DELETE FROM users WHERE id = ANY(%s)",
                    ([v for k, v in ids.items() if k.startswith('user_')],))
        cur.execute("DELETE FROM companies WHERE id = %s", (ids.get('company_id'),))
        conn.commit()
        release_db(conn)
