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
    # seed_defaults_if_empty() runs at the start of publish/publish-bulk/GET schema
    # and hits the real DB when the map is empty; neutralize it here so route unit
    # tests stay isolated (seeding itself is covered at the repository level).
    monkeypatch.setattr(routes_mod._schema_repo, 'seed_defaults_if_empty', lambda: None)

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
    monkeypatch.setattr(routes_mod._schema_repo, 'get_active_field_map', lambda: [{'target_key': 'marca'}])
    monkeypatch.setattr(routes_mod._schema_repo, 'get_value_map', lambda: {})
    monkeypatch.setattr(routes_mod, '_reconcile_best_effort', lambda client: None)
    monkeypatch.setattr(routes_mod, 'ensure_platform', lambda pub, dom: 3)

    captured = {}
    class FakeConn:
        def __init__(self, *a, **k): pass
        def publish(self, v, p, field_map, value_map, config):
            captured['args'] = (field_map, value_map, config)
            return {'success': True, 'external_id': 'gid://shopify/Product/9',
                    'external_url': 'https://x', 'warnings': []}
    monkeypatch.setattr(routes_mod, 'ShopifyConnector', FakeConn)

    r = client.post('/shopify/api/vehicles/7/publish')
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is True and body['external_id'] == 'gid://shopify/Product/9'
    field_map, value_map, config = captured['args']
    assert field_map == [{'target_key': 'marca'}]
    assert value_map == {}
    assert config == {'vendor': 'Autoworld', 'template_suffix': 'produs_servicii_stoc'}

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


def test_preview_returns_warnings_without_touching_shopify(client, monkeypatch):
    monkeypatch.setattr(routes_mod._repo, 'get_all_by_type',
        lambda t: [{'id': 1, 'connector_type': 'shopify',
                    'config': {'store_domain': 'cb6c17-2.myshopify.com'},
                    'credentials': {'client_id': 'cid', 'client_secret': 'sec'}}])
    monkeypatch.setattr(routes_mod._vehicle_repo, 'get_by_id',
        lambda vid: {'id': vid, 'vin': 'V1', 'brand': 'Audi', 'model': 'RSQ8',
                     'status': 'LISTED', 'current_price': 100000, 'vehicle_type': 'SUV'})
    monkeypatch.setattr(routes_mod._photo_repo, 'get_by_vehicle',
        lambda vid, photo_type=None: [{'url': 'https://cdn/1.jpg', 'is_primary': True, 'sort_order': 0}])
    monkeypatch.setattr(routes_mod._schema_repo, 'get_active_field_map',
        lambda: [{'source_expr': 'co2_emissions', 'target_namespace': 'custom',
                  'target_key': 'emisii_co2', 'target_type': 'single_line_text_field',
                  'transform': 'int', 'is_active': True}])
    monkeypatch.setattr(routes_mod._schema_repo, 'get_value_map', lambda: {})

    def _boom(*a, **k):
        raise AssertionError('preview must not build a client or hit Shopify')
    monkeypatch.setattr(routes_mod, 'ShopifyConnector', _boom)
    monkeypatch.setattr(routes_mod, '_build_client', _boom)

    r = client.get('/shopify/api/vehicles/7/preview')
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is True
    assert body['eligible'] is True
    assert any('emisii_co2' in w for w in body['warnings'])


def test_preview_reports_blocking_reason_when_ineligible(client, monkeypatch):
    monkeypatch.setattr(routes_mod._repo, 'get_all_by_type',
        lambda t: [{'id': 1, 'connector_type': 'shopify',
                    'config': {'store_domain': 'x.myshopify.com'},
                    'credentials': {'client_id': 'c', 'client_secret': 's'}}])
    monkeypatch.setattr(routes_mod._vehicle_repo, 'get_by_id',
        lambda vid: {'id': vid, 'vin': 'V1', 'brand': 'Audi', 'status': 'LISTED',
                     'current_price': 100000})
    monkeypatch.setattr(routes_mod._photo_repo, 'get_by_vehicle', lambda vid, photo_type=None: [])
    r = client.get('/shopify/api/vehicles/7/preview')
    assert r.status_code == 200
    body = r.get_json()
    assert body['eligible'] is False
    assert 'photo' in (body['blocking_reason'] or '').lower()
    assert body['warnings'] == []


def test_preview_forbidden_without_edit_permission(client, monkeypatch):
    class ViewerUser:
        is_authenticated = True; id = 2; company_id = 10
        can_access_carpark = True; can_edit_carpark = False
        can_access_settings = True
    viewer = ViewerUser()
    monkeypatch.setattr(api_helpers, 'current_user', viewer)
    monkeypatch.setattr(routes_mod, 'current_user', viewer)
    r = client.get('/shopify/api/vehicles/7/preview')
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


