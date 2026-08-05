import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))
import pytest


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


def test_edit_client_route_registered_and_auth_protected(client):
    # RED before impl: no such route -> 404 -> excluded by the assertions.
    # GREEN after impl: the auth guard rejects the unauthenticated PUT with
    # 401/403 or a 302 login redirect, never 404 (route exists) or 200.
    resp = client.put('/api/field-sales/clients/1', json={'phone': '0722000000'})
    assert resp.status_code != 404, 'route should be registered'
    assert resp.status_code in (301, 302, 401, 403), resp.status_code
