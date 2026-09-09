# jarvis/tests/carpark/test_shopify_connector.py
from carpark.connectors.shopify.connector import ShopifyConnector, ensure_platform

class FakeClient:
    def __init__(self): self.status_calls = []; self.last_input = None
    def product_set(self, product_input):
        self.last_input = product_input
        return {'id': 'gid://shopify/Product/55', 'handle': 'bmw-x5',
                'status': 'DRAFT', 'preview_url': 'https://x/preview', 'userErrors': []}
    def set_product_status(self, gid, status):
        self.status_calls.append((gid, status)); return {'product': {'id': gid, 'status': status}, 'userErrors': []}

class FakePub:
    def __init__(self): self.created=[]; self.updated=[]; self._listing=None
    def get_listing_by_vehicle_platform(self, vid, pid): return self._listing
    def create_listing(self, data): self.created.append(data); return {'id': 1, **data}
    def update_listing(self, listing_id, data): self.updated.append((listing_id, data)); return {'id': listing_id, **data}

VEH = {'id': 7, 'vin': 'WBA1234567890XYZ1', 'brand': 'BMW', 'model': 'X5',
       'status': 'LISTED', 'current_price': 45000, 'vehicle_type': 'Autoturism'}
PHOTOS = [{'url': 'https://cdn/1.jpg', 'is_primary': True, 'sort_order': 0}]

def test_publish_creates_listing_when_none_exists():
    pub = FakePub()
    conn = ShopifyConnector(FakeClient(), pub, platform_id=3)
    out = conn.publish(VEH, PHOTOS, taxo_map={})
    assert out['success'] is True
    assert out['external_id'] == 'gid://shopify/Product/55'
    assert pub.created and pub.created[0]['vehicle_id'] == 7
    assert pub.created[0]['platform_id'] == 3
    assert pub.created[0]['external_listing_id'] == 'gid://shopify/Product/55'

def test_publish_updates_listing_when_exists():
    pub = FakePub(); pub._listing = {'id': 9, 'external_listing_id': 'gid://shopify/Product/55'}
    fc = FakeClient()
    conn = ShopifyConnector(fc, pub, platform_id=3)
    out = conn.publish(VEH, PHOTOS, taxo_map={})
    assert out['success'] is True
    assert fc.last_input['id'] == 'gid://shopify/Product/55'
    assert pub.updated and pub.updated[0][0] == 9
    data = pub.updated[0][1]
    assert data['status'] == 'published'
    assert 'vehicle_id' not in data and 'platform_id' not in data

def test_publish_rejects_ineligible():
    conn = ShopifyConnector(FakeClient(), FakePub(), platform_id=3)
    out = conn.publish({**VEH, 'status': 'SOLD'}, PHOTOS, taxo_map={})
    assert out['success'] is False and 'status' in out['error']

def test_deactivate_archives():
    fc = FakeClient()
    conn = ShopifyConnector(fc, FakePub(), platform_id=3)
    out = conn.deactivate('gid://shopify/Product/55')
    assert out['success'] is True
    assert fc.status_calls == [('gid://shopify/Product/55', 'ARCHIVED')]

def test_ensure_platform_creates_when_missing():
    class P:
        def __init__(self): self.rows=[]
        def list_platforms(self): return []
        def create_platform(self, data): self.rows.append(data); return {'id': 42, **data}
    p = P()
    pid = ensure_platform(p, 'cb6c17-2.myshopify.com')
    assert pid == 42 and p.rows[0]['platform_type'] == 'shopify'
