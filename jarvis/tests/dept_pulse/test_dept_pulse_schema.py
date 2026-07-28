"""Task 1 — hr_dept_pulse_votes schema. Runs against localhost/defaultdb only."""
import os
import sys

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

# jarvis/conftest.py mocks sys.modules['psycopg2'] (and .pool/.extras/.errors)
# at collection time, before this module is ever imported. A plain `import
# psycopg2` here would just re-bind to that already-installed mock, so this
# test — which needs a genuine connection to real localhost Postgres, per its
# purpose — explicitly drops the mock out of sys.modules first, so that both
# this module's own `import psycopg2` and `database`'s internal `import
# psycopg2` (triggered by the `from database import ...` below) resolve to
# the real driver.
#
# This only works because this test file is meant to be run in its own
# pytest invocation (see the module's stated test command), so `database`
# has not yet been imported — and therefore not yet cached with the mock
# bound in — by any other test module in the same process.
from unittest.mock import MagicMock as _ConftestMockType
for _mod_name in ('psycopg2', 'psycopg2.pool', 'psycopg2.extras', 'psycopg2.errors'):
    if isinstance(sys.modules.get(_mod_name), _ConftestMockType):
        del sys.modules[_mod_name]

import psycopg2  # noqa: F401  (real driver now, per the bypass above)
import pytest
from database import get_db, get_cursor, release_db


def _run_migration():
    """Apply the incremental migration (idempotent) so the table exists."""
    from migrations.domains.schema_incremental import create_schema_incremental
    conn = get_db()
    try:
        conn.autocommit = False
        cur = get_cursor(conn)
        create_schema_incremental(conn, cur)
        conn.commit()
    finally:
        release_db(conn)


@pytest.fixture(scope='module', autouse=True)
def ensure_migrated():
    _run_migration()


def test_table_and_columns_exist():
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'hr_dept_pulse_votes'
        """)
        cols = {r['column_name'] for r in cur.fetchall()}
        assert {'id', 'voter_user_id', 'department_node_id',
                'perspective', 'competency_key', 'rating', 'updated_at'} <= cols
    finally:
        release_db(conn)


def test_rating_check_rejects_out_of_range():
    """The CHECK (rating BETWEEN 1 AND 5) must reject 6."""
    from psycopg2.errors import CheckViolation
    conn = get_db()
    try:
        cur = get_cursor(conn)
        # Need a valid FK pair — reuse any existing user + org node, else skip.
        cur.execute("SELECT id FROM users ORDER BY id LIMIT 1")
        u = cur.fetchone()
        cur.execute("SELECT id FROM sincron_org_nodes ORDER BY id LIMIT 1")
        n = cur.fetchone()
        if not u or not n:
            pytest.skip('no seed user/org node available on this DB')
        with pytest.raises(CheckViolation):
            cur.execute("""
                INSERT INTO hr_dept_pulse_votes
                    (voter_user_id, department_node_id, perspective, competency_key, rating)
                VALUES (%s, %s, 'self', 'communication', 6)
            """, (u['id'], n['id']))
        conn.rollback()
    finally:
        release_db(conn)
