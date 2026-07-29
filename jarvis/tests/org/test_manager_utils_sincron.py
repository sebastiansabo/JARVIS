"""manager_utils Sincron repoint — tests. localhost/defaultdb only."""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
import psycopg2  # noqa: F401

from core.organization.manager_utils import is_manager, get_managed_employee_ids, get_visible_tree


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


def test_is_manager_sincron_responsable(org_fixture):
    assert is_manager(org_fixture['user_M']) is True   # responsable @ P


def test_is_manager_l0(org_fixture):
    assert is_manager(org_fixture['user_L0']) is True   # company_responsables


def test_is_manager_plain_member_false(org_fixture):
    assert is_manager(org_fixture['user_A']) is False   # only a member
    assert is_manager(org_fixture['user_X']) is False   # in company, no org node
