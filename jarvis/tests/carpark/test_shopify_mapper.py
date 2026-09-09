from carpark.connectors.shopify import mapper
from carpark.connectors.shopify import taxonomy

BASE = {'vin': 'WBA1234567890XYZ1', 'brand': 'BMW', 'model': 'X5', 'variant': 'xDrive30d',
        'year_of_manufacture': 2021, 'status': 'LISTED', 'current_price': 45000,
        'price_currency': 'EUR', 'fuel_type': 'Motorină', 'transmission': 'Automată',
        'color_exterior': 'Negru', 'state': 'SH', 'vehicle_type': 'Autoturism',
        'mileage_km': 60000, 'listing_title': '', 'listing_description': 'Stare impecabilă'}
PHOTOS = [{'url': 'https://cdn.example/1.jpg', 'is_primary': True, 'sort_order': 0}]

MAP = {
  'fuel_type': {'Motorină': {'target_gid': 'gid://.../diesel', 'target_label': 'Diesel',
                             'shopify_attribute_gid': 'gid://shopify/TaxonomyAttribute/2177'}},
  'category':  {'Autoturism': {'target_gid': 'gid://shopify/TaxonomyCategory/vp-2-2-1-1',
                               'target_label': 'Cars', 'shopify_attribute_gid': None}},
}

def test_eligible_true():
    ok, reason = mapper.is_eligible(BASE, PHOTOS)
    assert ok is True and reason == ''

def test_ineligible_no_photo():
    ok, reason = mapper.is_eligible(BASE, [])
    assert ok is False and 'photo' in reason.lower()

def test_ineligible_status():
    ok, reason = mapper.is_eligible({**BASE, 'status': 'SOLD'}, PHOTOS)
    assert ok is False and 'status' in reason.lower()

def test_ineligible_no_price():
    ok, reason = mapper.is_eligible({**BASE, 'current_price': 0, 'list_price': None}, PHOTOS)
    assert ok is False and 'price' in reason.lower()

def test_vehicle_to_product_core_fields():
    prod, warnings = mapper.vehicle_to_product(BASE, PHOTOS, MAP)
    assert prod['title'] == 'BMW X5 xDrive30d 2021'      # title fallback
    assert prod['vendor'] == 'BMW'
    assert prod['productType'] == 'Autovehicul'
    assert prod['status'] == 'DRAFT'
    assert prod['category'] == 'gid://shopify/TaxonomyCategory/vp-2-2-1-1'
    v = prod['variants'][0]
    assert v['sku'] == 'WBA1234567890XYZ1'
    assert v['price'] == '45000.00'
    assert prod['files'][0]['originalSource'] == 'https://cdn.example/1.jpg'
    # mapped fuel -> metafield present
    mf = {(m['namespace'], m['key']): m['value'] for m in prod['metafields']}
    assert mf[('carpark', 'fuel_type')] == 'Diesel'
    assert mf[('carpark', 'vin')] == 'WBA1234567890XYZ1'
    # transmission unmapped -> warning, no transmission metafield
    assert any('transmission' in w for w in warnings)
    assert ('carpark', 'transmission') not in mf

def test_files_ordered_primary_then_sort_order():
    photos = [{'url': 'a', 'is_primary': False, 'sort_order': 2},
              {'url': 'b', 'is_primary': True, 'sort_order': 5},
              {'url': 'c', 'is_primary': False, 'sort_order': 1}]
    prod, _ = mapper.vehicle_to_product(BASE, photos, MAP)
    assert [f['originalSource'] for f in prod['files']] == ['b', 'c', 'a']

def test_category_falls_back_when_unmapped():
    prod, _ = mapper.vehicle_to_product(BASE, PHOTOS, {})
    assert prod['category'] == taxonomy.CARS_CATEGORY_GID
