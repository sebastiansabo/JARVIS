"""Consum efectiv on the monthly Foaie de Parcurs = total fuel *alimentat* (Σ of
the alimentări the user records), not the per-session `fuel_consumed_liters`
column (which the route flow never populates → it always rendered 0).

Fuel section → Σ litri; Energie section → Σ kWh. Shown on BOTH the HTML/PDF and
the Excel, for both sections.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import foi_parcurs.services.route_sheet_service as rss

# 41.43 + 16.89 = 58.32 l alimentat over 843 km (the reported case).
ENTRIES_L = [
    {'date': '2026-08-03', 'bon': '001', 'liters': 41.43, 'lei': 392.34},
    {'date': '2026-08-13', 'bon': '001', 'liters': 16.89, 'lei': 161.64},
]


def test_fuel_html_consum_efectiv_equals_total_alimentat():
    html = rss._fuel_section_html('l', 6.5, ENTRIES_L, 843)
    assert 'Consum efectiv</td><td>58.32 l' in html


def test_energy_html_consum_efectiv_shown_for_kwh():
    html = rss._fuel_section_html('kWh', 17.0, [{'liters': 17.5, 'lei': 30}], 100)
    assert 'Consum efectiv</td><td>17.5 kWh' in html


def test_fuel_html_consum_efectiv_zero_when_no_alimentari():
    html = rss._fuel_section_html('l', 6.5, [], 843)
    assert 'Consum efectiv</td><td>0 l' in html


def test_xlsx_consum_efectiv_equals_total_alimentat():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    bold = Font(bold=True)
    fill = PatternFill('solid', fgColor='1A1A2E')
    rss._xlsx_fuel_section(ws, 1, 'l', 6.5, ENTRIES_L, 843, bold, fill, bold)
    labels = {}
    for r in range(1, ws.max_row + 1):
        label = str(ws.cell(row=r, column=1).value or '')
        if label.startswith('Consum efectiv'):
            labels[label] = ws.cell(row=r, column=2).value
    assert any(v == 58.32 for v in labels.values())