def test_status_returns_freshness_and_vehicle_updated_at(client, monkeypatch):
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(routes_mod._repo, 'get_all_by_type',
        lambda t: [{'id': 1, 'connector_type': 'shopify',
                    'config': {'store_domain': 'cb6c17-2.myshopify.com'},
                    'credentials': {'client_id': 'cid', 'client_secret': 'sec'}}])
    monkeypatch.setattr(routes_mod._vehicle_repo, 'get_by_id',
        lambda vid: {'id': vid, 'updated_at': now - timedelta(hours=2)})
    monkeypatch.setattr(routes_mod, 'ensure_platform', lambda pub, dom: 3)
    monkeypatch.setattr(routes_mod._pub_repo, 'get_listing_by_vehicle_platform',
        lambda vid, pid: {'external_listing_id': 'gid://shopify/Product/9',
                          'status': 'published', 'last_sync': now - timedelta(hours=1),
                          'expires_at': None})

    r = client.get('/shopify/api/vehicles/7/status')
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is True
    assert body['freshness'] == 'up_to_date'
    assert 'vehicle_updated_at' in body


def test_status_no_account_is_not_published(client, monkeypatch):
    monkeypatch.setattr(routes_mod._repo, 'get_all_by_type', lambda t: [])
    monkeypatch.setattr(routes_mod._vehicle_repo, 'get_by_id', lambda vid: None)

    r = client.get('/shopify/api/vehicles/7/status')
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is True
    assert body['freshness'] == 'not_published'
    assert body['vehicle_updated_at'] is None


def test_get_schema_returns_shape(client, monkeypatch):
    monkeypatch.setattr(routes_mod._repo, 'get_all_by_type',
        lambda t: [{'id': 1, 'connector_type': 'shopify',
                    'config': {'store_domain': 'cb6c17-2.myshopify.com'},
                    'credentials': {'client_id': 'cid', 'client_secret': 'sec'}}])
    monkeypatch.setattr(routes_mod._schema_repo, 'get_field_map',
        lambda: [{'target_namespace': 'custom', 'target_key': 'marca'}])
    monkeypatch.setattr(routes_mod._schema_repo, 'get_value_map', lambda: {'fuel_type': {'Diesel': 'Motorină'}})
    captured = {}

    def fake_reconcile(store_defs, persist=True):
        captured['persist'] = persist
        return {'new': [], 'stale': [], 'type_changed': [], 'ok': 1}
    monkeypatch.setattr(routes_mod._schema_repo, 'reconcile', fake_reconcile)

    class FakeClient:
        def fetch_metafield_definitions(self): return {'custom.marca': 'single_line_text_field'}
    monkeypatch.setattr(routes_mod, '_build_client', lambda connector: FakeClient())

    r = client.get('/shopify/api/schema')
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is True
    for key in ('field_map', 'value_map', 'store_defs', 'drift'):
        assert key in body
    assert body['field_map'] == [{'target_namespace': 'custom', 'target_key': 'marca'}]
    assert body['value_map'] == {'fuel_type': {'Diesel': 'Motorină'}}
    assert body['store_defs'] == {'custom.marca': 'single_line_text_field'}
    assert body['drift'] == {'new': [], 'stale': [], 'type_changed': [], 'ok': 1}
    # GET must not write — reconcile is called with persist=False.
    assert captured['persist'] is False


def test_get_schema_no_account_returns_empty_store_defs(client, monkeypatch):
    monkeypatch.setattr(routes_mod._repo, 'get_all_by_type', lambda t: [])
    monkeypatch.setattr(routes_mod._schema_repo, 'get_field_map', lambda: [])
    monkeypatch.setattr(routes_mod._schema_repo, 'get_value_map', lambda: {})

    r = client.get('/shopify/api/schema')
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is True
    assert body['store_defs'] == {} and body['drift'] == {}


def test_schema_sync_returns_drift(client, monkeypatch):
    monkeypatch.setattr(routes_mod._repo, 'get_all_by_type',
        lambda t: [{'id': 1, 'connector_type': 'shopify',
                    'config': {'store_domain': 'cb6c17-2.myshopify.com'},
                    'credentials': {'client_id': 'cid', 'client_secret': 'sec'}}])

    class FakeClient:
        def fetch_metafield_definitions(self): return {'custom.marca': 'single_line_text_field'}
    monkeypatch.setattr(routes_mod, '_build_client', lambda connector: FakeClient())
    monkeypatch.setattr(routes_mod._schema_repo, 'reconcile',
        lambda store_defs: {'new': [{'namespace': 'custom', 'key': 'nou'}], 'stale': [],
                            'type_changed': [], 'ok': 0})

    r = client.post('/shopify/api/schema/sync')
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is True
    assert body['drift']['new'] == [{'namespace': 'custom', 'key': 'nou'}]


