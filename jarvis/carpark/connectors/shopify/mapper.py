"""Map a carpark_vehicles record to a Shopify ProductSetInput.

Builds the product from the DB-backed field map (carpark_shopify_field_map)
and value map (carpark_shopify_value_map): metafields live entirely under the
store's `custom.*` (Romanian) namespace, resolved dynamically from the field
map — no hardcoded `carpark.*` metafields. productType/vendor/templateSuffix/
status/tags/description are fixed, vehicle-field-driven logic (independent of
the field map) that reuses the same RO value-map translations via `ro()` so
there is a single source of truth for CarPark -> Romanian value translation.
"""
import html
import json
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from .translations import AUTOVIT_EQUIPMENT_RO, BODY_TYPE_RO, ro

ELIGIBLE_STATUSES = {'READY_FOR_SALE', 'LISTED', 'PRICE_REDUCED', 'AUCTION_CANDIDATE'}

# Metric horsepower (CP/PS) -> kilowatt conversion factor, used to derive
# custom.putere_kw when engine_power_kw is not filled but engine_power_hp is.
HP_TO_KW = 0.7355


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


def _coerce_list(value: Any) -> List[str]:
    """Normalize an equipment/packages value into a flat list of item strings.

    Handles every shape this column takes in the codebase:
      - list                          -> the (stripped, non-empty) items
      - manual dict {category:[items]} -> flattened items across categories
      - Autovit flag dict {flag:bool}  -> keys whose value is truthy
      - JSON string of any of the above -> recurse on the parsed value
      - bare string                    -> single item
      - None / '' / {} / [] / '{}'     -> []
    """
    if value is None:
        return []
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
        except (TypeError, ValueError):
            return [s]
        if isinstance(parsed, (list, dict)):
            return _coerce_list(parsed)
        return [s]
    if isinstance(value, list):
        return [str(x).strip() for x in value if x is not None and str(x).strip()]
    if isinstance(value, dict):
        if any(isinstance(v, list) for v in value.values()):
            # manual {category: [items]} shape -> flatten items across categories
            return [str(i).strip() for v in value.values() if isinstance(v, list)
                    for i in v if i is not None and str(i).strip()]
        # Autovit {flag: bool} shape -> keep truthy flags
        return [str(k).strip() for k, v in value.items() if v]
    s = str(value).strip()
    return [s] if s else []


def _equipment_label(value_map: Dict[str, Dict[str, str]], slug: str) -> str:
    """Translate an equipment_options Autovit slug to a display label.

    Precedence: admin value-map override ('equipment' dimension) > Autovit RO
    taxonomy > the slug itself (identity fallback, so nothing is ever dropped).
    """
    s = str(slug).strip()
    override = value_map.get('equipment', {}).get(s)
    return override or AUTOVIT_EQUIPMENT_RO.get(s, s)


