"""Low-level Shopify Admin API client (client-credentials grant + GraphQL)."""
import time
import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger('jarvis.carpark.shopify')

DEFAULT_API_VERSION = '2026-07'
TOKEN_TTL_BUFFER = 300  # refresh 5 min before expiry


class ShopifyAuthError(Exception):
    """Raised when the client-credentials grant fails."""
    pass


class ShopifyError(Exception):
    """Raised on GraphQL/userErrors."""
    pass


class ShopifyClient:
    """HTTP client for one Shopify store using the client-credentials grant."""

    def __init__(self, store_domain: str, client_id: str, client_secret: str,
                 api_version: str = DEFAULT_API_VERSION, timeout: int = 20):
        self.store_domain = store_domain.strip().rstrip('/')
        self.client_id = client_id
        self.client_secret = client_secret
        self.api_version = api_version
        self.timeout = timeout
        self._token: Optional[str] = None
        self._token_expires: float = 0.0

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires:
            return self._token
        url = f'https://{self.store_domain}/admin/oauth/access_token'
        resp = requests.post(
            url,
            data={
                'grant_type': 'client_credentials',
                'client_id': self.client_id,
                'client_secret': self.client_secret,
            },
            headers={'Content-Type': 'application/x-www-form-urlencoded',
                     'Accept': 'application/json'},
            timeout=self.timeout,
        )
        try:
            data = resp.json()
        except ValueError:
            raise ShopifyAuthError(f'Non-JSON token response (HTTP {resp.status_code})')
        if resp.status_code >= 400 or 'error' in data or 'access_token' not in data:
            raise ShopifyAuthError(data.get('error_description') or data.get('error')
                                   or f'HTTP {resp.status_code}')
        self._token = data['access_token']
        self._token_expires = time.time() + int(data.get('expires_in', 86399)) - TOKEN_TTL_BUFFER
        logger.info('Shopify token acquired for %s', self.store_domain)
        return self._token

    # --- GraphQL core ---
    _THROTTLE_MAX_ATTEMPTS = 3
    _THROTTLE_BACKOFF = 1  # seconds slept between throttled retries

    @staticmethod
    def _is_throttled(errors: Any) -> bool:
        """True if any GraphQL error carries extensions.code == 'THROTTLED'."""
        if not isinstance(errors, list):
            return False
        for e in errors:
            if isinstance(e, dict):
                ext = e.get('extensions')
                if isinstance(ext, dict) and ext.get('code') == 'THROTTLED':
                    return True
        return False

    def graphql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        token = self._get_token()
        url = f'https://{self.store_domain}/admin/api/{self.api_version}/graphql.json'
        for attempt in range(self._THROTTLE_MAX_ATTEMPTS):
            resp = requests.post(url, json={'query': query, 'variables': variables or {}},
                                 headers={'X-Shopify-Access-Token': token,
                                          'Content-Type': 'application/json'},
                                 timeout=self.timeout)
            resp.raise_for_status()
            body = resp.json()
            errors = body.get('errors')
            if errors:
                # Shopify returns HTTP 200 with a THROTTLED error under rate limiting —
                # retry with bounded backoff before surfacing the error.
                if self._is_throttled(errors) and attempt < self._THROTTLE_MAX_ATTEMPTS - 1:
                    time.sleep(self._THROTTLE_BACKOFF)
                    continue
                raise ShopifyError(str(errors))
            return body['data']

    def get_shop(self) -> Dict[str, Any]:
        return self.graphql('{ shop { name currencyCode myshopifyDomain } }')['shop']

    _PRODUCT_SET = '''
    mutation productSet($input: ProductSetInput!) {
      productSet(synchronous: true, input: $input) {
        product { id handle status onlineStorePreviewUrl }
        userErrors { field message }
      }
    }'''

    def product_set(self, product_input: Dict[str, Any]) -> Dict[str, Any]:
        data = self.graphql(self._PRODUCT_SET, {'input': product_input})
        if 'productSet' not in data:
            raise ShopifyError(f'unexpected productSet response: {data}')
        node = data['productSet']
        p = node.get('product') or {}
        return {'id': p.get('id'), 'handle': p.get('handle'), 'status': p.get('status'),
                'preview_url': p.get('onlineStorePreviewUrl'),
                'userErrors': node.get('userErrors', [])}

    _PRODUCT_UPDATE_STATUS = '''
    mutation setStatus($input: ProductUpdateInput!) {
      productUpdate(product: $input) {
        product { id status }
        userErrors { field message }
      }
    }'''

    def set_product_status(self, product_gid: str, status: str) -> Dict[str, Any]:
        data = self.graphql(self._PRODUCT_UPDATE_STATUS,
                            {'input': {'id': product_gid, 'status': status}})
        if 'productUpdate' not in data:
            raise ShopifyError(f'unexpected productUpdate response: {data}')
        node = data['productUpdate']
        return {'product': node.get('product'), 'userErrors': node.get('userErrors', [])}

    _ATTR_VALUES = '''
    query attrValues {
      taxonomy {
        categories(first: 1, search: "Cars, Trucks & Vans") {
          edges { node {
            attributes(first: 50) { edges { node {
              ... on TaxonomyChoiceListAttribute {
                id name values(first: 250) { edges { node { id name } } }
              }
            } } }
          } }
        }
      }
    }'''

    def fetch_car_attribute_values(self) -> Dict[str, List[Dict[str, str]]]:
        """Fetch value lists for every choice-list attribute of the car category in ONE query.

        Returns a map {attribute_gid: [{'id','name'}, ...]}. Returns {} when the taxonomy
        response has no category edge. Missing 'attributes'/'values' keys are tolerated
        (treated as no attributes / no values) rather than raising.
        """
        data = self.graphql(self._ATTR_VALUES)
        taxonomy = data.get('taxonomy') if isinstance(data, dict) else None
        categories = taxonomy.get('categories') if isinstance(taxonomy, dict) else None
        edges = categories.get('edges') if isinstance(categories, dict) else None
        if not edges:
            return {}
        node = edges[0].get('node') or {}
        attributes = node.get('attributes') or {}
        result: Dict[str, List[Dict[str, str]]] = {}
        for a in attributes.get('edges', []) or []:
            attr = a.get('node') or {}
            gid = attr.get('id')
            if not gid:
                continue
            values = (attr.get('values') or {}).get('edges', []) or []
            result[gid] = [{'id': v['node']['id'], 'name': v['node']['name']} for v in values]
        return result

    def fetch_attribute_values(self, attribute_gid: str) -> List[Dict[str, str]]:
        """Value list for a single car-category attribute (delegates to the batch fetch)."""
        return self.fetch_car_attribute_values().get(attribute_gid, [])
