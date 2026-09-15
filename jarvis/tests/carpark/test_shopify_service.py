# jarvis/tests/carpark/test_shopify_service.py
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
from unittest.mock import patch, MagicMock

from carpark.connectors.shopify import service


def test_build_returns_none_when_no_account():
    with patch.object(service, '_get_single_account', return_value=None):
        assert service.build_shopify_connector() is None


def test_build_returns_connector_when_configured():
    acct = {'id': 1}
    with patch.object(service, '_get_single_account', return_value=acct), \
         patch.object(service, '_build_client', return_value=MagicMock(store_domain='x.myshopify.com')), \
         patch.object(service, 'ensure_platform', return_value=7):
        conn = service.build_shopify_connector()
    assert conn is not None and conn.platform_id == 7
