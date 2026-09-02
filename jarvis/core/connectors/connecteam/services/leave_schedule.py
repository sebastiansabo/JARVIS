"""Sincron-derived work window + day cap for the Bilet de Invoire form.

Pure helpers (window/cap/return/validation) live here so they are testable
without a DB; the single DB call is isolated in `_fetch_day_schedule`.
"""
import logging
from datetime import date as _date

logger = logging.getLogger('jarvis.connecteam.leave_schedule')

DEFAULT_START = '07:00'
DEFAULT_END = '18:00'
DEFAULT_CAP = 8.0        # full workday (norma_lucru is already net of lunch)
MAX_CAP = 8.0


def _hm(t):
    if t is None:
        return None
    if isinstance(t, str):
        return t[:5]
    return t.strftime('%H:%M')


def parse_hm(s):
    if not isinstance(s, str):
        return None
    parts = s.strip().split(':')
    if len(parts) < 2:
        return None
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h * 60 + m


def _day_cap(norma_lucru, lunch_minutes=None):
    """Max leave duration = the contracted daily WORK hours (norma_lucru), which is
    already net of the lunch break — so a full-day leave equals the norma (e.g. 8h),
    NOT norma − lunch. lunch_minutes is accepted for backward-compat but unused."""
    if norma_lucru is None:
        return DEFAULT_CAP
    cap = round(min(float(norma_lucru), MAX_CAP) * 2) / 2
    return cap if cap >= 0.5 else DEFAULT_CAP


def _fetch_company_schedules(jarvis_user_id, date_str):
    """All active company contracts' schedules — isolated so tests can monkeypatch it."""
    from core.connectors.sincron.repositories.sincron_repository import SincronRepository
    return SincronRepository().get_active_company_schedules(jarvis_user_id) or []


def _window(row):
    """(start, end) HH:MM from a schedule row, falling back to the default window."""
    return (_hm(row.get('schedule_start')) or DEFAULT_START,
            _hm(row.get('schedule_end')) or DEFAULT_END)


def _company_entry(row):
    start, end = _window(row)
    return {
        'company_name': row.get('company_name'),
        'norma_lucru': (float(row['norma_lucru']) if row.get('norma_lucru') is not None else None),
        'schedule_start': start,
        'schedule_end': end,
        'lunch_break_minutes': int(row.get('lunch_break_minutes') or 0),
        'day_cap_hours': _day_cap(row.get('norma_lucru'), row.get('lunch_break_minutes')),
    }


def get_leave_schedule(jarvis_user_id, date_str=None, company_name=None):
    """Work window + cap + lunch for the leave form, per selected company contract.

    Each contract sets its OWN selectable window (schedule_start–schedule_end from
    Sincron, fallback 07:00–18:00), day cap (norma_lucru) and lunch. `companies` lists
    every active contract so a multi-company employee can pick which one the leave is
    against; `selected_company` is the chosen one (or the primary = highest norma)."""
    d = date_str or _date.today().isoformat()
    rows = []
    try:
        rows = _fetch_company_schedules(jarvis_user_id, d) or []
    except Exception as e:
        logger.warning('sincron schedule fetch failed for user %s: %s', jarvis_user_id, e)
        rows = []
    companies = [_company_entry(r) for r in rows]
    # Chosen company by name, else the primary (rows are ordered norma DESC).
    pick = next((r for r in rows if r.get('company_name') == company_name), None) if company_name else None
    if pick is None and rows:
        pick = rows[0]
    if pick is not None:
        start, end = _window(pick)
        return {
            'schedule_start': start,
            'schedule_end': end,
            'day_cap_hours': _day_cap(pick.get('norma_lucru'), pick.get('lunch_break_minutes')),
            'lunch_break_minutes': int(pick.get('lunch_break_minutes') or 0),
            'source': 'sincron',
            'selected_company': pick.get('company_name'),
            'companies': companies,
        }
    return {'schedule_start': DEFAULT_START, 'schedule_end': DEFAULT_END,
            'day_cap_hours': DEFAULT_CAP, 'lunch_break_minutes': 60, 'source': 'default',
            'selected_company': None, 'companies': []}


def compute_return(start_hm, duration_hours, extra_minutes=0):
    """Return time = start + work duration + extra_minutes. A full-day leave passes
    the lunch break as extra_minutes so the return reflects the real program end
    (e.g. 08:00 + 8h work + 60m lunch = 17:00). The duration itself stays work-hours."""
    s = parse_hm(start_hm) or 0
    total = max(0, min(1439, s + int(round(float(duration_hours) * 60)) + int(round(extra_minutes or 0))))
    return f'{total // 60:02d}:{total % 60:02d}'


def _full_day_lunch(duration_hours, schedule):
    """Lunch minutes to append to the return — only for a full-day leave (duration
    equals the day cap); 0 otherwise. We don't know the lunch time-of-day, so a
    partial leave is assumed not to cross it."""
    try:
        dur = float(duration_hours)
    except (TypeError, ValueError):
        return 0
    cap = float(schedule.get('day_cap_hours') or 0)
    lunch = int(schedule.get('lunch_break_minutes') or 0)
    return lunch if cap and abs(dur - cap) < 1e-9 else 0


def validate_leave(start_hm, duration_hours, schedule):
    """Validate leave request: alignment, duration, cap, and window.

    Args:
        start_hm: Start time as HH:MM string
        duration_hours: Duration in hours (float)
        schedule: Dict with schedule_start, schedule_end, day_cap_hours

    Returns:
        Romanian error message string, or None if valid.
    """
    s = parse_hm(start_hm)
    if s is None or s % 30 != 0:
        return 'Ora de început trebuie să fie la interval de 30 de minute.'
    try:
        dur = float(duration_hours)
    except (TypeError, ValueError):
        return 'Durată invalidă.'
    if dur < 0.5 or round(dur * 2) != dur * 2:
        return 'Durata trebuie să fie un multiplu de 30 de minute.'
    cap = float(schedule.get('day_cap_hours') or DEFAULT_CAP)
    if dur > cap:
        return f'Durata maximă permisă este {cap:g} ore.'
    ws = parse_hm(schedule.get('schedule_start'))
    we = parse_hm(schedule.get('schedule_end'))
    if ws is not None and s < ws:
        return 'Ora de început este înainte de programul de lucru.'
    # Full-day leaves also span the lunch, so the real return is later by the
    # lunch break — validate against that so we never store a return past the window.
    ret = s + int(round(dur * 60)) + _full_day_lunch(dur, schedule)
    if we is not None and ret > we:
        return 'Ora de întoarcere depășește programul de lucru.'
    return None
