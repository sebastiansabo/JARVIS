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

def import_deals(file_path, user_id):
    """Import deals. Columns = DB field names. source + dossier_number required."""
    df = _read_sheet(file_path, 'Deals')
    if df is None or df.empty:
        return {'total': 0, 'errors': ['No data found in file']}

    batch = _import_repo.create('deals', file_path.split('/')[-1], user_id)
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


def import_clients(file_path, user_id):
    """Import clients. Columns = DB field names. display_name required."""
    df = _read_sheet(file_path, 'Clients')
    if df is None or df.empty:
        return {'total': 0, 'errors': ['No data found in file']}

    batch = _import_repo.create('crm_clients', file_path.split('/')[-1], user_id)
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

def import_nw(file_path, user_id):
    from ..parsers import parse_nw
    batch = _import_repo.create('nw', file_path.split('/')[-1], user_id)
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


def import_gw(file_path, user_id):
    from ..parsers import parse_gw
    batch = _import_repo.create('gw', file_path.split('/')[-1], user_id)
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


def import_crm_clients(file_path, user_id):
    from ..parsers import parse_crm_clients
    batch = _import_repo.create('crm_clients', file_path.split('/')[-1], user_id)
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


# Dispatch map
IMPORT_HANDLERS = {
    # Direct (unified template — DB column names)
    'deals': import_deals,
    'clients': import_clients,
    # Legacy (Romanian DMS headers)
    'nw': import_nw,
    'gw': import_gw,
    'crm_clients': import_crm_clients,
}
