import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))
from field_sales.repositories.client_fs_repository import ClientFSRepository


def _capture(repo):
    """Replace query_all so we can inspect the SQL/params without a DB."""
    calls = {}
    def fake_query_all(sql, params):
        calls['sql'] = sql
        calls['params'] = params
        return []
    repo.query_all = fake_query_all
    return calls


def test_search_clients_no_company_filter_when_none():
    repo = ClientFSRepository()
    calls = _capture(repo)
    repo.search_clients('acme', limit=20, company_ids=None)
    assert 'cp.company_id IN' not in calls['sql']
    assert calls['params'][-1] == 20  # limit is last


def test_search_clients_in_filter_for_id_list():
    repo = ClientFSRepository()
    calls = _capture(repo)
    repo.search_clients('acme', limit=5, company_ids=[10, 20])
    assert 'cp.company_id IN (%s, %s)' in calls['sql']
    assert calls['params'][-3:] == (10, 20, 5)  # ids then limit


def test_search_clients_empty_list_returns_empty_without_querying():
    repo = ClientFSRepository()
    calls = _capture(repo)
    out = repo.search_clients('acme', company_ids=[])
    assert out == []
    assert 'sql' not in calls  # query_all never called
