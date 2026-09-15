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


def test_set_and_clear_map(cc_fixture):
    cid = cc_fixture['company_id']
    cc = _repo.create(cid, '0281', 'IT')
    _repo.set_map(cc, cc_fixture['node_IT'])
    row = next(r for r in _repo.list_by_company(cid) if r['id'] == cc)
    assert row['structure_node_id'] == cc_fixture['node_IT']
    assert row['structure_node_name'] == 'IT'
    _repo.set_map(cc, None)
    row = next(r for r in _repo.list_by_company(cid) if r['id'] == cc)
    assert row['structure_node_id'] is None


def test_auto_seed_map_exact_matches_only(cc_fixture):
    cid = cc_fixture['company_id']
    it = _repo.create(cid, '0281', 'IT')                    # matches node 'IT'
    rep = _repo.create(cid, '0231', 'Reparatii generale VW')  # matches node 'Reparatii generale VW'
    none = _repo.create(cid, '0291', 'Conducere')           # no node -> stays unmapped
    n = _repo.auto_seed_map_exact(cid)
    assert n == 2
    by_id = {r['id']: r for r in _repo.list_by_company(cid)}
    assert by_id[it]['structure_node_id'] == cc_fixture['node_IT']
    assert by_id[rep]['structure_node_id'] == cc_fixture['node_Re']
    assert by_id[none]['structure_node_id'] is None
    assert _repo.auto_seed_map_exact(cid) == 0              # idempotent: nothing new


def test_auto_seed_map_exact_skips_ambiguous(cc_fixture):
    """A cost center whose name matches >1 structure node (case-insensitively) is
    ambiguous and must be SKIPPED silently — it must not raise a CardinalityViolation
    that aborts auto-seed for the whole company, and it must stay unmapped while an
    unambiguous cost center in the same company still gets mapped."""
    cid = cc_fixture['company_id']
    # cc_fixture only seeds unique node names; add a duplicate-named pair here so
    # one cost center matches TWO structure_nodes (LOWER('Marketing')==LOWER('marketing')).
    extra_node_ids = []
    conn = get_db()
    try:
        cur = get_cursor(conn)
        for nm in ('Marketing', 'marketing'):
            cur.execute(
                "INSERT INTO structure_nodes (company_id, parent_id, name, level) "
                "VALUES (%s, NULL, %s, 1) RETURNING id",
                (cid, nm),
            )
            extra_node_ids.append(cur.fetchone()['id'])
        conn.commit()
    finally:
        release_db(conn)

    try:
        amb = _repo.create(cid, '0261', 'Marketing')   # matches TWO nodes -> ambiguous -> skip
        it = _repo.create(cid, '0281', 'IT')           # matches single node 'IT'  -> map
        n = _repo.auto_seed_map_exact(cid)             # must NOT raise despite ambiguity
        assert n == 1
        by_id = {r['id']: r for r in _repo.list_by_company(cid)}
        assert by_id[amb]['structure_node_id'] is None
        assert by_id[it]['structure_node_id'] == cc_fixture['node_IT']
    finally:
        conn2 = get_db()
        try:
            cur2 = get_cursor(conn2)
            cur2.execute("DELETE FROM structure_nodes WHERE id = ANY(%s)", (extra_node_ids,))
            conn2.commit()
        finally:
            release_db(conn2)
