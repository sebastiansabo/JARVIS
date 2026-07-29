"""manager_utils Sincron repoint — tests. localhost/defaultdb only."""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
import psycopg2  # noqa: F401


def test_fixture_seeds_expected_topology(org_fixture):
    from database import get_db, get_cursor, release_db
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("SELECT count(*) AS n FROM sincron_org_members WHERE company_name = 'ZZ_ORG_TEST_CO'")
        assert cur.fetchone()['n'] == 5
        cur.execute("SELECT count(*) AS n FROM users WHERE company_id = %s", (org_fixture['company_id'],))
        assert cur.fetchone()['n'] == 6
    finally:
        release_db(conn)
