"""Sincron-derived work window + day cap for the Bilet de Invoire form.

Pure helpers (window/cap/return/validation) live here so they are testable
without a DB; the single DB call is isolated in `_fetch_day_schedule`.
"""
import logging
from datetime import date as _date

logger = logging.getLogger('jarvis.connecteam.leave_schedule')

DEFAULT_START = '07:00'
DEFAULT_END = '18:00'
DEFAULT_CAP = 7.0


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


def _day_cap(norma_lucru, lunch_minutes):
    if norma_lucru is None:
        return DEFAULT_CAP
    net = float(norma_lucru) - (float(lunch_minutes or 0) / 60.0)
    cap = round(min(net, 7.0) * 2) / 2
    return cap if cap >= 0.5 else DEFAULT_CAP


def _fetch_day_schedule(jarvis_user_id, date_str):
    """Single DB hop — isolated so unit tests can monkeypatch it."""
    from core.connectors.sincron.repositories.sincron_repository import SincronRepository
    return SincronRepository().get_day_schedule_by_jarvis_user(jarvis_user_id, date_str)


def get_leave_schedule(jarvis_user_id, date_str=None):
    d = date_str or _date.today().isoformat()
    row = None
    try:
        row = _fetch_day_schedule(jarvis_user_id, d)
    except Exception as e:
        logger.warning('sincron schedule fetch failed for user %s: %s', jarvis_user_id, e)
        row = None
    # The selectable window is a FIXED company program (07:00–18:00) for
    # everyone — the start dropdown always runs 07:00 → 17:30 (for a future day)
    # or now → 17:30 (for today). Sincron, when available, no longer narrows the
    # window; it only tightens the daily duration cap (norma − lunch, ≤7h).
    norma = row.get('norma_lucru') if row else None
    if norma is not None:
        return {
            'schedule_start': DEFAULT_START,
            'schedule_end': DEFAULT_END,
            'day_cap_hours': _day_cap(norma, row.get('lunch_break_minutes')),
            'lunch_break_minutes': int(row.get('lunch_break_minutes') or 0),
            'source': 'sincron',
        }
    return {'schedule_start': DEFAULT_START, 'schedule_end': DEFAULT_END,
            'day_cap_hours': DEFAULT_CAP, 'lunch_break_minutes': 60, 'source': 'default'}


def compute_return(start_hm, duration_hours):
    s = parse_hm(start_hm) or 0
    total = max(0, min(1439, s + int(round(float(duration_hours) * 60))))
    return f'{total // 60:02d}:{total % 60:02d}'


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
    ret = s + int(round(dur * 60))
    if we is not None and ret > we:
        return 'Ora de întoarcere depășește programul de lucru.'
    return None