def test_schema_write_forbidden_without_settings(client, monkeypatch):
    class NoSettingsUser:
        is_authenticated = True; id = 3; company_id = 10
        can_access_carpark = True; can_edit_carpark = True
        can_access_settings = False
    user = NoSettingsUser()
    monkeypatch.setattr(api_helpers, 'current_user', user)
    monkeypatch.setattr(routes_mod, 'current_user', user)
    r = client.post('/shopify/api/schema', json={'field_entries': [], 'value_entries': []})
    assert r.status_code == 403


def test_save_schema_upserts_entries(client, monkeypatch):
    saved = {'fields': [], 'values': []}
    monkeypatch.setattr(routes_mod._schema_repo, 'upsert_field',
        lambda source_expr, ns, key, ttype, transform, is_active=True, updated_by=None:
            saved['fields'].append((source_expr, ns, key, ttype, transform, is_active, updated_by)))
    monkeypatch.setattr(routes_mod._schema_repo, 'upsert_value',
        lambda dimension, source_value, ro_value, updated_by=None:
            saved['values'].append((dimension, source_value, ro_value, updated_by)))

    r = client.post('/shopify/api/schema', json={
        'field_entries': [{'source_expr': 'brand', 'target_namespace': 'custom',
                           'target_key': 'marca', 'target_type': 'single_line_text_field',
                           'transform': 'raw'}],
        'value_entries': [{'dimension': 'fuel_type', 'source_value': 'Diesel', 'ro_value': 'Motorină'}],
    })
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is True and body['saved'] == 2
    assert saved['fields'] == [('brand', 'custom', 'marca', 'single_line_text_field', 'raw', True, 1)]
    assert saved['values'] == [('fuel_type', 'Diesel', 'Motorină', 1)]


def test_set_autosync_merges_flag_without_wiping_config(client, monkeypatch):
    account = {'id': 1, 'connector_type': 'shopify', 'name': 'cb6c17-2.myshopify.com',
               'config': {'store_domain': 'cb6c17-2.myshopify.com', 'vendor': 'Autoworld'},
               'credentials': {'client_id': 'cid', 'client_secret': 'sec'}}
    monkeypatch.setattr(routes_mod, '_get_single_account', lambda: account)

    calls = []
    monkeypatch.setattr(routes_mod._repo, 'update',
        lambda account_id, **kwargs: calls.append((account_id, kwargs)))

    r = client.post('/shopify/api/autosync', json={'enabled': False})
    assert r.status_code == 200
    body = r.get_json()
    assert body == {'success': True, 'autosync_enabled': False}

    assert len(calls) == 1
    account_id, kwargs = calls[0]
    assert account_id == 1
    assert kwargs['config']['store_domain'] == 'cb6c17-2.myshopify.com'
    assert kwargs['config']['vendor'] == 'Autoworld'
    assert kwargs['config']['autosync_enabled'] is False
    assert kwargs['credentials'] == {'client_id': 'cid', 'client_secret': 'sec'}
    assert kwargs['name'] == 'cb6c17-2.myshopify.com'


def test_set_autosync_requires_configured_account(client, monkeypatch):
    monkeypatch.setattr(routes_mod, '_get_single_account', lambda: None)
    r = client.post('/shopify/api/autosync', json={'enabled': True})
    assert r.status_code == 400
    assert 'not configured' in r.get_json()['error'].lower()


def test_set_autosync_forbidden_without_settings(client, monkeypatch):
    class NoSettingsUser:
        is_authenticated = True; id = 3; company_id = 10
        can_access_carpark = True; can_edit_carpark = True
        can_access_settings = False
    user = NoSettingsUser()
    monkeypatch.setattr(api_helpers, 'current_user', user)
    monkeypatch.setattr(routes_mod, 'current_user', user)
    r = client.post('/shopify/api/autosync', json={'enabled': True})
    assert r.status_code == 403


def test_safe_account_reports_autosync_enabled_default_true(monkeypatch):
    row = {'id': 1, 'name': 'x', 'config': {'store_domain': 'd.myshopify.com'},
           'credentials': {}, 'status': 'connected', 'last_error': None}
    out = routes_mod._safe_account(row)
    assert out['autosync_enabled'] is True


def test_safe_account_reports_autosync_enabled_false_when_set(monkeypatch):
    row = {'id': 1, 'name': 'x',
           'config': {'store_domain': 'd.myshopify.com', 'autosync_enabled': False},
           'credentials': {}, 'status': 'connected', 'last_error': None}
    out = routes_mod._safe_account(row)
    assert out['autosync_enabled'] is False


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
