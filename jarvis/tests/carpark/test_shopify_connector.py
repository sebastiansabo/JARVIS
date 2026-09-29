# jarvis/tests/carpark/test_shopify_connector.py
import carpark.connectors.shopify.connector as conn_mod
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
    def __init__(self): self.created=[]; self.updated=[]; self._listing=None; self.logs=[]
    def get_listing_by_vehicle_platform(self, vid, pid): return self._listing
    def create_listing(self, data): self.created.append(data); return {'id': 1, **data}
    def update_listing(self, listing_id, data): self.updated.append((listing_id, data)); return {'id': listing_id, **data}
    def log_sync(self, **kw): self.logs.append(kw); return {'id': len(self.logs), **kw}

VEH = {'id': 7, 'vin': 'WBA1234567890XYZ1', 'brand': 'BMW', 'model': 'X5',
       'status': 'LISTED', 'current_price': 45000, 'vehicle_type': 'Autoturism'}
PHOTOS = [{'url': 'https://cdn/1.jpg', 'is_primary': True, 'sort_order': 0}]
FIELD_MAP = [{'source_expr': 'brand', 'target_namespace': 'custom', 'target_key': 'marca',
              'target_type': 'single_line_text_field', 'transform': 'raw'}]
VALUE_MAP = {}
CONFIG = {'vendor': 'Autoworld', 'template_suffix': 'produs_servicii_stoc'}

def test_publish_creates_listing_when_none_exists():
    pub = FakePub()
    conn = ShopifyConnector(FakeClient(), pub, platform_id=3)
    out = conn.publish(VEH, PHOTOS, field_map=FIELD_MAP, value_map=VALUE_MAP, config=CONFIG)
    assert out['success'] is True
    assert out['external_id'] == 'gid://shopify/Product/55'
    assert pub.created and pub.created[0]['vehicle_id'] == 7
    assert pub.created[0]['platform_id'] == 3
    assert pub.created[0]['external_listing_id'] == 'gid://shopify/Product/55'

FIELD_MAP_FUEL = [
    {'source_expr': 'brand', 'target_namespace': 'custom', 'target_key': 'marca',
     'target_type': 'single_line_text_field', 'transform': 'raw'},
    {'source_expr': 'fuel_type', 'target_namespace': 'custom', 'target_key': 'fuel',
     'target_type': 'single_line_text_field', 'transform': 'ro_value'},
]


class ChoiceErrorThenOkClient(FakeClient):
    """First product_set fails with a choice-list rejection; the second succeeds.
    Records the metafield keys sent on each call."""
    def __init__(self):
        super().__init__()
        self.calls = []
    def product_set(self, product_input):
        self.last_input = product_input
        self.calls.append([(m['namespace'], m['key']) for m in product_input.get('metafields', [])])
        if len(self.calls) == 1:
            return {'id': None, 'userErrors': [
                {'field': ['input', 'metafields', '1', 'value'],
                 'message': 'Value does not exist in provided choices'}]}
        return {'id': 'gid://shopify/Product/55', 'handle': 'x', 'status': 'ACTIVE',
                'preview_url': 'https://x/p', 'userErrors': []}


def test_publish_retries_dropping_unmapped_choice_field():
    # fuel_type 'ethanol' has no VALUE_MAP translation -> unmapped choice value.
    # The whole publish must not fail; it retries without custom.fuel and succeeds.
    veh = {**VEH, 'fuel_type': 'ethanol'}
    client = ChoiceErrorThenOkClient()
    pub = FakePub()
    conn = ShopifyConnector(client, pub, platform_id=3)
    out = conn.publish(veh, PHOTOS, field_map=FIELD_MAP_FUEL, value_map={}, config=CONFIG)
    assert out['success'] is True
    assert len(client.calls) == 2, 'should retry once'
    assert ('custom', 'fuel') in client.calls[0], 'first attempt includes the unmapped fuel field'
    assert ('custom', 'fuel') not in client.calls[1], 'retry drops the unmapped fuel field'
    assert ('custom', 'marca') in client.calls[1], 'retry keeps mapped fields'


def test_publish_success_writes_audit_log_row():
    pub = FakePub()
    conn = ShopifyConnector(FakeClient(), pub, platform_id=3)
    conn.publish(VEH, PHOTOS, field_map=FIELD_MAP, value_map=VALUE_MAP, config=CONFIG)
    assert pub.logs, 'a successful publish should record an audit-log row'
    log = pub.logs[-1]
    assert log['vehicle_id'] == 7 and log['platform_id'] == 3
    assert log['action'] == 'publish' and log['success'] is True


