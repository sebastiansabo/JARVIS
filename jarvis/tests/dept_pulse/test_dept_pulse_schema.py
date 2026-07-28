"""Task 1 — hr_dept_pulse_votes schema. Runs against localhost/defaultdb when a
real Postgres is reachable; skips cleanly under CI's mocked/unreachable DB.

The psycopg2 mock-drop/rebind + real-DB probe now lives centrally in this
package's conftest.py (REAL_DB_AVAILABLE), which also restores the pre-probe
mock state on failure so a no-DB run doesn't leak real-driver bindings into
other test packages collected in the same pytest session. This module just
consults that flag and skips (matching the idiom in
tests/foi_parcurs/test_session_lifecycle_tz.py's `_real_repo_or_skip`).
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from database import get_db, get_cursor, release_db

from .conftest import REAL_DB_AVAILABLE


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
    if not REAL_DB_AVAILABLE:
        pytest.skip(
            'Real Postgres not available (DATABASE_URL unreachable or psycopg2 '
            'mocked) — skipping dept_pulse schema tests'
        )
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
