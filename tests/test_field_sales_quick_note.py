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


def test_quick_note_route_registered_and_auth_protected(client):
    # RED before impl: no such route -> 404 (not in the allowed set) -> fails.
    # GREEN after impl: the auth guard (@jwt_or_login_required/@field_sales_required)
    # rejects the unauthenticated POST with 401/403 or a 302 redirect to login,
    # never 404 (route now exists) and never 200/201 (handler not reached).
    resp = client.post('/api/field-sales/visits/1/quick-note', json={'raw_note': 'x'})
    assert resp.status_code != 404, 'route should be registered'
    assert resp.status_code in (301, 302, 401, 403), resp.status_code
