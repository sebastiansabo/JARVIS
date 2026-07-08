"""Pure builders + workbook generation for the Pontaje export.

No SQL here — callers pass already-fetched rows/maps. Kept pure so the row
logic is unit-testable under the psycopg2-mocked test harness.
"""
import datetime as _dt
from io import BytesIO

HEADERS = ['Date', 'Weekday', 'Name', 'Group', 'Company', 'Checked In', 'Checked Out',
           'Actual In', 'Actual Out', 'Lunch', 'Duration', 'Punches', 'Schedule',
           'Sincron', 'Status']

_WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']


def _fmt_time(value):
    """Return 'HH:MM' from a datetime/str, by slice (no tz conversion)."""
    if value is None:
        return ''
    s = str(value)
    # match 'T08:03' or ' 08:03'
    for sep in ('T', ' '):
        i = s.find(sep)
        if i != -1 and len(s) >= i + 6 and s[i + 3] == ':':
            return s[i + 1:i + 6]
    return s[11:16] if len(s) >= 16 else s


def _fmt_hm(total_sec):
    if not total_sec or total_sec <= 0:
        return ''
    h = int(total_sec // 3600)
    m = round((total_sec % 3600) / 60)
    return f'{h}:{m:02d}'


def _net_seconds(gross_sec, lunch_min):
    if not gross_sec or gross_sec <= 0:
        return 0
    lunch_sec = (lunch_min or 0) * 60
    return gross_sec - lunch_sec if gross_sec > lunch_sec else gross_sec


def _lunch_cell(lunch_min):
    return '' if lunch_min is None else f'{int(lunch_min)} min'


def _span_seconds(a, b):
    if not a or not b:
        return None
    return (b - a).total_seconds()


def _status(has_punch, has_adj, single_punch_no_adj, code):
    if single_punch_no_adj:
        return 'Not exited'
    return 'Present' if (has_punch or has_adj) else 'Absent'


def build_rows(punch_rows, sched_map, code_map):
    out = []
    for r in punch_rows:
        day = r['day']
        juid = r.get('jarvis_user_id')
        sched = sched_map.get((juid, r.get('company_id'), day)) or {}
        lunch = sched.get('lunch_break_minutes')  # None allowed -> blank
        sstart = sched.get('schedule_start') or r.get('static_start')
        send = sched.get('schedule_end') or r.get('static_end')

        adj_first = r.get('adjusted_first_punch')
        adj_last = r.get('adjusted_last_punch')
        has_adj = bool(adj_first or adj_last)
        raw_first = r.get('first_punch')
        raw_last = r.get('last_punch')
        total = r.get('total_punches') or 0
        single_no_adj = total == 1 and not has_adj

        eff_in = adj_first or raw_first
        eff_out = adj_last or raw_last
        checked_out = eff_out if (eff_out and eff_out != eff_in) else None

        # gross seconds: adjusted span if both adjusted, else duration_seconds
        if adj_first and adj_last:
            gross = _span_seconds(adj_first, adj_last)
        else:
            gross = r.get('duration_seconds')
        duration = '' if (single_no_adj or not eff_in or not checked_out) else _fmt_hm(_net_seconds(gross, lunch))

        code = code_map.get((juid, day), '')
        wd = _WEEKDAYS[day.weekday()]

        out.append([
            day.isoformat(),
            wd,
            r.get('name') or '',
            r.get('group') or '',
            r.get('company') or '',
            _fmt_time(eff_in) if eff_in else '',
            _fmt_time(checked_out) if checked_out else '',
            _fmt_time(raw_first) if raw_first else '',
            _fmt_time(raw_last) if (raw_last and raw_last != raw_first) else '',
            _lunch_cell(lunch),
            duration,
            str(total),
            f'{sstart or ""}–{send or ""}' if (sstart or send) else '',
            code,
            _status(bool(raw_first), has_adj, single_no_adj, code),
        ])
    return out


def build_workbook(rows):
    """rows: list of 15-col lists (no header). Returns xlsx bytes."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = Workbook()
    ws = wb.active
    ws.title = 'Pontaje'
    fill = PatternFill(start_color='0F6D63', end_color='0F6D63', fill_type='solid')
    font = Font(bold=True, color='FFFFFF')
    for col, h in enumerate(HEADERS, 1):
        c = ws.cell(row=1, column=col, value=h)
        c.fill = fill
        c.font = font
        c.alignment = Alignment(horizontal='center')
    for i, r in enumerate(rows, 2):
        for col, val in enumerate(r, 1):
            ws.cell(row=i, column=col, value=val)
    widths = [11, 8, 22, 16, 16, 10, 11, 10, 10, 8, 9, 8, 14, 9, 12]
    for col, w in enumerate(widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = w
    ws.freeze_panes = 'A2'
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def _months_between(start, end):
    s = _dt.date.fromisoformat(str(start)[:10])
    e = _dt.date.fromisoformat(str(end)[:10])
    out, y, m = [], s.year, s.month
    while (y, m) <= (e.year, e.month):
        out.append((y, m))
        m += 1
        if m > 12:
            m = 1; y += 1
    return out


def generate(start, end, jarvis_user_ids):
    """Fetch + assemble + build workbook. Returns (xlsx_bytes, filename)."""
    from core.connectors.biostar.repositories.biostar_repository import BioStarRepository
    from core.connectors.sincron.repositories.sincron_repository import SincronRepository
    b_repo = BioStarRepository()
    s_repo = SincronRepository()

    punch_rows = b_repo.get_pontaje_rows(start, end, jarvis_user_ids)

    ids = sorted({r['jarvis_user_id'] for r in punch_rows if r.get('jarvis_user_id')})
    sched_map = {}
    code_map = {}
    if ids:
        for s in s_repo.get_day_schedules_for_users(ids, start, end):
            sched_map[(s['jarvis_user_id'], s['company_id'], s['day'])] = s
        for (y, m) in _months_between(start, end):
            for row in s_repo.get_day_codes_for_users(ids, y, m):
                code_map[(row['mapped_jarvis_user_id'], row['day'])] = row['short_code']

    rows = build_rows(punch_rows, sched_map, code_map)
    xlsx = build_workbook(rows)
    filename = f'pontaje_{start}_{end}.xlsx'
    return xlsx, filename
