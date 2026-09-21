import datetime
import json

from carpark.connectors.shopify import mapper
from carpark.connectors.shopify.translations import BODY_TYPE_RO

BASE = {
    'vin': 'WBA1234567890XYZ1', 'brand': 'BMW', 'model': 'X5', 'variant': 'xDrive30d',
    'year_of_manufacture': 2021, 'status': 'LISTED', 'current_price': 45000,
    'price_currency': 'EUR', 'fuel_type': 'petrol', 'transmission': 'automatic',
    'drive_type': 'rear', 'color_exterior': 'gray', 'body_type': 'suv',
    'mileage_km': 60000, 'listing_title': '', 'listing_description': 'Stare impecabilă',
    'equipment': ['Apple Carplay', 'Navigație'], 'optional_packages': ['Pachet M Sport'],
}
PHOTOS = [{'url': 'https://cdn.example/1.jpg', 'is_primary': True, 'sort_order': 0}]

FIELD_MAP = [
    {'source_expr': 'brand', 'target_namespace': 'custom', 'target_key': 'marca',
     'target_type': 'single_line_text_field', 'transform': 'raw', 'is_active': True},
    {'source_expr': 'fuel_type', 'target_namespace': 'custom', 'target_key': 'fuel',
     'target_type': 'single_line_text_field', 'transform': 'ro_value', 'is_active': True},
    {'source_expr': 'transmission', 'target_namespace': 'custom', 'target_key': 'cutie_viteze',
     'target_type': 'single_line_text_field', 'transform': 'ro_value', 'is_active': True},
    {'source_expr': 'drive_type', 'target_namespace': 'custom', 'target_key': 'transmisie',
     'target_type': 'list.single_line_text_field', 'transform': 'ro_list', 'is_active': True},
    {'source_expr': 'color_exterior', 'target_namespace': 'custom', 'target_key': 'culoare',
     'target_type': 'single_line_text_field', 'transform': 'ro_value', 'is_active': True},
    {'source_expr': 'mileage_km', 'target_namespace': 'custom', 'target_key': 'kilometraj',
     'target_type': 'single_line_text_field', 'transform': 'int', 'is_active': True},
    {'source_expr': 'equipment + optional_packages', 'target_namespace': 'custom', 'target_key': 'dotari',
     'target_type': 'multi_line_text_field', 'transform': 'dotari', 'is_active': True},
    # stale/deactivated row -> must NOT be emitted as a metafield
    {'source_expr': 'registration_number', 'target_namespace': 'custom', 'target_key': 'nr_imatr_',
     'target_type': 'single_line_text_field', 'transform': 'raw', 'is_active': False},
]

VALUE_MAP = {
    'fuel_type': {'petrol': 'Benzină'},
    'transmission': {'automatic': 'Automată'},
    'drive_type': {'rear': 'Spate'},
    'color_exterior': {'gray': 'Gri'},
}

CONFIG = {'vendor': 'Autoworld', 'template_suffix': 'produs_servicii_stoc'}


def _mf(prod):
    return {(m['namespace'], m['key']): m for m in prod['metafields']}


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


def test_metafields_are_custom_namespace_only():
    prod, _warnings = mapper.vehicle_to_product(BASE, PHOTOS, FIELD_MAP, VALUE_MAP, CONFIG)
    mf = _mf(prod)

    assert mf[('custom', 'marca')] == {
        'namespace': 'custom', 'key': 'marca', 'type': 'single_line_text_field', 'value': 'BMW',
    }
    assert mf[('custom', 'fuel')]['value'] == 'Benzină'
    assert mf[('custom', 'cutie_viteze')]['value'] == 'Automată'
    assert mf[('custom', 'transmisie')]['value'] == '["Spate"]'
    assert mf[('custom', 'culoare')]['value'] == 'Gri'
    assert mf[('custom', 'kilometraj')]['value'] == '60000'
    assert mf[('custom', 'dotari')]['value'] == 'Apple Carplay\nNavigație\nPachet M Sport'
    assert mf[('custom', 'dotari')]['type'] == 'multi_line_text_field'

    # no carpark.* metafields at all
    assert all(m['namespace'] != 'carpark' for m in prod['metafields'])


