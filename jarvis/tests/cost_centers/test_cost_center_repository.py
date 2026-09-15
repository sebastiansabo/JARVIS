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


from accounting.cost_centers.repositories.cost_center_repository import CostCenterRepository

_repo = CostCenterRepository()


def test_create_and_list_by_company(cc_fixture):
    cid = cc_fixture['company_id']
    a = _repo.create(cid, '0281', 'IT')
    b = _repo.create(cid, '0291', 'Conducere')
    rows = _repo.list_by_company(cid)
    codes = [r['code'] for r in rows]
    assert codes == ['0281', '0291']            # ordered by code
    assert {r['id'] for r in rows} == {a, b}
    assert all(r['structure_node_id'] is None for r in rows)


def test_duplicate_code_same_company_rejected(cc_fixture):
    cid = cc_fixture['company_id']
    _repo.create(cid, '0281', 'IT')
    with pytest.raises(Exception):
        _repo.create(cid, '0281', 'IT again')   # UNIQUE(company_id, code)


def test_update_and_delete(cc_fixture):
    cid = cc_fixture['company_id']
    cc = _repo.create(cid, '0281', 'IT')
    _repo.update(cc, code=None, name='IT & Systems', active=False)
    row = next(r for r in _repo.list_by_company(cid) if r['id'] == cc)
    assert row['name'] == 'IT & Systems' and row['active'] is False
    _repo.delete(cc)
    assert all(r['id'] != cc for r in _repo.list_by_company(cid))
