"""CRM Import Service — reads Excel/CSV with DB column names and inserts directly."""

import hashlib
import logging
import pandas as pd
from ..repositories import ClientRepository, DealRepository, ImportRepository
from ..parsers.utils import normalize_phone, normalize_name, safe_str, safe_date, safe_decimal, safe_int

logger = logging.getLogger('jarvis.crm.services.import')

_client_repo = ClientRepository()
_deal_repo = DealRepository()
_import_repo = ImportRepository()

# ── Allowed DB columns per table (excludes auto-generated: id, created_at, etc.) ──

DEAL_COLS = {
    'source', 'dealer_code', 'dealer_name', 'branch', 'dossier_number', 'order_number',
    'contract_date', 'order_date', 'delivery_date', 'invoice_date', 'registration_date',
    'entry_date', 'brand', 'model_name', 'model_code', 'model_year', 'body_code', 'vin',
    'engine_code', 'fuel_type', 'color', 'color_code', 'door_count', 'vehicle_type',
    'list_price', 'purchase_price_net', 'sale_price_net', 'gross_profit', 'discount_value',
    'other_costs', 'gw_gross_value', 'dossier_status', 'order_status', 'contract_status',
    'sales_person', 'buyer_name', 'buyer_address', 'owner_name', 'owner_address',
    'customer_group', 'registration_number', 'order_year',
}
DEAL_DATE_COLS = {'contract_date', 'order_date', 'delivery_date', 'invoice_date',
                  'registration_date', 'entry_date'}
DEAL_DECIMAL_COLS = {'list_price', 'purchase_price_net', 'sale_price_net', 'gross_profit',
                     'discount_value', 'other_costs', 'gw_gross_value'}
DEAL_INT_COLS = {'door_count', 'model_year', 'order_year'}

CLIENT_COLS = {
    'display_name', 'client_type', 'phone', 'email', 'company_name',
    'street', 'city', 'region', 'responsible',
}


def _coerce_row(row, allowed_cols, date_cols, decimal_cols, int_cols=None):
    """Read a pandas row, keep only allowed columns, coerce types."""
    data = {}
    for col in allowed_cols:
        val = row.get(col)
        if col in date_cols:
            data[col] = safe_date(val)
        elif col in decimal_cols:
            data[col] = safe_decimal(val)
        elif int_cols and col in int_cols:
            data[col] = safe_int(val)
        else:
            data[col] = safe_str(val)
    return {k: v for k, v in data.items() if v is not None}


def _match_or_create_client(display_name, phone_raw=None, email=None,
                            client_type='person', responsible=None,
                            street=None, city=None, region=None,
                            company_name=None, source_key='crm'):
    """Find existing client by phone or name, or create new. Returns (client_id, is_new)."""
    phone, phone_raw_out = normalize_phone(phone_raw)
    name_norm = normalize_name(display_name)

    if phone:
        existing = _client_repo.find_by_phone(phone)
        if existing:
            _client_repo.update_source_flags(existing['id'], source_key)
            return existing['id'], False

    if name_norm:
        try:
            existing = _client_repo.find_by_name_trigram(name_norm, threshold=0.7)
            if existing:
                _client_repo.update_source_flags(existing['id'], source_key)
                return existing['id'], False
        except Exception:
            pass

    result = _client_repo.create(
        display_name=display_name,
        name_normalized=name_norm,
        client_type=client_type,
        phone=phone,
        phone_raw=phone_raw_out,
        email=email,
        street=street,
        city=city,
        region=region,
        company_name=company_name if client_type == 'company' else None,
        responsible=responsible,
        source_flags={source_key: True},
    )
    return result['id'], True


def _read_sheet(file_path, sheet_name):
    """Read a specific sheet, fall back to first sheet if not found."""
    try:
        if file_path.endswith('.csv'):
            return pd.read_csv(file_path, dtype=str, keep_default_na=False)
        return pd.read_excel(file_path, sheet_name=sheet_name, dtype=str, keep_default_na=False)
    except (ValueError, KeyError):
        return pd.read_excel(file_path, dtype=str, keep_default_na=False)
    except Exception as e:
        logger.error(f'Failed to read {file_path}: {e}')
        return None


# ════════════════════════════════════════════════════════════════
# Direct importers — template columns = DB columns
# ════════════════════════════════════════════════════════════════