def test_publish_failure_writes_audit_log_row():
    pub = FakePub()
    conn = ShopifyConnector(FailingClient(), pub, platform_id=3)
    conn.publish(VEH, PHOTOS, field_map=FIELD_MAP, value_map=VALUE_MAP, config=CONFIG)
    assert pub.logs, 'a failed publish should record an audit-log row'
    log = pub.logs[-1]
    assert log['success'] is False
    assert 'choices' in (log['error_message'] or '')


class FailingClient(FakeClient):
    def product_set(self, product_input):
        self.last_input = product_input
        return {'id': None, 'userErrors': [
            {'field': 'fuel', 'message': 'Value does not exist in provided choices'}]}


def test_publish_records_error_row_on_first_publish_failure():
    # A first-ever publish that fails must leave a trace (status='error'), not
    # vanish so the vehicle reverts to 'not_published' with no recorded reason.
    pub = FakePub()  # no existing listing
    conn = ShopifyConnector(FailingClient(), pub, platform_id=3)
    out = conn.publish(VEH, PHOTOS, field_map=FIELD_MAP, value_map=VALUE_MAP, config=CONFIG)
    assert out['success'] is False
    assert pub.created, 'a failed first publish should still record a listing row'
    row = pub.created[0]
    assert row['status'] == 'error'
    assert row['vehicle_id'] == 7 and row['platform_id'] == 3
    assert 'choices' in row['error_message']


def test_publish_marks_existing_listing_error_on_failure():
    pub = FakePub(); pub._listing = {'id': 9, 'external_listing_id': 'gid://shopify/Product/55'}
    conn = ShopifyConnector(FailingClient(), pub, platform_id=3)
    out = conn.publish(VEH, PHOTOS, field_map=FIELD_MAP, value_map=VALUE_MAP, config=CONFIG)
    assert out['success'] is False
    assert pub.updated and pub.updated[0][1]['status'] == 'error'
    assert not pub.created  # existing row updated, not a new one


def test_publish_updates_listing_when_exists():
    pub = FakePub(); pub._listing = {'id': 9, 'external_listing_id': 'gid://shopify/Product/55'}
    fc = FakeClient()
    conn = ShopifyConnector(fc, pub, platform_id=3)
    out = conn.publish(VEH, PHOTOS, field_map=FIELD_MAP, value_map=VALUE_MAP, config=CONFIG)
    assert out['success'] is True
    assert fc.last_input['id'] == 'gid://shopify/Product/55'
    assert pub.updated and pub.updated[0][0] == 9
    data = pub.updated[0][1]
    assert data['status'] == 'published'
    assert 'vehicle_id' not in data and 'platform_id' not in data

def test_publish_presigns_spaces_photo_keys(monkeypatch):
    # Photos are stored as private Spaces object keys; Shopify fetches originalSource
    # server-side, so keys must be turned into time-limited public URLs. Already-public
    # http(s) sources pass through untouched, and primary/sort ordering is preserved.
    monkeypatch.setattr(conn_mod.spaces_service, 'presigned_url',
                        lambda key, **kw: f'https://signed.example/{key}')
    fc = FakeClient()
    conn = ShopifyConnector(fc, FakePub(), platform_id=3)
    photos = [{'url': 'private/carpark/7/b.jpg', 'is_primary': False, 'sort_order': 1},
              {'url': 'private/carpark/7/a.jpg', 'is_primary': True, 'sort_order': 0},
              {'url': 'https://cdn/already-public.jpg', 'is_primary': False, 'sort_order': 2}]
    conn.publish(VEH, photos, field_map=FIELD_MAP, value_map=VALUE_MAP, config=CONFIG)
    sources = [f['originalSource'] for f in fc.last_input['files']]
    assert sources == [
        'https://signed.example/private/carpark/7/a.jpg',
        'https://signed.example/private/carpark/7/b.jpg',
        'https://cdn/already-public.jpg',
    ]


def test_publish_rejects_ineligible():
    conn = ShopifyConnector(FakeClient(), FakePub(), platform_id=3)
    out = conn.publish({**VEH, 'status': 'SOLD'}, PHOTOS, field_map=FIELD_MAP, value_map=VALUE_MAP, config=CONFIG)
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
