"""Map a carpark_vehicles record to a Shopify ProductSetInput."""
import html
from typing import Any, Dict, List, Tuple

from . import taxonomy

ELIGIBLE_STATUSES = {'READY_FOR_SALE', 'LISTED', 'PRICE_REDUCED', 'AUCTION_CANDIDATE'}
PRODUCT_TYPE = 'Autovehicul'
METAFIELD_NAMESPACE = 'carpark'

# dimensions surfaced as native taxonomy attributes (also written as metafields for the theme)
_ATTR_DIMENSIONS = ['fuel_type', 'transmission', 'drive_type', 'color', 'condition']


def _price(vehicle: Dict[str, Any]):
    return vehicle.get('current_price') or vehicle.get('list_price')


def is_eligible(vehicle: Dict[str, Any], photos: List[dict]) -> Tuple[bool, str]:
    if vehicle.get('status') not in ELIGIBLE_STATUSES:
        return False, f"status {vehicle.get('status')!r} not in for-sale set"
    if not _price(vehicle) or float(_price(vehicle)) <= 0:
        return False, 'no positive price'
    if not photos:
        return False, 'no photo'
    return True, ''


def _title(v: Dict[str, Any]) -> str:
    if (v.get('listing_title') or '').strip():
        return v['listing_title'].strip()
    parts = [v.get('brand'), v.get('model'), v.get('variant'), v.get('year_of_manufacture')]
    return ' '.join(str(p) for p in parts if p)


def _description_html(v: Dict[str, Any]) -> str:
    body = (v.get('listing_description') or '').strip()
    specs = [
        ('Combustibil', v.get('fuel_type')), ('Cutie', v.get('transmission')),
        ('Putere', f"{v['engine_power_hp']} CP" if v.get('engine_power_hp') else None),
        ('Kilometraj', f"{v['mileage_km']} km" if v.get('mileage_km') is not None else None),
        ('Culoare', v.get('color_exterior')), ('An', v.get('year_of_manufacture')),
        ('Norma', v.get('euro_standard')),
    ]
    rows = ''.join(f'<tr><td>{html.escape(str(k))}</td><td>{html.escape(str(val))}</td></tr>'
                   for k, val in specs if val)
    table = f'<table>{rows}</table>' if rows else ''
    return f'<p>{html.escape(body)}</p>{table}' if body else table


def vehicle_to_product(vehicle: Dict[str, Any], photos: List[dict],
                       taxo_map: Dict[str, Dict[str, dict]]) -> Tuple[Dict[str, Any], List[str]]:
    """Build a Shopify ProductSetInput from a vehicle record.

    Caller must pass an eligible vehicle (see is_eligible) — a vehicle with no
    price will raise TypeError on price formatting.
    """
    warnings: List[str] = []

    def resolve(dimension: str):
        col = taxonomy.vehicle_field_for(dimension)
        src = vehicle.get(col)
        if not src:
            return None
        hit = taxo_map.get(dimension, {}).get(src)
        if not hit:
            warnings.append(f'unmapped {dimension}={src!r}')
        return hit

    metafields: List[dict] = [
        {'namespace': METAFIELD_NAMESPACE, 'key': 'vin', 'type': 'single_line_text_field',
         'value': str(vehicle.get('vin') or '')},
    ]
    for key in ('mileage_km', 'year_of_manufacture', 'engine_power_hp', 'co2_emissions',
                'euro_standard', 'first_registration_date'):
        val = vehicle.get(key)
        if val is not None and val != '':
            metafields.append({'namespace': METAFIELD_NAMESPACE, 'key': key,
                               'type': 'single_line_text_field', 'value': str(val)})

    for dim in _ATTR_DIMENSIONS:
        hit = resolve(dim)
        if hit:
            metafields.append({'namespace': METAFIELD_NAMESPACE, 'key': dim,
                               'type': 'single_line_text_field',
                               'value': hit.get('target_label') or ''})

    body_hit = resolve('body_type')
    if body_hit:
        metafields.append({'namespace': METAFIELD_NAMESPACE, 'key': 'body_type',
                           'type': 'single_line_text_field',
                           'value': body_hit.get('target_label') or ''})

    cat_hit = resolve('category')
    category_gid = (cat_hit or {}).get('target_gid') or taxonomy.CARS_CATEGORY_GID

    ordered = sorted(photos, key=lambda p: (not p.get('is_primary'), p.get('sort_order', 0)))
    files = [{'originalSource': p['url'], 'contentType': 'IMAGE'} for p in ordered if p.get('url')]

    price = _price(vehicle)
    tags = [t for t in [vehicle.get('brand'), vehicle.get('model'), vehicle.get('fuel_type'),
                        str(vehicle.get('year_of_manufacture') or ''), vehicle.get('body_type'),
                        vehicle.get('state'), 'carpark'] if t]

    product_input: Dict[str, Any] = {
        'title': _title(vehicle),
        'descriptionHtml': _description_html(vehicle),
        'vendor': (vehicle.get('brand') or '').strip() or 'CarPark',
        'productType': PRODUCT_TYPE,
        'status': 'DRAFT',
        'category': category_gid,
        'tags': tags,
        'metafields': metafields,
        'files': files,
        'productOptions': [{'name': 'Title', 'values': [{'name': 'Default Title'}]}],
        'variants': [{
            'optionValues': [{'optionName': 'Title', 'name': 'Default Title'}],
            'sku': str(vehicle.get('vin') or ''),
            'price': f'{float(price):.2f}',
            'inventoryPolicy': 'DENY',
        }],
    }
    return product_input, warnings