def import_deals(file_path, user_id, original_filename=None):
    """Import deals. Columns = DB field names. source + dossier_number required."""
    df = _read_sheet(file_path, 'Deals')
    if df is None or df.empty:
        return {'total': 0, 'errors': ['No data found in file']}

    batch = _import_repo.create('deals', original_filename or file_path.split('/')[-1], user_id)
    batch_id = batch['id']
    stats = {'total': 0, 'new': 0, 'updated': 0, 'skipped': 0,
             'new_clients': 0, 'matched_clients': 0, 'errors': []}

    try:
        for _, row in df.iterrows():
            stats['total'] += 1
            try:
                data = _coerce_row(row, DEAL_COLS, DEAL_DATE_COLS, DEAL_DECIMAL_COLS, DEAL_INT_COLS)

                source = data.get('source')
                dossier = data.get('dossier_number')
                if not source or source not in ('nw', 'gw'):
                    stats['errors'].append(f"Row {stats['total']}: invalid source (must be nw or gw)")
                    stats['skipped'] += 1
                    continue
                if not dossier:
                    stats['errors'].append(f"Row {stats['total']}: missing dossier_number")
                    stats['skipped'] += 1
                    continue

                buyer_name = data.get('buyer_name')
                if buyer_name:
                    cid, is_new = _match_or_create_client(display_name=buyer_name, source_key=source)
                    data['client_id'] = cid
                    stats['new_clients' if is_new else 'matched_clients'] += 1

                hash_input = f"{source}|{dossier}|{buyer_name or ''}|{data.get('dossier_status', '')}"
                row_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:16]

                _, is_new = _deal_repo.upsert(source, dossier, row_hash, data, batch_id)
                stats['new' if is_new else 'updated'] += 1
            except Exception as e:
                stats['errors'].append(f"Row {stats['total']}: {str(e)[:200]}")
                stats['skipped'] += 1

        _import_repo.update_stats(batch_id, total_rows=stats['total'], new_rows=stats['new'],
                                  updated_rows=stats['updated'], skipped_rows=stats['skipped'],
                                  new_clients=stats['new_clients'], matched_clients=stats['matched_clients'],
                                  status='completed', error_log=stats['errors'][:100])
    except Exception as e:
        _import_repo.update_stats(batch_id, status='failed', error_log=[str(e)[:500]])
        stats['errors'].append(str(e))
    return stats


def import_clients(file_path, user_id, original_filename=None):
    """Import clients. Columns = DB field names. display_name required."""
    df = _read_sheet(file_path, 'Clients')
    if df is None or df.empty:
        return {'total': 0, 'errors': ['No data found in file']}

    batch = _import_repo.create('crm_clients', original_filename or file_path.split('/')[-1], user_id)
    batch_id = batch['id']
    stats = {'total': 0, 'new': 0, 'updated': 0, 'skipped': 0,
             'new_clients': 0, 'matched_clients': 0, 'errors': []}

    try:
        for _, row in df.iterrows():
            stats['total'] += 1
            try:
                data = _coerce_row(row, CLIENT_COLS, set(), set())

                display_name = data.get('display_name')
                if not display_name:
                    stats['skipped'] += 1
                    continue

                client_type = data.get('client_type', 'person')
                if client_type not in ('person', 'company'):
                    client_type = 'person'

                cid, is_new = _match_or_create_client(
                    display_name=display_name, phone_raw=data.get('phone'),
                    email=data.get('email'), client_type=client_type,
                    responsible=data.get('responsible'), street=data.get('street'),
                    city=data.get('city'), region=data.get('region'),
                    company_name=data.get('company_name'), source_key='crm')
                if is_new:
                    stats['new_clients'] += 1
                    stats['new'] += 1
                else:
                    stats['matched_clients'] += 1
                    stats['skipped'] += 1
            except Exception as e:
                stats['errors'].append(f"Row {stats['total']}: {str(e)[:200]}")
                stats['skipped'] += 1

        _import_repo.update_stats(batch_id, total_rows=stats['total'], new_rows=stats['new'],
                                  updated_rows=stats['updated'], skipped_rows=stats['skipped'],
                                  new_clients=stats['new_clients'], matched_clients=stats['matched_clients'],
                                  status='completed', error_log=stats['errors'][:100])
    except Exception as e:
        _import_repo.update_stats(batch_id, status='failed', error_log=[str(e)[:500]])
        stats['errors'].append(str(e))
    return stats


