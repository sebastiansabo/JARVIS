"""Detect contract termination from a Sincron monthly timesheet.

Sincron's timesheet API exposes no contract-end field. A mid-month leaver
stays in the current month's feed, but their post-termination days are filled
with code ``X`` (an out-of-contract marker). Empirically, across all of 2026,
``X`` only ever forms a single contiguous block at the START (pre-hire) or the
END (post-termination) of a person's real activity — work never resumes after
an ``X`` block within a month.

So a run of ``X`` *after* the employee's last real activity day marks a
termination, whereas a run of ``X`` *before* their first real activity is a new
hire (pre-employment days) and must NOT be treated as a termination.
"""

TERMINATION_CODE = 'X'


def detect_termination(days):
    """Detect a trailing-X termination in one employee's monthly timesheet.

    Args:
        days: dict ``{day_str: [activity, ...]}`` as returned by the Sincron
            API, where each activity carries a ``short_code``. ``day_str`` is an
            ISO ``YYYY-MM-DD`` string (lexicographic order == chronological).

    Returns:
        ``{'terminated': True, 'last_worked_day': <str>, 'termination_from': <str>}``
        when the timesheet ends in a run of ``X`` after the last real activity,
        else ``{'terminated': False}``.
    """
    x_days = []       # days whose only code is the out-of-contract marker
    active_days = []  # days carrying at least one real (non-X) code
    for day_str, activities in (days or {}).items():
        codes = {a.get('short_code') for a in (activities or []) if a.get('short_code')}
        if not codes:
            continue
        if codes == {TERMINATION_CODE}:
            x_days.append(day_str)
        else:
            active_days.append(day_str)

    if not active_days or not x_days:
        return {'terminated': False}

    last_worked = max(active_days)
    trailing_x = [d for d in x_days if d > last_worked]
    if not trailing_x:
        return {'terminated': False}  # leading X only == new hire

    return {
        'terminated': True,
        'last_worked_day': last_worked,
        'termination_from': min(trailing_x),
    }
