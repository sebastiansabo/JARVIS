"""Parser for NW (New Cars) Excel/CSV exports from DMS."""

import hashlib
import logging
from .utils import read_file, safe_date, safe_decimal, safe_int, safe_str, normalize_columns

logger = logging.getLogger('jarvis.crm.parsers.nw')

# Column mapping: Excel header → DB field
COLUMN_MAP = {
    'Dealer': 'dealer_name',
    'Codul de dealer': 'dealer_code',
    'Filiala': 'branch',
    'Nr.Dos.': 'dossier_number',
    'Nr.comanda': 'order_number',
    'Data contr.vanzare': 'contract_date',
    'Data comanda': 'order_date',
    'An comanda': 'order_year',
    'Data livrarii': 'delivery_date',
    'Data factura client': 'invoice_date',
    'Data inmatricularii': 'registration_date',
    'Data intrarii': 'entry_date',
    'Nume model': 'model_name',
    'Cod caroserie': 'body_code',
    'Marca': 'brand',
    'Nr. de usi': 'door_count',
    'Tip vehicul': 'vehicle_type',
    'Cod model': 'model_code',
    'Cod motor': 'engine_code',
    'Combustibil': 'fuel_type',
    'Culoare': 'color',
    'Cod culoare': 'color_code',
    'Serie sasiu': 'vin',
    'AnulModelului': 'model_year',
    'Stare dos.': 'dossier_status',
    'Stare comanda': 'order_status',
    'Stare contract vanz.': 'contract_status',
    'Bruttopreis (Liste)': 'list_price',
    'Valoare discount pret total': 'discount_value',
    'Date op. alte costuri': 'other_costs',
    'Date op. pret achizitie net': 'purchase_price_net',
    'Date op. pret vanzare net': 'sale_price_net',
    'Date op. profit brut': 'gross_profit',
    'Client cf.contr.vanz.': 'buyer_name',
    'Client cf.contr.vanz. - Nume/Strada/Regiune/Loc.': 'buyer_address',
    'Proprietar cf.contr.vanzare': 'owner_name',
    'Proprietar cf.contr.vanzare - Adresare eticheta/Loc./Strada/Regiune': 'owner_address',
    'Abnehmergruppebezeichnung': 'customer_group',
    'Vanz.cf.contract vanz': 'sales_person',
    'Nr.Imatr.': 'registration_number',
}

# Extra columns → vehicle_specs JSONB
SPEC_COLUMNS = {
    'Cilindri': 'cylinders',
    'Clasa de emisii noxe': 'emission_class',
    'Emisii CO2': 'co2_emissions',
    'Masa proprie': 'weight',
    'Denumire cutie': 'gearbox',
    'Cod tapiterie': 'upholstery_code',
    'Denumire tapiterie': 'upholstery_name',
    'Cod echip. suplim.': 'equipment_code',
    'Serie motor': 'engine_serial',
    'Tuning motor': 'engine_tuning',
    'Daune acc.': 'damage_accident',
    'Daune accident reparate': 'damage_repaired',
    'Gr. produs': 'product_group',
    'Id.vehicul': 'vehicle_id',
    'Data CIV': 'civ_date',
    'Nr. CIV': 'civ_number',
}

DATE_FIELDS = {'contract_date', 'order_date', 'delivery_date', 'invoice_date',
               'registration_date', 'entry_date'}
DECIMAL_FIELDS = {'list_price', 'discount_value', 'other_costs',
                  'purchase_price_net', 'sale_price_net', 'gross_profit'}
INT_FIELDS = {'door_count', 'model_year', 'order_year'}


def parse_nw(file_path):
    """Parse NW Excel/CSV and yield (dossier_number, row_hash, row_data) tuples."""
    import json
    # Try 'Deals' sheet (unified template), fall back to first sheet
    df = read_file(file_path, sheet_name='Deals')
    if df is None or df.empty:
        df = read_file(file_path)
    if df is None or df.empty:
        logger.warning(f'No data in NW file: {file_path}')
        return

    # Accept both Romanian DMS headers and DB field names
    df = normalize_columns(df, COLUMN_MAP)
    df = normalize_columns(df, SPEC_COLUMNS)

    # Unified template: filter to NW rows only if source column exists
    if 'source' in df.columns:
        df = df[df['source'].str.strip().str.lower() == 'nw']

    for _, row in df.iterrows():
        data = {}
        specs = {}

        # Map main columns (use DB field names after normalization)
        for db_field in COLUMN_MAP.values():
            val = row.get(db_field)
            if db_field in DATE_FIELDS:
                data[db_field] = safe_date(val)
            elif db_field in DECIMAL_FIELDS:
                data[db_field] = safe_decimal(val)
            elif db_field in INT_FIELDS:
                data[db_field] = safe_int(val)
            else:
                data[db_field] = safe_str(val)

        # Map spec columns to JSONB
        for spec_key in SPEC_COLUMNS.values():
            val = row.get(spec_key)
            v = safe_str(val)
            if v:
                specs[spec_key] = v
        if specs:
            data['vehicle_specs'] = json.dumps(specs)

        dossier_number = data.get('dossier_number')
        if not dossier_number:
            continue

        # Row hash for change detection
        hash_input = f"nw|{dossier_number}|{data.get('buyer_name', '')}|{data.get('dossier_status', '')}"
        row_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:16]

        yield dossier_number, row_hash, data
