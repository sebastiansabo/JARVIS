"""Parser for CRM Clients Excel/CSV exports — supports both Workleto and unified template formats."""

import hashlib
import logging
from .utils import read_file, safe_date, safe_str, normalize_columns

logger = logging.getLogger('jarvis.crm.parsers.clients')

# Romanian Workleto headers → DB field names
COLUMN_MAP = {
    'Denumire client': 'display_name',
    'Tip client': 'client_type_raw',
    'Adresa': 'address',
    'Telefon': 'phone',
    'E-mail': 'email',
    'Responsabil': 'responsible',
    'Data adaugarii': 'added_date',
}

# Unified template uses these DB field names directly
UNIFIED_FIELDS = {
    'display_name', 'client_type', 'phone', 'email',
    'company_name', 'street', 'city', 'region', 'responsible',
}


def parse_crm_clients(file_path):
    """Parse CRM Clients Excel/CSV and yield (row_hash, row_data) tuples."""
    # Try 'Clients' sheet (unified template), fall back to first sheet
    df = read_file(file_path, sheet_name='Clients')
    if df is None or df.empty:
        df = read_file(file_path)
    if df is None or df.empty:
        logger.warning(f'No data in CRM Clients file: {file_path}')
        return

    # Detect format: unified template uses DB field names, Workleto uses Romanian headers
    is_unified = 'display_name' in df.columns
    if not is_unified:
        df = normalize_columns(df, COLUMN_MAP)

    for _, row in df.iterrows():
        data = {}

        if is_unified:
            # Unified template — read DB field names directly
            for field in UNIFIED_FIELDS:
                val = row.get(field)
                data[field] = safe_str(val)
            # client_type already comes as 'person' or 'company'
            if data.get('client_type') not in ('person', 'company'):
                data['client_type'] = 'person'
        else:
            # Workleto format
            for db_field in COLUMN_MAP.values():
                val = row.get(db_field)
                if db_field == 'added_date':
                    data[db_field] = safe_date(val)
                else:
                    data[db_field] = safe_str(val)
            # Normalize client type from Romanian
            raw_type = data.pop('client_type_raw', '') or ''
            if 'juridica' in raw_type.lower():
                data['client_type'] = 'company'
            else:
                data['client_type'] = 'person'

        display_name = data.get('display_name')
        if not display_name:
            continue

        hash_input = f"crm|{display_name}|{data.get('phone', '')}|{data.get('email', '')}"
        row_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:16]

        yield row_hash, data
