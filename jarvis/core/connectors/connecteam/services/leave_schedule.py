"""Sincron-derived work window + day cap for the Bilet de Invoire form.

Pure helpers (window/cap/return/validation) live here so they are testable
without a DB; the single DB call is isolated in `_fetch_day_schedule`.
"""
import logging
from datetime import date as _date

logger = logging.getLogger('jarvis.connecteam.leave_schedule')

DEFAULT_START = '09:00'
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
    if row and row.get('schedule_start') and row.get('schedule_end'):
        return {
            'schedule_start': _hm(row['schedule_start']),
            'schedule_end': _hm(row['schedule_end']),
            'day_cap_hours': _day_cap(row.get('norma_lucru'), row.get('lunch_break_minutes')),
            'lunch_break_minutes': int(row.get('lunch_break_minutes') or 0),
            'source': 'sincron',
        }
    return {'schedule_start': DEFAULT_START, 'schedule_end': DEFAULT_END,
            'day_cap_hours': DEFAULT_CAP, 'lunch_break_minutes': 60, 'source': 'default'}


def compute_return(start_hm, duration_hours):
    s = parse_hm(start_hm) or 0
    total = max(0, min(1439, s + int(round(float(duration_hours) * 60))))
    return f'{total // 60:02d}:{total % 60:02d}'
