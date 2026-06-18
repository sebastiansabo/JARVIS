"""BAB .xlsx parser — extracts account lines from ERP BAB export."""
import io
from decimal import Decimal, InvalidOperation

import openpyxl


# Column name mappings (case-insensitive)
COLUMN_MAP = {
    'konto': 'konto',
    'saldo1': 'saldo1',
    'kostenstelle': 'kostenstelle',
    'konto_bez': 'konto_bez',
    'kst_bez1': 'kst_bez1',
}


def parse_bab_xlsx(file_bytes):
    """Parse BAB xlsx file bytes into a list of entry dicts.

    Returns:
        list[dict] with keys: konto, konto_bez, saldo1, kostenstelle, kst_bez1

    Raises:
        ValueError: if required columns are missing or file is invalid
    """
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
    except Exception as e:
        raise ValueError(f"Cannot open xlsx file: {e}")

    ws = wb.active
    if ws is None:
        raise ValueError("Workbook has no active sheet")

    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if not rows:
        raise ValueError("Workbook is empty")

    # Find header row (row 0)
    header_row = rows[0]
    col_idx = _map_columns(header_row)

    # Validate required columns
    for required in ('konto', 'saldo1', 'kostenstelle'):
        if required not in col_idx:
            raise ValueError(f"Required column '{required}' not found in header: {list(header_row)}")

    entries = []
    for row_num, row in enumerate(rows[1:], start=2):
        konto_raw = row[col_idx['konto']]

        # Skip rows with no konto (summary/header rows)
        if konto_raw is None:
            continue

        try:
            konto = int(float(konto_raw))
        except (ValueError, TypeError):
            continue  # skip non-numeric konto rows

        # Parse saldo1 as Decimal — never through float
        saldo1_raw = row[col_idx['saldo1']]
        if saldo1_raw is None:
            saldo1 = Decimal('0')
        else:
            try:
                saldo1 = Decimal(str(saldo1_raw))
            except (InvalidOperation, ValueError):
                raise ValueError(f"Row {row_num}: invalid saldo1 value '{saldo1_raw}'")

        # Parse kostenstelle
        kst_raw = row[col_idx['kostenstelle']]
        if kst_raw is None:
            continue  # skip rows without cost center
        try:
            kostenstelle = int(float(kst_raw))
        except (ValueError, TypeError):
            continue

        entry = {
            'konto': konto,
            'konto_bez': _get_cell(row, col_idx, 'konto_bez'),
            'saldo1': saldo1,
            'kostenstelle': kostenstelle,
            'kst_bez1': _get_cell(row, col_idx, 'kst_bez1'),
        }
        entries.append(entry)

    return entries


def _map_columns(header_row):
    """Map header names to column indices (case-insensitive)."""
    col_idx = {}
    for i, cell in enumerate(header_row):
        if cell is None:
            continue
        name = str(cell).strip().lower()
        if name in COLUMN_MAP:
            col_idx[COLUMN_MAP[name]] = i
    return col_idx


def _get_cell(row, col_idx, key):
    """Safely get a cell value by column key, or None."""
    idx = col_idx.get(key)
    if idx is None or idx >= len(row):
        return None
    val = row[idx]
    return str(val).strip() if val is not None else None
