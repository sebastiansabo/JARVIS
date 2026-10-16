"""Reconcile externally-published listings back to CarPark vehicles by VIN."""

from carpark.services.reconcile_service import match_by_vin


VEHICLES = {'WAUZZZF20KN115355': 31, 'TMBJK7NS0K8000001': 7}


def test_matches_vin_to_vehicle():
    items = [{'vin': 'WAUZZZF20KN115355', 'external_id': '555', 'external_url': 'http://a/555'}]
    out = match_by_vin(items, VEHICLES)
    assert out['matched'] == 1 and out['unmatched'] == 0
    assert out['matches'] == [{'vehicle_id': 31, 'external_id': '555',
                               'external_url': 'http://a/555', 'vin': 'WAUZZZF20KN115355'}]


def test_vin_normalised_case_and_whitespace():
    items = [{'vin': ' wauzzzf20kn115355 ', 'external_id': '1', 'external_url': None}]
    out = match_by_vin(items, VEHICLES)
    assert out['matched'] == 1 and out['matches'][0]['vehicle_id'] == 31


def test_unmatched_vin_not_linked():
    items = [{'vin': 'XXXXXXXXXXXXXXXXX', 'external_id': '9', 'external_url': None}]
    out = match_by_vin(items, VEHICLES)
    assert out['matched'] == 0 and out['unmatched'] == 1 and out['matches'] == []


def test_blank_and_duplicate_vins_handled():
    items = [
        {'vin': '', 'external_id': '1', 'external_url': None},
        {'vin': 'TMBJK7NS0K8000001', 'external_id': '2', 'external_url': None},
        {'vin': 'TMBJK7NS0K8000001', 'external_id': '3', 'external_url': None},  # dup VIN
    ]
    out = match_by_vin(items, VEHICLES)
    assert out['matched'] == 1                      # dup collapsed, blank skipped
    assert out['matches'][0]['external_id'] == '2'  # first wins


from carpark.services.reconcile_service import reconcile_autovit_account, _advert_vin


class FakeAutovitClient:
    def __init__(self, pages, details=None):
        self.pages = pages                 # list of get_adverts page dicts
        self.details = details or {}       # advert_id -> full advert
        self.detail_calls = []
    def get_adverts(self, page=1, status=None):
        return self.pages[page - 1] if page - 1 < len(self.pages) else {'results': [], 'total_pages': len(self.pages)}
    def get_advert(self, advert_id):
        self.detail_calls.append(advert_id)
        return self.details.get(str(advert_id), {})


class FakeAutovitListingRepo:
    def __init__(self, existing=None):
        self.existing = existing or {}     # (vehicle_id, account_id) -> row
        self.upserts = []
    def get(self, vehicle_id, account_id):
        return self.existing.get((vehicle_id, account_id))
    def upsert(self, vehicle_id, account_id, **fields):
        self.upserts.append((vehicle_id, account_id, fields))
        return {'id': 1}


def test_advert_vin_reads_params():
    assert _advert_vin({'params': {'vin': 'wauzzzf20kn115355'}}) == 'WAUZZZF20KN115355'
    assert _advert_vin({'params': {}}) == ''
    assert _advert_vin({}) == ''


def test_reconcile_autovit_links_matched_unlinked_vehicles():
    # advert 100 (VIN 31) matches a vehicle with no listing → link it;
    # advert 200 (unknown VIN) → unmatched; advert 300 (VIN 7, already linked) → skip.
    pages = [{'total_pages': 1, 'results': [
        {'id': 100, 'url': 'http://a/100', 'params': {'vin': 'WAUZZZF20KN115355'}},
        {'id': 200, 'url': 'http://a/200', 'params': {'vin': 'UNKNOWNVIN0000001'}},
        {'id': 300, 'url': 'http://a/300', 'params': {'vin': 'TMBJK7NS0K8000001'}},
    ]}]
    client = FakeAutovitClient(pages)
    repo = FakeAutovitListingRepo(existing={(7, 17): {'external_advert_id': '300'}})
    out = reconcile_autovit_account(client, 17, VEHICLES, repo)
    assert out['scanned'] == 3
    assert out['matched'] == 2 and out['unmatched'] == 1
    assert out['linked'] == 1 and out['already_linked'] == 1
    assert repo.upserts == [(31, 17, {'external_advert_id': '100',
                                      'external_url': 'http://a/100', 'status': 'active'})]


def test_reconcile_autovit_fetches_full_advert_when_list_lacks_vin():
    # List results without params.vin → fall back to get_advert for the VIN.
    pages = [{'total_pages': 1, 'results': [{'id': 100, 'url': 'http://a/100'}]}]
    details = {'100': {'id': 100, 'params': {'vin': 'WAUZZZF20KN115355'}}}
    client = FakeAutovitClient(pages, details)
    repo = FakeAutovitListingRepo()
    out = reconcile_autovit_account(client, 17, VEHICLES, repo)
    assert client.detail_calls == ['100']
    assert out['linked'] == 1


from carpark.services.reconcile_service import reconcile_shopify


class FakeShopifyClient:
    def __init__(self, products): self.products = products
    def list_products_with_sku(self): return self.products


class FakePubRepo:
    def __init__(self, existing=None): self.existing = existing or {}; self.created = []
    def get_listing_by_vehicle_platform(self, vid, pid): return self.existing.get((vid, pid))
    def create_listing(self, data): self.created.append(data); return {'id': 1, **data}


def test_reconcile_shopify_links_matched_products():
    products = [
        {'id': 'gid://shopify/Product/55', 'sku': 'WAUZZZF20KN115355', 'url': 'https://shop/p/55'},
        {'id': 'gid://shopify/Product/99', 'sku': 'NOPEVIN0000000001', 'url': 'https://shop/p/99'},
    ]
    pub = FakePubRepo()
    out = reconcile_shopify(FakeShopifyClient(products), VEHICLES, pub, platform_id=3)
    assert out['matched'] == 1 and out['unmatched'] == 1 and out['linked'] == 1
    assert pub.created == [{'vehicle_id': 31, 'platform_id': 3,
                            'external_listing_id': 'gid://shopify/Product/55',
                            'external_url': 'https://shop/p/55', 'status': 'published'}]


def test_reconcile_shopify_skips_already_linked():
    products = [{'id': 'gid://shopify/Product/55', 'sku': 'WAUZZZF20KN115355', 'url': 'u'}]
    pub = FakePubRepo(existing={(31, 3): {'external_listing_id': 'gid://shopify/Product/55'}})
    out = reconcile_shopify(FakeShopifyClient(products), VEHICLES, pub, platform_id=3)
    assert out['already_linked'] == 1 and out['linked'] == 0 and pub.created == []