def _dotari_items(vehicle: Dict[str, Any], value_map: Dict[str, Dict[str, str]]) -> List[str]:
    """Flat, de-duplicated equipment list drawn from every column that holds it.

    - equipment_options (TEXT[]): Autovit slugs saved by the current vehicle form
      -> translated via the Autovit taxonomy / value-map override.
    - equipment (JSONB) + optional_packages: already human-readable strings (or an
      Autovit flag/category dict) -> passed through the value-map ('equipment').
    """
    items = [_equipment_label(value_map, slug)
             for slug in _coerce_list(vehicle.get('equipment_options'))]
    items += [ro(value_map, 'equipment', item)
              for item in _coerce_list(vehicle.get('equipment')) + _coerce_list(vehicle.get('optional_packages'))]
    seen: set = set()
    out: List[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _extract_year(value: Any) -> Optional[int]:
    if isinstance(value, (datetime, date)):
        return value.year
    if isinstance(value, (int, float)):
        year = int(value)
        return year if 1900 <= year <= 2100 else None
    s = str(value).strip()
    if not s:
        return None
    m = re.search(r'(19|20)\d{2}', s)
    return int(m.group(0)) if m else None


def _apply_transform(row: Dict[str, Any], vehicle: Dict[str, Any],
                      value_map: Dict[str, Dict[str, str]]) -> Optional[str]:
    """Resolve one field-map row's value for the current vehicle, or None if empty."""
    source_expr = (row.get('source_expr') or '').strip()
    transform = row.get('transform') or 'raw'

    if transform == 'dotari' or source_expr.replace(' ', '') == 'equipment+optional_packages':
        items = _dotari_items(vehicle, value_map)
        return '\n'.join(items) if items else None

    raw_value = vehicle.get(source_expr)
    if (raw_value is None or raw_value == '') and source_expr == 'engine_power_kw':
        # Derive kW from metric horsepower when the kW column is not filled.
        hp = vehicle.get('engine_power_hp')
        if hp not in (None, ''):
            try:
                raw_value = round(float(hp) * HP_TO_KW)
            except (TypeError, ValueError):
                pass
    if raw_value is None or raw_value == '':
        return None

    if transform == 'raw':
        return str(raw_value)

    if transform == 'int':
        try:
            return str(int(float(raw_value)))
        except (TypeError, ValueError):
            return None

    if transform == 'year':
        year = _extract_year(raw_value)
        return str(year) if year else None

    if transform == 'ro_value':
        translated = ro(value_map, source_expr, raw_value)
        return translated or None

    if transform == 'ro_list':
        translated = ro(value_map, source_expr, raw_value)
        if not translated:
            return None
        return json.dumps([translated], ensure_ascii=False)

    # unknown transform -> raw fallback rather than dropping the field silently
    return str(raw_value)


def _description_html(vehicle: Dict[str, Any], spec_pairs: List[Tuple[str, str]],
                       dotari_items: List[str]) -> str:
    title = _title(vehicle)
    year = vehicle.get('year_of_manufacture') or ''
    parts = [f'<h3>{html.escape(str(title))} ({html.escape(str(year))})</h3>']

    # Anunț free-text from CarPark (listing_description): the marketing copy the
    # sales team wrote. Escaped, with newlines preserved as <br>.
    anunt = (vehicle.get('listing_description') or '').strip()
    if anunt:
        parts.append(f'<div>{html.escape(anunt).replace(chr(10), "<br>")}</div>')

    if spec_pairs:
        specs = ''.join(
            f'<li><strong>{html.escape(str(label))}:</strong> {html.escape(str(value))}</li>'
            for label, value in spec_pairs
        )
        parts.append(f'<h4>Specificații Tehnice:</h4><ul>{specs}</ul>')

    if dotari_items:
        dotari = ''.join(f'<li>{html.escape(str(item))}</li>' for item in dotari_items)
        parts.append(f'<h4>Dotări și Opțiuni:</h4><ul>{dotari}</ul>')

    return ''.join(parts)


def vehicle_to_product(vehicle: Dict[str, Any], photos: List[dict],
                        field_map: List[dict], value_map: Dict[str, Dict[str, str]],
                        config: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Build a Shopify ProductSetInput from a vehicle record.

    Caller must pass an eligible vehicle (see is_eligible) — a vehicle with no
    price will raise TypeError on price formatting.
    """
    warnings: List[str] = []
    metafields: List[dict] = []

    for row in field_map:
        if not row.get('is_active', True):
            continue
        target_namespace = row.get('target_namespace')
        target_key = row.get('target_key')
        if not row.get('last_seen_in_store', True):
            warnings.append(f'skipped stale field {target_namespace}.{target_key} (no longer in store)')
            continue
        value = _apply_transform(row, vehicle, value_map)
        if not value:
            warnings.append(f"empty value for {target_namespace}.{target_key} "
                             f"(source={row.get('source_expr')!r})")
            continue
        metafields.append({
            'namespace': target_namespace,
            'key': target_key,
            'type': row.get('target_type') or 'single_line_text_field',
            'value': value,
        })

    # Non-metafield product fields (fixed logic, independent of the field map,
    # but reusing the same RO value-map translation utility for consistency).
    fuel_ro = ro(value_map, 'fuel_type', vehicle.get('fuel_type'))
    gearbox_ro = ro(value_map, 'transmission', vehicle.get('transmission'))
    drive_ro = ro(value_map, 'drive_type', vehicle.get('drive_type'))
    color_ro = ro(value_map, 'color_exterior', vehicle.get('color_exterior'))

    raw_body = str(vehicle.get('body_type') or vehicle.get('vehicle_type') or '').strip()
    body_ro = BODY_TYPE_RO.get(raw_body, raw_body)

    spec_pairs: List[Tuple[str, str]] = []
    if fuel_ro:
        spec_pairs.append(('Combustibil', fuel_ro))
    if gearbox_ro:
        spec_pairs.append(('Cutie de viteze', gearbox_ro))
    if drive_ro:
        spec_pairs.append(('Tracțiune', drive_ro))
    if body_ro:
        spec_pairs.append(('Caroserie', body_ro))
    if color_ro:
        spec_pairs.append(('Culoare', color_ro))
    if vehicle.get('engine_displacement_cc'):
        spec_pairs.append(('Cilindree', f"{vehicle['engine_displacement_cc']} cm³"))
    if vehicle.get('engine_power_hp'):
        spec_pairs.append(('Putere', f"{vehicle['engine_power_hp']} CP"))
    if vehicle.get('mileage_km') not in (None, ''):
        spec_pairs.append(('Kilometraj', f"{vehicle['mileage_km']} km"))

    dotari_items = _dotari_items(vehicle, value_map)

    ordered_photos = sorted(photos, key=lambda p: (not p.get('is_primary'), p.get('sort_order', 0)))
    files = [{'originalSource': p['url'], 'contentType': 'IMAGE'} for p in ordered_photos if p.get('url')]

    price = _price(vehicle)
    year = vehicle.get('year_of_manufacture')
    tags = [t for t in [
        str(year) if year else None, gearbox_ro, fuel_ro, color_ro, body_ro,
        vehicle.get('brand'), vehicle.get('model'),
    ] if t]

    product_input: Dict[str, Any] = {
        'title': _title(vehicle),
        'descriptionHtml': _description_html(vehicle, spec_pairs, dotari_items),
        'vendor': config.get('vendor') or 'Autoworld',
        'productType': body_ro or 'Autovehicul',
        'templateSuffix': config.get('template_suffix'),
        'status': 'ACTIVE',
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
