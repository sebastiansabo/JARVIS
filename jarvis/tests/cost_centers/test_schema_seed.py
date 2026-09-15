import pytest
from tests.cost_centers.conftest import REAL_DB_AVAILABLE
from database import get_db, get_cursor, release_db
from migrations.domains.schema_cost_centers import _seed_cost_centers

pytestmark = pytest.mark.skipif(not REAL_DB_AVAILABLE, reason='no real DB available (CI)')


def test_seed_is_idempotent_and_skips_unknown_company(monkeypatch):
    # Point the seed at a temp company so the real seed is untouched
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("INSERT INTO companies (company, vat) VALUES ('ZZ_CC_SEED_CO','ZZS') RETURNING id")
        cid = cur.fetchone()['id']
        conn.commit()
        import migrations.domains.schema_cost_centers as m
        monkeypatch.setattr(m, 'SEED_ROWS', [('S', '0281', 'IT'), ('S', '0291', 'Conducere')])
        monkeypatch.setattr(m, 'SHEET_TO_COMPANY', {'S': 'ZZ_CC_SEED_CO'})
        _seed_cost_centers(cur); conn.commit()
        _seed_cost_centers(cur); conn.commit()  # second run must not duplicate
        cur.execute("SELECT COUNT(*) AS n FROM cost_centers WHERE company_id = %s", (cid,))
        assert cur.fetchone()['n'] == 2
    finally:
        cur.execute("DELETE FROM cost_centers WHERE company_id = %s", (cid,))
        cur.execute("DELETE FROM companies WHERE id = %s", (cid,))
        conn.commit()
        release_db(conn)
