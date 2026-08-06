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


# =============================================================================
# Task 2: Endpoint scope enforcement
# =============================================================================

import pytest
from field_sales.routes.clients import _resolve_search_company_ids


@pytest.mark.parametrize('is_admin,requested,allowed,expected', [
    (True, 5, set(), [5]),            # admin + id -> that tenant
    (True, None, set(), None),        # admin + omitted -> all tenants
    (False, 10, {10, 20}, [10]),      # non-admin + in-set id -> narrow
    (False, 99, {10, 20}, [10, 20]),  # non-admin + forbidden id -> allowed set
    (False, None, {10, 20}, [10, 20]),# non-admin + omitted -> allowed set
    (False, 10, set(), []),           # non-admin + no allowed -> []
])
def test_resolve_search_company_ids(is_admin, requested, allowed, expected):
    assert _resolve_search_company_ids(is_admin, requested, allowed) == expected


# Registration/auth: the endpoint must reject an unauthenticated request.
@pytest.fixture(scope='module')
def app():
    from core.config import AppConfig
    from app import create_app
    cfg = AppConfig(
        secret_key='test-secret-key-for-tests',
        database_url=os.environ.get('DATABASE_URL', 'postgresql://test:test@localhost/test'),
    )
    application = create_app(cfg)
    application.config['TESTING'] = True
    application.config['WTF_CSRF_ENABLED'] = False
    return application


@pytest.fixture(scope='module')
def client(app):
    return app.test_client()


def test_client_search_route_auth_protected(client):
    resp = client.get('/api/field-sales/clients/search?q=acme')
    assert resp.status_code != 404, 'route should be registered'
    assert resp.status_code in (301, 302, 401, 403), resp.status_code
