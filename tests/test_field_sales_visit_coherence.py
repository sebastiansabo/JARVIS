import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))
from field_sales.repositories.client_fs_repository import ClientFSRepository


def test_get_client_company_id_returns_profile_company():
    repo = ClientFSRepository()
    captured = {}
    def fake_query_one(sql, params):
        captured['sql'] = sql
        captured['params'] = params
        return {'company_id': 20}
    repo.query_one = fake_query_one
    assert repo.get_client_company_id(760) == 20
    assert 'FROM client_profiles' in captured['sql']
    assert 'company_id' in captured['sql']
    assert captured['params'] == (760,)


def test_get_client_company_id_none_when_no_row():
    repo = ClientFSRepository()
    repo.query_one = lambda sql, params: None
    assert repo.get_client_company_id(999) is None


def test_get_client_company_id_none_when_null_company():
    repo = ClientFSRepository()
    repo.query_one = lambda sql, params: {'company_id': None}
    assert repo.get_client_company_id(5) is None
