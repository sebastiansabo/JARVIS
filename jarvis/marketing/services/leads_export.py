"""Project-leads Excel export — builds a single-sheet .xlsx.

Pure data→bytes helper (DB-free, unit-testable): the route fetches the
filtered rows and hands them here. Mirrors hr/time_bank/export.py, including
the spreadsheet formula-injection guard.
"""
import io
from datetime import datetime, timezone

import openpyxl
from openpyxl.styles import Font

try:  # py3.9+ stdlib; backport on older runtimes
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo

_RO_TZ = ZoneInfo('Europe/Bucharest')

_HEADERS = ['Received', 'Name', 'Phone', 'Email', 'Company', 'CUI', 'Source',
            'Campaign', 'Message', 'Model', 'Status', 'Assigned', 'Notes']
_WIDTHS = [18, 22, 15, 24, 22, 12, 16, 16, 40, 16, 12, 20, 30]

# A cell whose text starts with one of these can be executed as a formula when
# the .xlsx is opened; prefix with an apostrophe so it stays literal text.
_FORMULA_TRIGGERS = ('=', '+', '-', '@', '\t', '\r', '\n')


def _safe_text(value):
    """Neutralise spreadsheet formula injection in a free-text cell."""
    if isinstance(value, str) and value and value[0] in _FORMULA_TRIGGERS:
        return "'" + value
    return value


def _fmt_dt(value):
    """Render a stored UTC timestamp as Europe/Bucharest 'YYYY-MM-DD HH:MM'."""
    if value is None:
        return ''
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(_RO_TZ).strftime('%Y-%m-%d %H:%M')
    return str(value)


def build_leads_workbook(leads):
    """Return .xlsx bytes for a project's (already filtered) lead rows."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Leads'

    for col, (header, width) in enumerate(zip(_HEADERS, _WIDTHS), 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True)
        ws.column_dimensions[cell.column_letter].width = width
    ws.freeze_panes = 'A2'

    for lead in leads:
        ws.append([
            _safe_text(_fmt_dt(lead.get('created_at'))),
            _safe_text(lead.get('contact_name') or ''),
            _safe_text(lead.get('phone') or ''),
            _safe_text(lead.get('email') or ''),
            _safe_text(lead.get('company_name') or ''),
            _safe_text(lead.get('cui') or ''),
            _safe_text(lead.get('source') or ''),
            _safe_text(lead.get('utm_campaign') or ''),
            _safe_text(lead.get('message') or ''),
            _safe_text(lead.get('model_of_interest') or ''),
            _safe_text(lead.get('status') or ''),
            _safe_text(lead.get('assigned_to_name') or ''),
            _safe_text(lead.get('status_notes') or ''),
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()
