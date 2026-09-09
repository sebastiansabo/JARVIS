import pytest
from carpark.connectors.shopify.client import ShopifyClient, ShopifyAuthError

class _Resp:
    def __init__(self, status, payload):
        self.status_code = status; self._p = payload
    def json(self): return self._p
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(f'HTTP {self.status_code}')

def test_get_token_caches_and_refreshes(monkeypatch):
    calls = []
    def fake_post(url, data=None, headers=None, timeout=None):
        calls.append(url)
        return _Resp(200, {'access_token': 'shpat_x', 'scope': 'write_products', 'expires_in': 86399})
    monkeypatch.setattr('carpark.connectors.shopify.client.requests.post', fake_post)
    c = ShopifyClient('cb6c17-2.myshopify.com', 'cid', 'shpss_sec')
    assert c._get_token() == 'shpat_x'
    assert c._get_token() == 'shpat_x'          # cached — no 2nd HTTP call
    assert len(calls) == 1
    assert calls[0] == 'https://cb6c17-2.myshopify.com/admin/oauth/access_token'

def test_get_token_error_raises(monkeypatch):
    def fake_post(url, data=None, headers=None, timeout=None):
        return _Resp(400, {'error': 'invalid_client', 'error_description': 'bad secret'})
    monkeypatch.setattr('carpark.connectors.shopify.client.requests.post', fake_post)
    c = ShopifyClient('cb6c17-2.myshopify.com', 'cid', 'bad')
    with pytest.raises(ShopifyAuthError):
        c._get_token()


def test_graphql_retries_on_throttled(monkeypatch):
    # Shopify returns HTTP 200 with a THROTTLED error; the client should retry and succeed.
    monkeypatch.setattr('carpark.connectors.shopify.client.time.sleep', lambda s: None)
    calls = {'n': 0}
    def fake_post(url, json=None, headers=None, timeout=None):
        calls['n'] += 1
        if calls['n'] == 1:
            return _Resp(200, {'errors': [{'message': 'Throttled',
                                           'extensions': {'code': 'THROTTLED'}}]})
        return _Resp(200, {'data': {'shop': {'name': 'Autoworld.ro'}}})
    monkeypatch.setattr('carpark.connectors.shopify.client.requests.post', fake_post)
    c = ShopifyClient('cb6c17-2.myshopify.com', 'cid', 'sec')
    c._token = 'shpat_x'; c._token_expires = 9e18  # skip the oauth round-trip
    out = c.graphql('{ shop { name } }')
    assert out['shop']['name'] == 'Autoworld.ro'
    assert calls['n'] == 2


def test_fetch_car_attribute_values_maps_by_gid(monkeypatch):
    payload = {'taxonomy': {'categories': {'edges': [
        {'node': {'attributes': {'edges': [
            {'node': {'id': 'gid://a/1', 'name': 'Fuel',
                      'values': {'edges': [{'node': {'id': 'v1', 'name': 'One'}}]}}},
            {'node': {'id': 'gid://a/2', 'name': 'Color',
                      'values': {'edges': [{'node': {'id': 'v2', 'name': 'Two'}},
                                           {'node': {'id': 'v3', 'name': 'Three'}}]}}},
        ]}}},
    ]}}}
    c = ShopifyClient('d.myshopify.com', 'cid', 'sec')
    monkeypatch.setattr(c, 'graphql', lambda q, v=None: payload)
    result = c.fetch_car_attribute_values()
    assert set(result.keys()) == {'gid://a/1', 'gid://a/2'}
    assert result['gid://a/1'] == [{'id': 'v1', 'name': 'One'}]
    assert result['gid://a/2'] == [{'id': 'v2', 'name': 'Two'}, {'id': 'v3', 'name': 'Three'}]


def test_fetch_car_attribute_values_empty_edges(monkeypatch):
    c = ShopifyClient('d.myshopify.com', 'cid', 'sec')
    monkeypatch.setattr(c, 'graphql', lambda q, v=None: {'taxonomy': {'categories': {'edges': []}}})
    assert c.fetch_car_attribute_values() == {}