# ── Legacy importers (Romanian DMS column headers) ──

def import_nw(file_path, user_id, original_filename=None):
    from ..parsers import parse_nw
    batch = _import_repo.create('nw', original_filename or file_path.split('/')[-1], user_id)
    batch_id = batch['id']
    stats = {'total': 0, 'new': 0, 'updated': 0, 'skipped': 0,
             'new_clients': 0, 'matched_clients': 0, 'errors': []}
    try:
        for dossier_number, row_hash, data in parse_nw(file_path):
            stats['total'] += 1
            try:
                buyer = data.get('buyer_name')
                if buyer:
                    cid, is_new = _match_or_create_client(display_name=buyer, source_key='nw')
                    data['client_id'] = cid
                    stats['new_clients' if is_new else 'matched_clients'] += 1
                _, is_new = _deal_repo.upsert('nw', dossier_number, row_hash, data, batch_id)
                stats['new' if is_new else 'updated'] += 1
            except Exception as e:
                stats['errors'].append(f'Row {stats["total"]}: {str(e)[:200]}')
                stats['skipped'] += 1
        _import_repo.update_stats(batch_id, total_rows=stats['total'], new_rows=stats['new'],
                                  updated_rows=stats['updated'], skipped_rows=stats['skipped'],
                                  new_clients=stats['new_clients'], matched_clients=stats['matched_clients'],
                                  status='completed', error_log=stats['errors'][:100])
    except Exception as e:
        _import_repo.update_stats(batch_id, status='failed', error_log=[str(e)[:500]])
        stats['errors'].append(str(e))
    return stats


def import_gw(file_path, user_id, original_filename=None):
    from ..parsers import parse_gw
    batch = _import_repo.create('gw', original_filename or file_path.split('/')[-1], user_id)
    batch_id = batch['id']
    stats = {'total': 0, 'new': 0, 'updated': 0, 'skipped': 0,
             'new_clients': 0, 'matched_clients': 0, 'errors': []}
    try:
        for dossier_number, row_hash, data in parse_gw(file_path):
            stats['total'] += 1
            try:
                buyer = data.get('buyer_name')
                if buyer:
                    cid, is_new = _match_or_create_client(display_name=buyer, source_key='gw')
                    data['client_id'] = cid
                    stats['new_clients' if is_new else 'matched_clients'] += 1
                _, is_new = _deal_repo.upsert('gw', dossier_number, row_hash, data, batch_id)
                stats['new' if is_new else 'updated'] += 1
            except Exception as e:
                stats['errors'].append(f'Row {stats["total"]}: {str(e)[:200]}')
                stats['skipped'] += 1
        _import_repo.update_stats(batch_id, total_rows=stats['total'], new_rows=stats['new'],
                                  updated_rows=stats['updated'], skipped_rows=stats['skipped'],
                                  new_clients=stats['new_clients'], matched_clients=stats['matched_clients'],
                                  status='completed', error_log=stats['errors'][:100])
    except Exception as e:
        _import_repo.update_stats(batch_id, status='failed', error_log=[str(e)[:500]])
        stats['errors'].append(str(e))
    return stats


def import_crm_clients(file_path, user_id, original_filename=None):
    from ..parsers import parse_crm_clients
    batch = _import_repo.create('crm_clients', original_filename or file_path.split('/')[-1], user_id)
    batch_id = batch['id']
    stats = {'total': 0, 'new': 0, 'updated': 0, 'skipped': 0,
             'new_clients': 0, 'matched_clients': 0, 'errors': []}
    try:
        for row_hash, data in parse_crm_clients(file_path):
            stats['total'] += 1
            try:
                cid, is_new = _match_or_create_client(
                    display_name=data.get('display_name'), phone_raw=data.get('phone'),
                    email=data.get('email'), client_type=data.get('client_type', 'person'),
                    responsible=data.get('responsible'), source_key='crm')
                if is_new:
                    stats['new_clients'] += 1
                    stats['new'] += 1
                else:
                    stats['matched_clients'] += 1
                    stats['skipped'] += 1
            except Exception as e:
                stats['errors'].append(f'Row {stats["total"]}: {str(e)[:200]}')
                stats['skipped'] += 1
        _import_repo.update_stats(batch_id, total_rows=stats['total'], new_rows=stats['new'],
                                  updated_rows=stats['updated'], skipped_rows=stats['skipped'],
                                  new_clients=stats['new_clients'], matched_clients=stats['matched_clients'],
                                  status='completed', error_log=stats['errors'][:100])
    except Exception as e:
        _import_repo.update_stats(batch_id, status='failed', error_log=[str(e)[:500]])
        stats['errors'].append(str(e))
    return stats


