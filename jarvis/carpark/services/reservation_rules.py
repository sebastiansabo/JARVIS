"""Reservation rules — pure duration + overlap helpers for Dispo reserve.

Three rules the reserve flow enforces (see DispoService.reserve):
  1. a vehicle may hold MORE THAN ONE reservation at a time;
  2. two reservations may NOT overlap in time;
  3. a single reservation may span at most MAX_RESERVATION_DAYS days.

Kept pure (no DB, no `now()`) so the rules are testable in isolation; the
service resolves the effective start/"now" and passes concrete values in.
"""
from datetime import date, datetime
from typing import Any, Dict, List, Optional

MAX_RESERVATION_DAYS = 3

# Open-ended reservations (reservation_end IS NULL) block everything from
# their start onward — represented as "the end of time" for overlap math.
_FOREVER = datetime.max


def _coerce_dt(value: Any) -> Optional[datetime]:
    """Normalise a date / datetime / ISO string to a datetime, or None.

    Dates become midnight datetimes so date-only and timestamp reservations
    compare on one axis. Unparseable values yield None (the caller decides
    what a missing bound means)."""
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00').replace(' ', 'T'))
        except ValueError:
            # Date-only string ('2026-09-01') not caught above on older
            # Pythons, or a bare date — fall back to date parsing.
            try:
                return datetime.fromisoformat(value[:10])
            except ValueError:
                return None
    return None


def exceeds_max_duration(start: Any, end: Any, max_days: int = MAX_RESERVATION_DAYS) -> bool:
    """True if [start, end] spans strictly more than `max_days` days.

    A None/unparseable bound can't exceed the limit (treated as not-exceeding);
    the required-field guards upstream handle genuinely missing data."""
    s = _coerce_dt(start)
    e = _coerce_dt(end)
    if s is None or e is None:
        return False
    return (e - s).days > max_days


def ends_before_start(start: Any, end: Any) -> bool:
    """True if `end` is strictly before `start` (an inverted interval). A
    None/unparseable bound is treated as not-inverted — the required-field
    guards handle genuinely missing data."""
    s = _coerce_dt(start)
    e = _coerce_dt(end)
    if s is None or e is None:
        return False
    return e < s


def intervals_overlap(s1: Any, e1: Any, s2: Any, e2: Any) -> bool:
    """True if [s1, e1) and [s2, e2) overlap. Touching endpoints do NOT
    overlap (back-to-back reservations are allowed). A None end is treated
    as open-ended (far future)."""
    a_start = _coerce_dt(s1)
    b_start = _coerce_dt(s2)
    if a_start is None or b_start is None:
        return False
    a_end = _coerce_dt(e1) or _FOREVER
    b_end = _coerce_dt(e2) or _FOREVER
    return a_start < b_end and b_start < a_end


def find_conflict(start: Any, end: Any, existing: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return the first existing reservation whose range overlaps [start, end],
    or None if the interval is free. Rows without a start are skipped."""
    for res in existing or []:
        if res.get('reservation_start') is None:
            continue
        if intervals_overlap(start, end, res.get('reservation_start'), res.get('reservation_end')):
            return res
    return None
