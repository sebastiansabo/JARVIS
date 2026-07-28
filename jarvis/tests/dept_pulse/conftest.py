"""Seeded Sincron-org fixture for department-pulse tests. localhost/defaultdb only.

Topology:
    Node P (level 1)  ── responsable: user M
      └─ Node C (level 2, parent=P) ── members: users A, B, C

Eligibility consequences the tests rely on:
  - M (responsable of P) is eligible for P and its descendant C.
  - A/B/C (members of C) are eligible for C only — NOT for parent P.
"""
import os
import sys
from unittest.mock import MagicMock

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

# jarvis/conftest.py installs a MagicMock for psycopg2 (and .pool/.extras/.errors)
# in sys.modules at collection time, before any test module or sub-package
# conftest.py runs. DB-backed dept_pulse tests need the REAL driver. Two steps,
# in order, are required — the second is essential for a FULL-suite run:
#
#   1. Drop the mock modules from sys.modules so a fresh `import psycopg2`
#      resolves the real driver.
#   2. In a full-suite run, an earlier test package imports `database` (which
#      does `import psycopg2` + `from psycopg2 import pool` at its top and lazily
#      builds a module-global `_connection_pool`) BEFORE this package's conftest
#      runs. That already-imported `database` captured the MOCKS into its own
#      namespace (`database.psycopg2` / `database.pool` / `database.RealDictCursor`)
#      and may hold a mock `_connection_pool`. Step 1 alone can't fix that — those
#      are separate references. So rebind them to the real driver and drop the
#      pool, forcing the next get_db() (used by BaseRepository → DeptPulseRepository)
#      to build a real pool against the real DATABASE_URL.
#
# Both steps are gated on isinstance(..., MagicMock) so the whole block is
# idempotent and a strict no-op once the real driver is already bound (isolated
# dept_pulse runs, reruns) — it never disturbs a genuine already-real
# environment or any other suite's modules.
for _mod_name in ('psycopg2', 'psycopg2.pool', 'psycopg2.extras', 'psycopg2.errors'):
    if isinstance(sys.modules.get(_mod_name), MagicMock):
        del sys.modules[_mod_name]

import psycopg2  # noqa: F401  (real driver now, per the bypass above)
import psycopg2.pool  # noqa: F401
from psycopg2.extras import RealDictCursor as _RealDictCursor

# Force an already-imported `database` module off the mocks it captured.
_db = sys.modules.get('database')
if _db is not None and (
    isinstance(getattr(_db, 'psycopg2', None), MagicMock)
    or isinstance(getattr(_db, 'pool', None), MagicMock)
):
    _db.psycopg2 = psycopg2
    _db.pool = psycopg2.pool
    _db.RealDictCursor = _RealDictCursor
    _db._connection_pool = None  # drop mock pool → next get_db() builds a real one

import pytest
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
