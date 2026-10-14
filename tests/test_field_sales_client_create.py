import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))
import pytest


def test_resolve_create_company_non_admin_in_set():
    from field_sales.routes.clients import _resolve_create_company
    assert _resolve_create_company(5, False, {5, 6}, 9) == 5


def test_resolve_create_company_non_admin_forbidden_or_missing_falls_back_home():
    from field_sales.routes.clients import _resolve_create_company
    assert _resolve_create_company(77, False, {5, 6}, 9) == 9    # forbidden → home
    assert _resolve_create_company(None, False, {5, 6}, 9) == 9  # omitted → home


def test_resolve_create_company_admin_passthrough():
    from field_sales.routes.clients import _resolve_create_company
    assert _resolve_create_company(77, True, set(), 9) == 77
    assert _resolve_create_company(None, True, set(), 9) is None


def test_set_profile_company_issues_scoped_update():
    from field_sales.repositories.client_fs_repository import ClientFSRepository
    repo = ClientFSRepository()
    captured = {}
    repo.execute = lambda sql, params: captured.update(sql=sql, params=params)
    repo.set_profile_company(42, 7)
    assert 'UPDATE client_profiles' in captured['sql']
    assert 'company_id = %s' in captured['sql']
    assert captured['params'] == (7, 42)


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


def test_client_create_registered_and_auth_protected(client):
    resp = client.post('/api/field-sales/clients', json={'display_name': 'Test SRL'})
    assert resp.status_code != 404, 'POST /clients should be registered'
    assert resp.status_code in (301, 302, 401, 403), resp.status_code
