"""Bilant Excel Handler — read Balanta uploads, generate output Excel."""

import io
import pandas as pd
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from .formula_engine import extract_ct_formula, extract_row_formula


def read_balanta_from_excel(file_bytes):
    """Read Balanta sheet from uploaded Excel.

    Returns:
        pd.DataFrame with columns at indices 0=Cont, 1=SFD, 2=SFC

    Raises:
        ValueError: if Balanta sheet not found
    """
    xlsx = pd.ExcelFile(io.BytesIO(file_bytes))
    if 'Balanta' not in xlsx.sheet_names:
        raise ValueError('Sheet "Balanta" not found in the uploaded file')
    return pd.read_excel(xlsx, sheet_name='Balanta')


def read_bilant_sheet_for_import(file_bytes):
    """Read Bilant sheet and auto-extract formulas for template import.

    Returns:
        list of dicts: [{description, nr_rd, formula_ct, formula_rd, row_type, sort_order}, ...]
    """
    xlsx = pd.ExcelFile(io.BytesIO(file_bytes))
    if 'Bilant' not in xlsx.sheet_names:
        raise ValueError('Sheet "Bilant" not found in the uploaded file')

    df = pd.read_excel(xlsx, sheet_name='Bilant')
    rows = []
    for idx, row in df.iterrows():
        desc = str(row.iloc[0]) if pd.notna(row.iloc[0]) else ''
        nr_rd = str(row.iloc[1]).replace('.0', '') if pd.notna(row.iloc[1]) else ''
        formula_ct = extract_ct_formula(desc)
        formula_rd = extract_row_formula(desc)

        # Determine row type
        row_type = 'data'
        desc_lower = desc.lower()
        if 'total' in desc_lower or formula_rd:
            row_type = 'total'
        elif not nr_rd and not formula_ct and not formula_rd:
            if desc.strip():
                row_type = 'section_header'
            else:
                row_type = 'separator'

        rows.append({
            'description': desc,
            'nr_rd': nr_rd,
            'formula_ct': formula_ct,
            'formula_rd': formula_rd,
            'row_type': row_type,
            'is_bold': row_type in ('total', 'section_header'),
            'indent_level': 0,
            'sort_order': idx,
        })
    return rows