# ── Clienti importer (DMS client-vehicle lists) ──

def _update_client_extra(client_id, client_data):
    """Update contact_person, dealer_codes, phones, revenue, and service history."""
    import json

    # 1. contact_person + dealer_codes on crm_clients
    contact_person = client_data.get('contact_person')
    dealer_codes = client_data.get('dealer_codes')
    salesperson = client_data.get('salesperson')
    city = client_data.get('city')
    street = client_data.get('street')
    region = client_data.get('region')

    updates, params = [], []
    if contact_person:
        updates.append('contact_person = COALESCE(%s, contact_person)')
        params.append(contact_person)
    if dealer_codes:
        updates.append('dealer_codes = COALESCE(%s, dealer_codes)')
        params.append(dealer_codes)
    if salesperson:
        updates.append('responsible = COALESCE(%s, responsible)')
        params.append(salesperson)
    if city:
        updates.append('city = COALESCE(%s, city)')
        params.append(city)
    if street:
        updates.append('street = COALESCE(%s, street)')
        params.append(street)
    if region:
        updates.append('region = COALESCE(%s, region)')
        params.append(region)
    if updates:
        updates.append('updated_at = NOW()')
        params.append(client_id)
        _client_repo.execute(
            f"UPDATE crm_clients SET {', '.join(updates)} WHERE id = %s",
            tuple(params)
        )

    # 2. Phones → client_phones table (ON CONFLICT skip)
    for phone_entry in client_data.get('phones', []):
        try:
            _client_repo.execute(
                '''INSERT INTO client_phones (client_id, phone, phone_raw, source)
                   VALUES (%s, %s, %s, 'clienti')
                   ON CONFLICT (client_id, phone) DO NOTHING''',
                (client_id, phone_entry['phone'], phone_entry.get('phone_raw'))
            )
        except Exception:
            pass  # skip individual phone errors

    # 3. Revenue + service history → client_profiles (upsert)
    revenue_nw = client_data.get('revenue_nw')
    revenue_gw = client_data.get('revenue_gw')
    last_service_date = client_data.get('last_service_date')
    last_service_advisor = client_data.get('last_service_advisor')
    last_advisor_date = client_data.get('last_advisor_date')

    if any(v is not None for v in [revenue_nw, revenue_gw, last_service_date,
                                    last_service_advisor, last_advisor_date]):
        _client_repo.execute(
            '''INSERT INTO client_profiles (client_id, revenue_nw, revenue_gw,
                   last_service_date, last_service_advisor, last_advisor_date)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (client_id) DO UPDATE SET
                   revenue_nw = COALESCE(EXCLUDED.revenue_nw, client_profiles.revenue_nw),
                   revenue_gw = COALESCE(EXCLUDED.revenue_gw, client_profiles.revenue_gw),
                   last_service_date = GREATEST(EXCLUDED.last_service_date, client_profiles.last_service_date),
                   last_service_advisor = COALESCE(EXCLUDED.last_service_advisor, client_profiles.last_service_advisor),
                   last_advisor_date = GREATEST(EXCLUDED.last_advisor_date, client_profiles.last_advisor_date),
                   updated_at = NOW()''',
            (client_id, revenue_nw, revenue_gw,
             last_service_date, last_service_advisor, last_advisor_date)
        )


