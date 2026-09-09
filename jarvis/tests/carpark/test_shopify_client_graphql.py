import pytest
from carpark.connectors.shopify.client import ShopifyClient, ShopifyError

class _Resp:
    def __init__(self, status, payload): self.status_code=status; self._p=payload
    def json(self): return self._p
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError('http')

def _client(monkeypatch, gql_payload):
    c = ShopifyClient('cb6c17-2.myshopify.com', 'cid', 'sec')
    c._token = 'shpat_x'; c._token_expires = 9e18
    def fake_post(url, json=None, headers=None, timeout=None):
        assert headers['X-Shopify-Access-Token'] == 'shpat_x'
        assert '/admin/api/2026-07/graphql.json' in url
        return _Resp(200, gql_payload)
    monkeypatch.setattr('carpark.connectors.shopify.client.requests.post', fake_post)
    return c

def test_graphql_returns_data(monkeypatch):
    c = _client(monkeypatch, {'data': {'shop': {'name': 'Autoworld.ro'}}})
    assert c.graphql('{ shop { name } }')['shop']['name'] == 'Autoworld.ro'

def test_graphql_top_level_errors_raise(monkeypatch):
    c = _client(monkeypatch, {'errors': [{'message': 'boom'}]})
    with pytest.raises(ShopifyError):
        c.graphql('{ shop { name } }')

def test_product_set_returns_product_and_usererrors(monkeypatch):
    payload = {'data': {'productSet': {
        'product': {'id': 'gid://shopify/Product/1', 'handle': 'x', 'status': 'DRAFT'},
        'userErrors': []}}}
    c = _client(monkeypatch, payload)
    out = c.product_set({'title': 'BMW'})
    assert out['id'] == 'gid://shopify/Product/1'
    assert out['userErrors'] == []

def test_get_shop_returns_shop_fields(monkeypatch):
    payload = {'data': {'shop': {'name': 'Autoworld.ro', 'currencyCode': 'EUR',
                                 'myshopifyDomain': 'cb6c17-2.myshopify.com'}}}
    c = _client(monkeypatch, payload)
    out = c.get_shop()
    assert out['name'] == 'Autoworld.ro'
    assert out['currencyCode'] == 'EUR'

def test_set_product_status_returns_product_and_usererrors(monkeypatch):
    payload = {'data': {'productUpdate': {
        'product': {'id': 'gid://shopify/Product/1', 'status': 'ARCHIVED'},
        'userErrors': []}}}
    c = _client(monkeypatch, payload)
    out = c.set_product_status('gid://shopify/Product/1', 'ARCHIVED')
    assert out['product']['status'] == 'ARCHIVED'
    assert out['userErrors'] == []

def test_fetch_attribute_values_returns_matching_attribute(monkeypatch):
    gid = 'gid://shopify/TaxonomyAttribute/2177'
    payload = {'data': {'taxonomy': {'categories': {'edges': [
        {'node': {'attributes': {'edges': [
            {'node': {'id': 'gid://shopify/TaxonomyAttribute/9999', 'name': 'Other',
                      'values': {'edges': [
                          {'node': {'id': 'gid://shopify/TaxonomyValue/1', 'name': 'Nope'}}]}}},
            {'node': {'id': gid, 'name': 'Color',
                      'values': {'edges': [
                          {'node': {'id': 'gid://shopify/TaxonomyValue/10', 'name': 'Red'}},
                          {'node': {'id': 'gid://shopify/TaxonomyValue/11', 'name': 'Blue'}}]}}},
        ]}}},
    ]}}}}
    c = _client(monkeypatch, payload)
    out = c.fetch_attribute_values(gid)
    assert out == [
        {'id': 'gid://shopify/TaxonomyValue/10', 'name': 'Red'},
        {'id': 'gid://shopify/TaxonomyValue/11', 'name': 'Blue'},
    ]

def test_fetch_attribute_values_empty_category_returns_empty(monkeypatch):
    payload = {'data': {'taxonomy': {'categories': {'edges': []}}}}
    c = _client(monkeypatch, payload)
    assert c.fetch_attribute_values('gid://shopify/TaxonomyAttribute/2177') == []
