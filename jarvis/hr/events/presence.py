"""Granular presence-day logic for event bonuses (pure, no DB).

An event bonus is attended on a set of specific *full* days chosen from the
event's date range. These helpers are the single source of truth for:

- validating/normalising the chosen days against the event window,
- deriving the columns stored on ``hr.event_bonuses`` (count, window, primary
  month),
- splitting the bonus money pro-rata across the calendar months the days fall
  in (uniform per-day rate; whole-cent exact), so a bonus that spans a month
  boundary is reported under every month it touches.
"""
from datetime import date, datetime
from typing import Callable, Dict, List, Tuple


def parse_day(value) -> date:
    """Coerce an ISO ``YYYY-MM-DD`` string, ``date`` or ``datetime`` to ``date``."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()


def normalize_presence_days(days, event_start, event_end) -> List[date]:
    """Return the sorted, de-duplicated presence days.

    Raises ``ValueError`` if the list is empty or any day falls outside the
    inclusive ``[event_start, event_end]`` range.
    """
    start = parse_day(event_start)
    end = parse_day(event_end)
    parsed = {parse_day(d) for d in days}
    if not parsed:
        raise ValueError('At least one presence day is required')
    for d in parsed:
        if d < start or d > end:
            raise ValueError(
                f'Presence day {d.isoformat()} is outside the event range '
                f'{start.isoformat()}..{end.isoformat()}')
    return sorted(parsed)


def derive_bonus_fields(days) -> Dict:
    """Derive the ``hr.event_bonuses`` columns from the presence days.

    ``year``/``month`` are the *primary* month = the earliest attended day.
    """
    ordered = sorted(parse_day(d) for d in days)
    first = ordered[0]
    return {
        'bonus_days': len(ordered),
        'participation_start': first,
        'participation_end': ordered[-1],
        'year': first.year,
        'month': first.month,
    }


def months_touched(days) -> List[Tuple[int, int]]:
    """Sorted, de-duplicated ``(year, month)`` tuples the days fall in.

    Used to lock-check every month a bonus's days touch. The per-month money
    split itself lives in SQL (``hr.v_event_bonus_days.day_net``), the single
    source of truth for reporting, so there is no Python splitter here.
    """
    return sorted({(d.year, d.month) for d in (parse_day(x) for x in days)})


def _coerce_whole_hour(value, day: str):
    """Return ``value`` as an int hour, or raise if it isn't a whole 0..24 hour.

    ``None`` passes through unchanged (an unset bound).
    """
    if value is None:
        return None
    # Reject fractional numbers (10.5) but accept ints and whole-valued floats.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{day}: hours must be whole hours')
    if float(value) != int(value):
        raise ValueError(f'{day}: hours must be whole hours')
    ivalue = int(value)
    if ivalue < 0 or ivalue > 24:
        raise ValueError(f'{day}: hours must be between 0 and 24')
    return ivalue


def validate_day_hours(day_hours, presence_days) -> Dict[str, Dict[str, int]]:
    """Validate optional per-day hour intervals against the attended days.

    ``day_hours`` maps ``'YYYY-MM-DD' -> {'start': h, 'end': h}`` (whole hours).
    A day with neither bound set is dropped (no interval yet). Returns the
    normalised map of only the days that carry a full, valid interval.

    Raises ``ValueError`` if a day is not in ``presence_days``, only one bound
    is set, a bound is not a whole hour in ``0..24``, or ``end <= start``.
    """
    if not day_hours:
        return {}
    attended = {str(d)[:10] for d in (presence_days or [])}
    out: Dict[str, Dict[str, int]] = {}
    for raw_day, bounds in day_hours.items():
        day = str(raw_day)[:10]
        bounds = bounds or {}
        start = _coerce_whole_hour(bounds.get('start'), day)
        end = _coerce_whole_hour(bounds.get('end'), day)
        if start is None and end is None:
            continue  # selected day with no interval set — contributes 0 hours
        if day not in attended:
            raise ValueError(f'{day} is not an attended day')
        if start is None or end is None:
            raise ValueError(f'{day}: set both a start and end hour, or neither')
        if end <= start:
            raise ValueError(f'{day}: end hour must be after start hour')
        out[day] = {'start': start, 'end': end}
    return out


def total_event_hours(day_hours) -> int:
    """Sum of ``end - start`` (whole hours) over days with a full interval."""
    if not day_hours:
        return 0
    total = 0
    for bounds in day_hours.values():
        bounds = bounds or {}
        start, end = bounds.get('start'), bounds.get('end')
        if start is None or end is None:
            continue
        if int(end) > int(start):
            total += int(end) - int(start)
    return total


def check_months_editable(
    months, is_locked: Callable[[int, int], bool]
) -> Tuple[bool, List[Tuple[int, int]]]:
    """Editable only if *none* of the touched months are locked.

    Returns ``(editable, locked_months)`` where ``locked_months`` is sorted.
    """
    locked = sorted((y, m) for (y, m) in months if is_locked(y, m))
    return (not locked, locked)