def generate_output_excel(generation, results, metrics):
    """Generate 3-sheet Excel output from persisted generation data.

    Args:
        generation: dict with generation metadata (company_name, period_label, etc.)
        results: list of result dicts (description, nr_rd, value, verification)
        metrics: dict with summary, ratios, structure

    Returns:
        io.BytesIO containing the Excel file
    """
    output = io.BytesIO()

    # Styles
    header_font = Font(bold=True, color='FFFFFF', size=11)
    header_fill = PatternFill(start_color='2563EB', end_color='2563EB', fill_type='solid')
    section_font = Font(bold=True, size=11)
    total_font = Font(bold=True, size=10)
    border = Border(
        left=Side(style='thin', color='D1D5DB'),
        right=Side(style='thin', color='D1D5DB'),
        top=Side(style='thin', color='D1D5DB'),
        bottom=Side(style='thin', color='D1D5DB'),
    )
    money_format = '#,##0.00'

    from openpyxl import Workbook
    wb = Workbook()

    # ── Sheet 1: Bilant Results ──
    ws1 = wb.active
    ws1.title = 'Bilant'
    headers = ['Nr. rd.', 'Denumirea elementului', 'Sold Final', 'Verificare']
    for col, h in enumerate(headers, 1):
        cell = ws1.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal='center', wrap_text=True)

    for i, r in enumerate(results, 2):
        ws1.cell(row=i, column=1, value=r.get('nr_rd', '')).border = border
        desc_cell = ws1.cell(row=i, column=2, value=r.get('description', ''))
        desc_cell.border = border
        indent = r.get('indent_level', 0)
        if indent:
            desc_cell.alignment = Alignment(indent=indent)
        val_cell = ws1.cell(row=i, column=3, value=r.get('value', 0))
        val_cell.number_format = money_format
        val_cell.border = border
        verif_cell = ws1.cell(row=i, column=4, value=r.get('verification', ''))
        verif_cell.border = border
        verif_cell.alignment = Alignment(wrap_text=True)

        if r.get('is_bold') or r.get('row_type') in ('total', 'section_header'):
            for col in range(1, 5):
                ws1.cell(row=i, column=col).font = total_font if r.get('row_type') == 'total' else section_font

    ws1.column_dimensions['A'].width = 10
    ws1.column_dimensions['B'].width = 55
    ws1.column_dimensions['C'].width = 18
    ws1.column_dimensions['D'].width = 40

    # ── Sheet 2: Dashboard ──
    ws2 = wb.create_sheet('Dashboard')
    row_num = 1

    # Title
    title_cell = ws2.cell(row=row_num, column=1, value=f"Bilant — {generation.get('company_name', '')} — {generation.get('period_label', '')}")
    title_cell.font = Font(bold=True, size=14)
    row_num += 2

    # Summary
    ws2.cell(row=row_num, column=1, value='SUMAR FINANCIAR').font = section_font
    row_num += 1
    summary = metrics.get('summary', {})
    for label, key in [('Total Active', 'total_active'), ('Active Imobilizate', 'active_imobilizate'),
                       ('Active Circulante', 'active_circulante'), ('Capitaluri Proprii', 'capitaluri_proprii'),
                       ('Total Datorii', 'total_datorii')]:
        ws2.cell(row=row_num, column=1, value=label).border = border
        val_cell = ws2.cell(row=row_num, column=2, value=summary.get(key, 0))
        val_cell.number_format = money_format
        val_cell.border = border
        row_num += 1

    row_num += 1
    ws2.cell(row=row_num, column=1, value='INDICATORI FINANCIARI').font = section_font
    row_num += 1
    for h_col, h_val in enumerate(['Indicator', 'Valoare', 'Interpretare'], 1):
        c = ws2.cell(row=row_num, column=h_col, value=h_val)
        c.font = header_font
        c.fill = header_fill
        c.border = border
    row_num += 1

    from .formula_engine import STANDARD_RATIOS
    ratios = metrics.get('ratios', {})
    for key, spec in STANDARD_RATIOS.items():
        val = ratios.get(key)
        ws2.cell(row=row_num, column=1, value=spec['label']).border = border
        ws2.cell(row=row_num, column=2, value=val if val is not None else 'N/A').border = border
        ws2.cell(row=row_num, column=3, value=spec['interpretation']).border = border
        row_num += 1

    row_num += 1
    # Asset structure
    ws2.cell(row=row_num, column=1, value='STRUCTURA ACTIVELOR').font = section_font
    row_num += 1
    for item in metrics.get('structure', {}).get('assets', []):
        ws2.cell(row=row_num, column=1, value=item['name']).border = border
        val_cell = ws2.cell(row=row_num, column=2, value=item['value'])
        val_cell.number_format = money_format
        val_cell.border = border
        ws2.cell(row=row_num, column=3, value=f"{item['percent']}%").border = border
        row_num += 1

    row_num += 1
    ws2.cell(row=row_num, column=1, value='STRUCTURA PASIVELOR').font = section_font
    row_num += 1
    for item in metrics.get('structure', {}).get('liabilities', []):
        ws2.cell(row=row_num, column=1, value=item['name']).border = border
        val_cell = ws2.cell(row=row_num, column=2, value=item['value'])
        val_cell.number_format = money_format
        val_cell.border = border
        ws2.cell(row=row_num, column=3, value=f"{item['percent']}%").border = border
        row_num += 1

    ws2.column_dimensions['A'].width = 30
    ws2.column_dimensions['B'].width = 20
    ws2.column_dimensions['C'].width = 20

    wb.save(output)
    output.seek(0)
    return output