def test_inactive_field_map_row_not_emitted():
    prod, _warnings = mapper.vehicle_to_product(BASE, PHOTOS, FIELD_MAP, VALUE_MAP, CONFIG)
    mf = _mf(prod)
    assert ('custom', 'nr_imatr_') not in mf


def test_field_map_row_missing_entirely_not_emitted():
    field_map = [r for r in FIELD_MAP if r['target_key'] != 'kilometraj']
    prod, _warnings = mapper.vehicle_to_product(BASE, PHOTOS, field_map, VALUE_MAP, CONFIG)
    mf = _mf(prod)
    assert ('custom', 'kilometraj') not in mf


def test_empty_source_is_skipped_with_warning():
    vehicle = {**BASE, 'color_exterior': None}
    prod, warnings = mapper.vehicle_to_product(vehicle, PHOTOS, FIELD_MAP, VALUE_MAP, CONFIG)
    mf = _mf(prod)
    assert ('custom', 'culoare') not in mf
    assert any('culoare' in w for w in warnings)


def test_top_level_product_fields():
    prod, _warnings = mapper.vehicle_to_product(BASE, PHOTOS, FIELD_MAP, VALUE_MAP, CONFIG)
    assert prod['productType'] == BODY_TYPE_RO.get('suv')
    assert prod['vendor'] == 'Autoworld'
    assert prod['templateSuffix'] == 'produs_servicii_stoc'
    assert prod['status'] == 'ACTIVE'
    assert 'category' not in prod

    v = prod['variants'][0]
    assert v['sku'] == 'WBA1234567890XYZ1'
    assert v['price'] == '45000.00'


def test_tags_order_and_content():
    prod, _warnings = mapper.vehicle_to_product(BASE, PHOTOS, FIELD_MAP, VALUE_MAP, CONFIG)
    assert prod['tags'] == ['2021', 'Automată', 'Benzină', 'Gri', BODY_TYPE_RO.get('suv'), 'BMW', 'X5']


def test_description_html_format():
    prod, _warnings = mapper.vehicle_to_product(BASE, PHOTOS, FIELD_MAP, VALUE_MAP, CONFIG)
    desc = prod['descriptionHtml']
    assert 'Specificații Tehnice' in desc
    assert 'Dotări și Opțiuni' in desc
    assert '<li><strong>Combustibil:</strong> Benzină</li>' in desc
    assert '<h3>BMW X5 xDrive30d 2021 (2021)</h3>' in desc


def test_description_html_escapes_special_characters():
    vehicle = {**BASE, 'equipment': ['A&B "Sport" <pkg>'], 'optional_packages': []}
    prod, _warnings = mapper.vehicle_to_product(vehicle, PHOTOS, FIELD_MAP, VALUE_MAP, CONFIG)
    desc = prod['descriptionHtml']
    assert '<pkg>' not in desc
    assert 'A&amp;B &quot;Sport&quot; &lt;pkg&gt;' in desc


def test_files_ordered_primary_then_sort_order():
    photos = [{'url': 'a', 'is_primary': False, 'sort_order': 2},
              {'url': 'b', 'is_primary': True, 'sort_order': 5},
              {'url': 'c', 'is_primary': False, 'sort_order': 1}]
    prod, _warnings = mapper.vehicle_to_product(BASE, photos, FIELD_MAP, VALUE_MAP, CONFIG)
    assert [f['originalSource'] for f in prod['files']] == ['b', 'c', 'a']


def test_ro_list_unmapped_value_falls_back_identity():
    vehicle = {**BASE, 'drive_type': 'unknown-drive'}
    prod, _warnings = mapper.vehicle_to_product(vehicle, PHOTOS, FIELD_MAP, VALUE_MAP, CONFIG)
    mf = _mf(prod)
    assert mf[('custom', 'transmisie')]['value'] == json.dumps(['unknown-drive'], ensure_ascii=False)


