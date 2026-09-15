# jarvis/carpark/connectors/shopify/service.py
"""Headless Shopify connector construction (usable outside a Flask request).

Imports the account/client/platform wiring ONE-WAY from routes.py so a
background job (e.g. the listing autosync tick) can build a ShopifyConnector
without going through a request. routes.py must NOT import this module —
that would create a circular import, since this module imports from routes.
"""
from carpark.connectors.shopify.connector import ShopifyConnector, ensure_platform
from carpark.connectors.shopify.routes import _get_single_account, _build_client, _pub_repo


def build_shopify_connector():
    """Return a ShopifyConnector built from the single stored account, or None."""
    account = _get_single_account()
    if not account:
        return None
    client = _build_client(account)
    platform_id = ensure_platform(_pub_repo, client.store_domain)
    return ShopifyConnector(client, _pub_repo, platform_id)
