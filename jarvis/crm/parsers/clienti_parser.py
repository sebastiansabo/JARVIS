"""Parser for Clienti (DMS client-vehicle lists) Excel exports.

Each row represents one vehicle belonging to a client. The same client name
appears on multiple rows — deduplication is handled by the import service.
"""

import hashlib
import logging
from .utils import (read_file, safe_date, safe_decimal, safe_int, safe_str,
                    normalize_columns, normalize_phone, normalize_name)

logger = logging.getLogger('jarvis.crm.parsers.clienti')

# Excel header → internal field name
COLUMN_MAP = {
    # Client identity
    'Numele':                                                   'display_name',
    'Persoana de contact':                                      'contact_person',
    'Legaturi telefonice client/partener':                      'phones_raw',
    'Nr.Telefon (1)':                                           'phone_primary',
    'Alocare client/partener la unitati':                       'dealer_codes_raw',
    'Alocari client/partener la vanzator':                      'salesperson',
    'Adresa#':                                                  'address_raw',
    # Revenue
    'Cl-Venit NW (total)':                                      'revenue_nw',
    'Cl-Venit GW (total)':                                      'revenue_gw',
    # Service history
    'Data ultim.vizita service':                                'last_service_date',
    'Ultimul consilier al clientului/partenerului':              'last_service_advisor',
    'Data ultimului consilier (al clientului/partenerului)':     'last_advisor_date',
    # Vehicle data (one per row)
    'Nume model':                                               'vehicle_model',
    'Serie sasiu':                                              'vin',
    'Nr.Imatr.':                                                'license_plate',
    'AnulModelului':                                            'vehicle_year',
    'Data livrarii':                                            'purchase_date',
    'Rulaj vehic. (total)':                                     'estimated_mileage',
}

DATE_FIELDS = {'last_service_date', 'last_advisor_date', 'purchase_date'}
DECIMAL_FIELDS = {'revenue_nw', 'revenue_gw'}
INT_FIELDS = {'vehicle_year', 'estimated_mileage'}


def _split_phones(raw):
    """Split semicolon-separated phone string into list of {phone, phone_raw} dicts."""
    if not raw:
        return []
    parts = [p.strip() for p in str(raw).split(';') if p.strip()]
    result = []
    seen = set()
    for p in parts:
        normalized, raw_val = normalize_phone(p)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append({'phone': normalized, 'phone_raw': raw_val})
    return result


def _split_dealer_codes(raw):
    """Split semicolon-separated dealer codes into a list."""
    if not raw:
        return []
    return [c.strip() for c in str(raw).split(';') if c.strip()]


def _parse_address(raw):
    """Best-effort split of 'City, Street, Nr. X' into city/street components."""
    if not raw:
        return None, None, None
    parts = [p.strip() for p in str(raw).split(',')]
    if len(parts) >= 3:
        # Typical: "Bucuresti, Sector 2, Strada X, Nr. Y"
        city = parts[0]
        region = parts[1] if 'sector' in parts[1].lower() or 'jud' in parts[1].lower() else None
        street = ', '.join(parts[2:]) if region else ', '.join(parts[1:])
        return city, street, region
    elif len(parts) == 2:
        return parts[0], parts[1], None
    else:
        return None, raw, None


def parse_clienti(file_path):
    """Parse Clienti Excel and yield (client_key, row_hash, client_data, vehicle_data) tuples.

    client_key: normalized display_name for dedup cache
    row_hash: SHA256-based hash for change detection
    client_data: dict with client-level fields
    vehicle_data: dict with vehicle-level fields
    """
    df = read_file(file_path)
    if df is None or df.empty:
        logger.warning(f'No data in Clienti file: {file_path}')
        return

    df = normalize_columns(df, COLUMN_MAP)

    for _, row in df.iterrows():
        display_name = safe_str(row.get('display_name'))
        if not display_name:
            continue

        client_key = normalize_name(display_name)

        # -- Client-level data --
        phones_raw = safe_str(row.get('phones_raw'))
        phone_primary = safe_str(row.get('phone_primary'))
        phones = _split_phones(phones_raw)

        # If phone_primary exists but wasn't in the phones_raw list, add it
        if phone_primary:
            primary_norm, primary_raw = normalize_phone(phone_primary)
            if primary_norm:
                existing_nums = {p['phone'] for p in phones}
                if primary_norm not in existing_nums:
                    phones.insert(0, {'phone': primary_norm, 'phone_raw': primary_raw})

        dealer_codes = _split_dealer_codes(safe_str(row.get('dealer_codes_raw')))
        city, street, region = _parse_address(safe_str(row.get('address_raw')))

        client_data = {
            'display_name': display_name,
            'contact_person': safe_str(row.get('contact_person')),
            'phones': phones,
            'phone_primary_raw': phone_primary,
            'dealer_codes': dealer_codes or None,
            'salesperson': safe_str(row.get('salesperson')),
            'city': city,
            'street': street,
            'region': region,
            'revenue_nw': safe_decimal(row.get('revenue_nw')),
            'revenue_gw': safe_decimal(row.get('revenue_gw')),
            'last_service_date': safe_date(row.get('last_service_date')),
            'last_service_advisor': safe_str(row.get('last_service_advisor')),
            'last_advisor_date': safe_date(row.get('last_advisor_date')),
        }

        # -- Vehicle-level data --
        vin = safe_str(row.get('vin'))
        license_plate = safe_str(row.get('license_plate'))

        vehicle_data = {
            'vehicle_model': safe_str(row.get('vehicle_model')),
            'vin': vin,
            'license_plate': license_plate,
            'vehicle_year': safe_int(row.get('vehicle_year')),
            'purchase_date': safe_date(row.get('purchase_date')),
            'estimated_mileage': safe_int(row.get('estimated_mileage')),
        }

        # Row hash for change detection (unique per vehicle row)
        hash_input = f"clienti|{display_name}|{vin or ''}|{license_plate or ''}"
        row_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:16]

        yield client_key, row_hash, client_data, vehicle_data
