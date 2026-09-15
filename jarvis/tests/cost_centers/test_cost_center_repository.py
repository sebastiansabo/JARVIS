import pytest
from tests.cost_centers.conftest import REAL_DB_AVAILABLE
from database import get_db, get_cursor, release_db

pytestmark = pytest.mark.skipif(not REAL_DB_AVAILABLE, reason='no real DB available (CI)')


def test_cost_center_tables_exist():
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("SELECT to_regclass('public.cost_centers') AS t")
        assert cur.fetchone()['t'] == 'cost_centers'
        cur.execute("SELECT to_regclass('public.cost_center_structure_map') AS t")
        assert cur.fetchone()['t'] == 'cost_center_structure_map'
    finally:
        release_db(conn)