def test_dotari_manual_category_dict_flattened_in_order():
    vehicle = {**BASE, 'optional_packages': [],
               'equipment': {'Confort': ['Climatizare automată', 'Scaune încălzite'],
                             'Siguranță': ['ABS']}}
    prod, _warnings = mapper.vehicle_to_product(vehicle, PHOTOS, FIELD_MAP, VALUE_MAP, CONFIG)
    mf = _mf(prod)
    assert mf[('custom', 'dotari')]['value'] == 'Climatizare automată\nScaune încălzite\nABS'


def test_dotari_empty_dict_and_list_skipped_with_warning():
    vehicle = {**BASE, 'equipment': {}, 'optional_packages': []}
    prod, warnings = mapper.vehicle_to_product(vehicle, PHOTOS, FIELD_MAP, VALUE_MAP, CONFIG)
    mf = _mf(prod)
    assert ('custom', 'dotari') not in mf
    assert any('dotari' in w for w in warnings)


def test_dotari_empty_jsonb_string_skipped():
    vehicle = {**BASE, 'equipment': '{}', 'optional_packages': '[]'}
    prod, _warnings = mapper.vehicle_to_product(vehicle, PHOTOS, FIELD_MAP, VALUE_MAP, CONFIG)
    mf = _mf(prod)
    assert ('custom', 'dotari') not in mf


def test_dotari_autovit_flag_dict_keeps_truthy_flags():
    vehicle = {**BASE, 'optional_packages': [],
               'equipment': {'Navigație': True, 'Trapă': False}}
    prod, _warnings = mapper.vehicle_to_product(vehicle, PHOTOS, FIELD_MAP, VALUE_MAP, CONFIG)
    mf = _mf(prod)
    assert mf[('custom', 'dotari')]['value'] == 'Navigație'


YEAR_FIELD_MAP = FIELD_MAP + [
    {'source_expr': 'first_registration_date', 'target_namespace': 'custom',
     'target_key': 'data_livrarii', 'target_type': 'single_line_text_field',
     'transform': 'year', 'is_active': True},
]


def test_year_transform_from_date_string():
    vehicle = {**BASE, 'first_registration_date': '2019-05-10'}
    prod, _warnings = mapper.vehicle_to_product(vehicle, PHOTOS, YEAR_FIELD_MAP, VALUE_MAP, CONFIG)
    mf = _mf(prod)
    assert mf[('custom', 'data_livrarii')]['value'] == '2019'


def test_year_transform_from_date_object():
    vehicle = {**BASE, 'first_registration_date': datetime.date(2019, 5, 10)}
    prod, _warnings = mapper.vehicle_to_product(vehicle, PHOTOS, YEAR_FIELD_MAP, VALUE_MAP, CONFIG)
    mf = _mf(prod)
    assert mf[('custom', 'data_livrarii')]['value'] == '2019'


def test_product_type_defaults_when_body_unresolved():
    vehicle = {k: val for k, val in BASE.items() if k != 'body_type'}
    vehicle.pop('vehicle_type', None)
    prod, _warnings = mapper.vehicle_to_product(vehicle, PHOTOS, FIELD_MAP, VALUE_MAP, CONFIG)
    assert prod['productType'] == 'Autovehicul'


# ── Anunț free-text (listing_description) surfaced in the Shopify description ──

def test_description_includes_anunt_listing_description():
    vehicle = {**BASE, 'listing_description': 'Audi RSQ8 Quattro MHEV 600CP'}
    prod, _warnings = mapper.vehicle_to_product(vehicle, PHOTOS, FIELD_MAP, VALUE_MAP, CONFIG)
    assert 'Audi RSQ8 Quattro MHEV 600CP' in prod['descriptionHtml']


def test_description_anunt_preserves_line_breaks_and_escapes():
    vehicle = {**BASE, 'listing_description': 'Linia 1\nLinia 2 <b>'}
    prod, _warnings = mapper.vehicle_to_product(vehicle, PHOTOS, FIELD_MAP, VALUE_MAP, CONFIG)
    desc = prod['descriptionHtml']
    assert 'Linia 1<br>Linia 2 &lt;b&gt;' in desc
    assert '<b>' not in desc  # raw markup must be escaped, not injected