def _upsert_fleet_vehicle(client_id, vehicle_data, batch_id):
    """Insert or update a client_fleet vehicle, deduplicating by VIN or license plate."""
    vin = vehicle_data.get('vin')
    plate = vehicle_data.get('license_plate')

    if not vin and not plate:
        return  # no way to identify the vehicle

    # Try to find existing by VIN first, then by plate
    existing = None
    if vin:
        existing = _client_repo.query_one(
            'SELECT id FROM client_fleet WHERE client_id = %s AND vin = %s',
            (client_id, vin)
        )
    if not existing and plate:
        existing = _client_repo.query_one(
            'SELECT id FROM client_fleet WHERE client_id = %s AND license_plate = %s',
            (client_id, plate)
        )

    if existing:
        _client_repo.execute(
            '''UPDATE client_fleet
               SET vehicle_model = COALESCE(%s, vehicle_model),
                   vehicle_year = COALESCE(%s, vehicle_year),
                   vin = COALESCE(%s, vin),
                   license_plate = COALESCE(%s, license_plate),
                   purchase_date = COALESCE(%s, purchase_date),
                   estimated_mileage = COALESCE(%s, estimated_mileage),
                   import_batch_id = %s,
                   updated_at = NOW()
               WHERE id = %s''',
            (vehicle_data.get('vehicle_model'), vehicle_data.get('vehicle_year'),
             vin, plate, vehicle_data.get('purchase_date'),
             vehicle_data.get('estimated_mileage'),
             batch_id, existing['id'])
        )
    else:
        _client_repo.execute(
            '''INSERT INTO client_fleet
               (client_id, vehicle_model, vehicle_year, vin, license_plate,
                purchase_date, estimated_mileage, import_batch_id, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active')''',
            (client_id, vehicle_data.get('vehicle_model'), vehicle_data.get('vehicle_year'),
             vin, plate, vehicle_data.get('purchase_date'),
             vehicle_data.get('estimated_mileage'), batch_id)
        )


def import_clienti(file_path, user_id, original_filename=None):
    """Import Clienti Excel (DMS client-vehicle lists). One row = one vehicle per client."""
    from ..parsers import parse_clienti
    batch = _import_repo.create('clienti', original_filename or file_path.split('/')[-1], user_id)
    batch_id = batch['id']
    stats = {'total': 0, 'new': 0, 'updated': 0, 'skipped': 0,
             'new_clients': 0, 'matched_clients': 0,
             'fleet_created': 0, 'fleet_updated': 0, 'errors': []}

    # Dedup cache: normalized_name → client_id (avoids redundant DB lookups)
    client_cache = {}

    try:
        for client_key, row_hash, client_data, vehicle_data in parse_clienti(file_path):
            stats['total'] += 1
            try:
                # 1. Resolve client (dedup via in-memory cache)
                if client_key in client_cache:
                    client_id = client_cache[client_key]
                else:
                    # Use primary phone for matching
                    phone_raw = client_data.get('phone_primary_raw')
                    if not phone_raw:
                        phones = client_data.get('phones', [])
                        phone_raw = phones[0]['phone_raw'] if phones else None

                    cid, is_new = _match_or_create_client(
                        display_name=client_data['display_name'],
                        phone_raw=phone_raw,
                        street=client_data.get('street'),
                        city=client_data.get('city'),
                        region=client_data.get('region'),
                        responsible=client_data.get('salesperson'),
                        source_key='clienti',
                    )
                    client_id = cid
                    client_cache[client_key] = client_id
                    stats['new_clients' if is_new else 'matched_clients'] += 1

                    # 2. Update client-level extra fields (once per unique client)
                    try:
                        _update_client_extra(client_id, client_data)
                    except Exception as e:
                        stats['errors'].append(f"Row {stats['total']}: client extra update: {str(e)[:150]}")

                # 3. Create/update fleet vehicle
                try:
                    _upsert_fleet_vehicle(client_id, vehicle_data, batch_id)
                    stats['new'] += 1
                except Exception as e:
                    stats['errors'].append(f"Row {stats['total']}: fleet upsert: {str(e)[:150]}")
                    stats['skipped'] += 1

            except Exception as e:
                stats['errors'].append(f"Row {stats['total']}: {str(e)[:200]}")
                stats['skipped'] += 1

        _import_repo.update_stats(batch_id, total_rows=stats['total'], new_rows=stats['new'],
                                  updated_rows=stats['updated'], skipped_rows=stats['skipped'],
                                  new_clients=stats['new_clients'], matched_clients=stats['matched_clients'],
                                  status='completed', error_log=stats['errors'][:100])
    except Exception as e:
        _import_repo.update_stats(batch_id, status='failed', error_log=[str(e)[:500]])
        stats['errors'].append(str(e))
    return stats


# Dispatch map
IMPORT_HANDLERS = {
    # Direct (unified template — DB column names)
    'deals': import_deals,
    'clients': import_clients,
    # Legacy (Romanian DMS headers)
    'nw': import_nw,
    'gw': import_gw,
    'crm_clients': import_crm_clients,
    # Clienti (DMS client-vehicle lists)
    'clienti': import_clienti,
}
