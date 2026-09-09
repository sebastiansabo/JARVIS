# jarvis/tests/carpark/test_shopify_routes.py
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
import pytest
from flask import Flask
import core.utils.api_helpers as api_helpers
from carpark.connectors.shopify import shopify_bp
import carpark.connectors.shopify.routes as routes_mod

class FakeUser:
    is_authenticated = True; id = 1; company_id = 10
    can_access_carpark = True; can_edit_carpark = True
    can_access_settings = True

@pytest.fixture(autouse=True)
def _auth(monkeypatch):
    # carpark_edit_required reads current_user from the routes module namespace,
    # while api_login_required reads it from api_helpers — patch BOTH.
    user = FakeUser()
    monkeypatch.setattr(api_helpers, 'current_user', user)
    monkeypatch.setattr(routes_mod, 'current_user', user)

@pytest.fixture
def client():
    app = Flask(__name__); app.register_blueprint(shopify_bp); app.config['TESTING'] = True
    return app.test_client()

def test_config_get_lists_accounts(client, monkeypatch):
    monkeypatch.setattr(routes_mod._repo, 'get_all_by_type', lambda t: [])
    r = client.get('/shopify/api/config')
    assert r.status_code == 200 and r.get_json()['success'] is True

def test_publish_vehicle_calls_connector(client, monkeypatch):
    monkeypatch.setattr(routes_mod._repo, 'get_all_by_type',
        lambda t: [{'id': 1, 'connector_type': 'shopify',
                    'config': {'store_domain': 'cb6c17-2.myshopify.com'},
                    'credentials': {'client_id': 'cid', 'client_secret': 'sec'}}])
    monkeypatch.setattr(routes_mod._vehicle_repo, 'get_by_id',
        lambda vid: {'id': vid, 'vin': 'WBA1234567890XYZ1', 'brand': 'BMW',
                     'status': 'LISTED', 'current_price': 45000, 'vehicle_type': 'Autoturism'})
    monkeypatch.setattr(routes_mod._photo_repo, 'get_by_vehicle',
        lambda vid, photo_type=None: [{'url': 'https://cdn/1.jpg', 'is_primary': True, 'sort_order': 0}])
    monkeypatch.setattr(routes_mod._taxo_repo, 'get_map', lambda: {})
    monkeypatch.setattr(routes_mod, 'ensure_platform', lambda pub, dom: 3)

    class FakeConn:
        def __init__(self, *a, **k): pass
        def publish(self, v, p, m): return {'success': True, 'external_id': 'gid://shopify/Product/9',
                                            'external_url': 'https://x', 'warnings': []}
    monkeypatch.setattr(routes_mod, 'ShopifyConnector', FakeConn)

    r = client.post('/shopify/api/vehicles/7/publish')
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is True and body['external_id'] == 'gid://shopify/Product/9'

def test_publish_requires_configured_account(client, monkeypatch):
    monkeypatch.setattr(routes_mod._repo, 'get_all_by_type', lambda t: [])
    r = client.post('/shopify/api/vehicles/7/publish')
    assert r.status_code == 400
    assert 'not configured' in r.get_json()['error'].lower()

def test_publish_forbidden_without_edit_permission(client, monkeypatch):
    class ViewerUser:
        is_authenticated = True; id = 2; company_id = 10
        can_access_carpark = True; can_edit_carpark = False
        can_access_settings = True
    viewer = ViewerUser()
    monkeypatch.setattr(api_helpers, 'current_user', viewer)
    monkeypatch.setattr(routes_mod, 'current_user', viewer)
    r = client.post('/shopify/api/vehicles/7/publish')
    assert r.status_code == 403


def test_unpublish_vehicle_archives(client, monkeypatch):
    monkeypatch.setattr(routes_mod._repo, 'get_all_by_type',
        lambda t: [{'id': 1, 'connector_type': 'shopify',
                    'config': {'store_domain': 'cb6c17-2.myshopify.com'},
                    'credentials': {'client_id': 'cid', 'client_secret': 'sec'}}])
    monkeypatch.setattr(routes_mod, 'ensure_platform', lambda pub, dom: 3)

    class FakeConn:
        platform_id = 3
        def __init__(self, *a, **k): pass
        def deactivate(self, external_id): return {'success': True}
    monkeypatch.setattr(routes_mod, 'ShopifyConnector', FakeConn)

    monkeypatch.setattr(routes_mod._pub_repo, 'get_listing_by_vehicle_platform',
        lambda vid, pid: {'id': 5, 'external_listing_id': 'gid://shopify/Product/9'})

    calls = []
    class FakePub:
        # positional (listing_id, data) — a kwargs regression like status='archived' TypeErrors.
        def update_listing(self, listing_id, data):
            calls.append((listing_id, data))
    monkeypatch.setattr(routes_mod._pub_repo, 'update_listing', FakePub().update_listing)

    r = client.post('/shopify/api/vehicles/7/unpublish')
    assert r.status_code == 200
    assert calls == [(5, {'status': 'archived'})]


def test_unpublish_forbidden_without_edit_permission(client, monkeypatch):
    class ViewerUser:
        is_authenticated = True; id = 2; company_id = 10
        can_access_carpark = True; can_edit_carpark = False
        can_access_settings = True
    viewer = ViewerUser()
    monkeypatch.setattr(api_helpers, 'current_user', viewer)
    monkeypatch.setattr(routes_mod, 'current_user', viewer)
    r = client.post('/shopify/api/vehicles/7/unpublish')
    assert r.status_code == 403


def test_save_config_forbidden_without_settings(client, monkeypatch):
    class NoSettingsUser:
        is_authenticated = True; id = 3; company_id = 10
        can_access_carpark = True; can_edit_carpark = True
        can_access_settings = False
    user = NoSettingsUser()
    monkeypatch.setattr(api_helpers, 'current_user', user)
    monkeypatch.setattr(routes_mod, 'current_user', user)
    r = client.post('/shopify/api/config', json={'store_domain': 'x.myshopify.com',
                                                 'client_id': 'cid', 'client_secret': 'sec'})
    assert r.status_code == 403


def test_build_client_caches_per_connector(monkeypatch):
    routes_mod._client_cache.clear()
    row = {'id': 42, 'config': {'store_domain': 'd.myshopify.com'},
           'credentials': {'client_id': 'cid', 'client_secret': 'sec1'}}
    c1 = routes_mod._build_client(row)
    c2 = routes_mod._build_client(row)
    assert c1 is c2  # same connector + creds → cached instance reused
    row2 = {'id': 42, 'config': {'store_domain': 'd.myshopify.com'},
            'credentials': {'client_id': 'cid', 'client_secret': 'sec2'}}
    c3 = routes_mod._build_client(row2)
    assert c3 is not c1  # changed secret → fresh client