def test_description_no_anunt_block_when_listing_description_empty():
    vehicle = {**BASE, 'listing_description': '   '}
    prod, _warnings = mapper.vehicle_to_product(vehicle, PHOTOS, FIELD_MAP, VALUE_MAP, CONFIG)
    # still has the structured spec block, just no free-text paragraph
    assert 'Specificații Tehnice' in prod['descriptionHtml']


# ── dotari: also read equipment_options (TEXT[] Autovit slugs) + translate ──

def test_dotari_includes_equipment_options_translated():
    vehicle = {**BASE, 'equipment': {}, 'optional_packages': [],
               'equipment_options': ['carplay', 'android-auto']}
    prod, _warnings = mapper.vehicle_to_product(vehicle, PHOTOS, FIELD_MAP, VALUE_MAP, CONFIG)
    mf = _mf(prod)
    assert mf[('custom', 'dotari')]['value'] == 'Apple CarPlay\nAndroid Auto'


def test_dotari_equipment_options_value_map_override_wins():
    vm = {**VALUE_MAP, 'equipment': {'carplay': 'CarPlay (custom)'}}
    vehicle = {**BASE, 'equipment': {}, 'optional_packages': [],
               'equipment_options': ['carplay']}
    prod, _warnings = mapper.vehicle_to_product(vehicle, PHOTOS, FIELD_MAP, vm, CONFIG)
    assert _mf(prod)[('custom', 'dotari')]['value'] == 'CarPlay (custom)'


def test_dotari_equipment_options_unknown_slug_falls_back_identity():
    vehicle = {**BASE, 'equipment': {}, 'optional_packages': [],
               'equipment_options': ['zzz-unmapped-slug']}
    prod, _warnings = mapper.vehicle_to_product(vehicle, PHOTOS, FIELD_MAP, VALUE_MAP, CONFIG)
    assert _mf(prod)[('custom', 'dotari')]['value'] == 'zzz-unmapped-slug'


def test_dotari_merges_and_dedups_across_sources():
    # equipment_options adds a NEW item ('carplay'->'Apple CarPlay') and a
    # DUPLICATE of the manual equipment ('navigation'->'Navigație').
    vehicle = {**BASE, 'equipment': ['Navigație'], 'optional_packages': [],
               'equipment_options': ['carplay', 'navigation']}
    prod, _warnings = mapper.vehicle_to_product(vehicle, PHOTOS, FIELD_MAP, VALUE_MAP, CONFIG)
    assert _mf(prod)[('custom', 'dotari')]['value'] == 'Apple CarPlay\nNavigație'


# ── putere_kw: derive from HP when the kw column is empty ──

KW_FIELD_MAP = [
    {'source_expr': 'engine_power_kw', 'target_namespace': 'custom', 'target_key': 'putere_kw',
     'target_type': 'single_line_text_field', 'transform': 'int', 'is_active': True},
]


def test_putere_kw_derived_from_hp_when_missing():
    vehicle = {**BASE, 'engine_power_kw': None, 'engine_power_hp': 600}
    prod, _warnings = mapper.vehicle_to_product(vehicle, PHOTOS, KW_FIELD_MAP, VALUE_MAP, CONFIG)
    assert _mf(prod)[('custom', 'putere_kw')]['value'] == '441'  # round(600 * 0.7355)


def test_putere_kw_uses_explicit_value_when_present():
    vehicle = {**BASE, 'engine_power_kw': 300, 'engine_power_hp': 600}
    prod, _warnings = mapper.vehicle_to_product(vehicle, PHOTOS, KW_FIELD_MAP, VALUE_MAP, CONFIG)
    assert _mf(prod)[('custom', 'putere_kw')]['value'] == '300'


def test_putere_kw_empty_when_no_hp_either():
    vehicle = {**BASE, 'engine_power_kw': None, 'engine_power_hp': None}
    prod, warnings = mapper.vehicle_to_product(vehicle, PHOTOS, KW_FIELD_MAP, VALUE_MAP, CONFIG)
    assert ('custom', 'putere_kw') not in _mf(prod)
    assert any('putere_kw' in w for w in warnings)
