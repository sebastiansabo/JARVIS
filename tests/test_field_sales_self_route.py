import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))
import pytest


def test_resolve_stop_companies_tags_in_set_and_drops_companyless():
    from field_sales.routes.visits import _resolve_stop_companies
    stops = [{'client_id': 10, 'company_id': 999}, {'client_id': 11}]
    lookup = {10: 20, 11: None}.get
    forbidden = _resolve_stop_companies(stops, False, {20}, lookup)
    assert forbidden is None
    assert stops[0]['company_id'] == 20          # client's company overrides the request's 999
    assert 'company_id' not in stops[1]          # companyless client → key dropped


def test_resolve_stop_companies_blocks_forbidden_client():
    from field_sales.routes.visits import _resolve_stop_companies
    stops = [{'client_id': 10}, {'client_id': 11}]
    lookup = {10: 20, 11: 77}.get
    assert _resolve_stop_companies(stops, False, {20}, lookup) == 1   # stop index 1 is out-of-tenant


def test_resolve_stop_companies_admin_bypasses_gate():
    from field_sales.routes.visits import _resolve_stop_companies
    stops = [{'client_id': 10}]
    lookup = {10: 77}.get
    assert _resolve_stop_companies(stops, True, set(), lookup) is None
    assert stops[0]['company_id'] == 77


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


def test_self_route_registered_and_auth_protected(client):
    resp = client.post('/api/field-sales/routes/mine',
                       json={'planned_date': '2026-10-20', 'stops': [{'client_id': 1}]})
    assert resp.status_code != 404, 'routes/mine should be registered'
    assert resp.status_code in (301, 302, 401, 403), resp.status_code
