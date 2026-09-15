import pytest
from carpark.connectors.shopify.client import ShopifyClient


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._p = payload

    def json(self):
        return self._p

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError('http')


def _client(monkeypatch, gql_payload):
    c = ShopifyClient('cb6c17-2.myshopify.com', 'cid', 'sec')
    c._token = 'shpat_x'
    c._token_expires = 9e18

    def fake_post(url, json=None, headers=None, timeout=None):
        assert headers['X-Shopify-Access-Token'] == 'shpat_x'
        assert '/admin/api/2026-07/graphql.json' in url
        return _Resp(200, gql_payload)

    monkeypatch.setattr('carpark.connectors.shopify.client.requests.post', fake_post)
    return c


def test_fetch_metafield_definitions_returns_namespace_key_to_type_dict(monkeypatch):
    payload = {
        'data': {
            'metafieldDefinitions': {
                'edges': [
                    {
                        'node': {
                            'namespace': 'custom',
                            'key': 'marca',
                            'type': {'name': 'single_line_text_field'},
                        }
                    },
                    {
                        'node': {
                            'namespace': 'custom',
                            'key': 'dotari',
                            'type': {'name': 'multi_line_text_field'},
                        }
                    },
                ],
                'pageInfo': {'hasNextPage': False, 'endCursor': None},
            }
        }
    }
    c = _client(monkeypatch, payload)
    out = c.fetch_metafield_definitions()
    assert out == {
        'custom.marca': 'single_line_text_field',
        'custom.dotari': 'multi_line_text_field',
    }
