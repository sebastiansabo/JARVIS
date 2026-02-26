"""Parser for GW (Used Cars / Gebrauchtwagen) Excel/CSV exports from DMS."""

import hashlib
import logging
from .utils import read_file, safe_date, safe_decimal, safe_int, safe_str, normalize_columns

logger = logging.getLogger('jarvis.crm.parsers.gw')

COLUMN_MAP = {
    'Dealer': 'dealer_name',
    'Codul de dealer': 'dealer_code',
    'Filiala conf.det.dos.': 'branch',
    'Nr.Dos.': 'dossier_number',
    'Nr.comanda': 'order_number',
    'Data contr.vanzare': 'contract_date',
    'Data livrarii': 'delivery_date',
    'Data factura client': 'invoice_date',
    'Stare dos.': 'dossier_status',
    'Nume model': 'model_name',
    'Cod caroserie': 'body_code',
    'AnulModelului': 'model_year',
    'Marca': 'brand',
    'Nr. de usi': 'door_count',
    'Cod model': 'model_code',
    'Cod motor': 'engine_code',
    'Combustibil': 'fuel_type',
    'Culoare': 'color',
    'Serie sasiu': 'vin',
    'Data inmatricularii': 'registration_date',
    'PV brut': 'gw_gross_value',
    'Abnehmergruppebezeichnung': 'customer_group',
    'Client cf.contr.vanz.': 'buyer_name',
    'Proprietar cf.contr.vanzare': 'owner_name',
    'Proprietar cf.contr.vanzare - Adresare eticheta': 'owner_address',
    'Client cf.contr.vanz. - Loc./Strada/Regiune': 'buyer_address',
    'Proprietar cf.contr.vanzare - Strada/Regiune': '_owner_address_2',
}

# Extra DB fields accepted from unified template (not in DMS export)
UNIFIED_EXTRA = {
    'order_date', 'entry_date', 'order_year', 'color_code', 'vehicle_type',
    'list_price', 'purchase_price_net', 'sale_price_net', 'gross_profit',
    'discount_value', 'other_costs', 'order_status', 'contract_status',
    'sales_person', 'registration_number',
}

DATE_FIELDS = {'contract_date', 'delivery_date', 'invoice_date', 'registration_date',
               'order_date', 'entry_date'}
DECIMAL_FIELDS = {'gw_gross_value', 'list_price', 'purchase_price_net', 'sale_price_net',
                  'gross_profit', 'discount_value', 'other_costs'}
INT_FIELDS = {'door_count', 'model_year', 'order_year'}


def parse_gw(file_path):
    """Parse GW Excel/CSV and yield (dossier_number, row_hash, row_data) tuples."""
    # Try 'Deals' sheet (unified template), fall back to first sheet
    df = read_file(file_path, sheet_name='Deals')
    if df is None or df.empty:
        df = read_file(file_path)
    if df is None or df.empty:
        logger.warning(f'No data in GW file: {file_path}')
        return

    # Accept both Romanian DMS headers and DB field names
    df = normalize_columns(df, COLUMN_MAP)

    # Unified template: filter to GW rows only if source column exists
    if 'source' in df.columns:
        df = df[df['source'].str.strip().str.lower() == 'gw']

    for _, row in df.iterrows():
        data = {}

        all_fields = {v for v in COLUMN_MAP.values() if not v.startswith('_')} | UNIFIED_EXTRA
        for db_field in all_fields:
            val = row.get(db_field)
            if db_field in DATE_FIELDS:
                data[db_field] = safe_date(val)
            elif db_field in DECIMAL_FIELDS:
                data[db_field] = safe_decimal(val)
            elif db_field in INT_FIELDS:
                data[db_field] = safe_int(val)
            else:
                data[db_field] = safe_str(val)

        # Combine owner address fields (from Romanian DMS format)
        addr2 = safe_str(row.get('_owner_address_2'))
        if addr2 and data.get('owner_address'):
            data['owner_address'] = f"{data['owner_address']}, {addr2}"
        elif addr2:
            data['owner_address'] = addr2

        dossier_number = data.get('dossier_number')
        if not dossier_number:
            continue

        hash_input = f"gw|{dossier_number}|{data.get('buyer_name', '')}|{data.get('dossier_status', '')}"
        row_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:16]

        yield dossier_number, row_hash, data
