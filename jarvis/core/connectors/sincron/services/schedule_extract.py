"""Pure helper: pick an employee's daily schedule from Sincron activities.

Kept dependency-free so it is unit-testable without app/DB imports.
"""


def extract_employee_schedule(days):
    """Return (schedule_in, schedule_out, pauza_masa) for an employee's month.

    Prefers an OZ (worked) activity's program. When the whole period has no OZ
    (e.g. a full month of medical/annual leave), falls back to the first activity
    of any code that carries a program — Sincron puts the contracted schedule on
    leave rows too. Returns (None, None, None) when nothing has a program.
    """
    fallback = None
    for day_acts in (days or {}).values():
        for a in day_acts:
            prog = a.get('program') or {}
            if not prog.get('in'):
                continue
            if a.get('short_code') == 'OZ':
                return prog['in'], prog.get('out'), prog.get('pauza_masa')
            if fallback is None:
                fallback = (prog['in'], prog.get('out'), prog.get('pauza_masa'))
    return fallback if fallback is not None else (None, None, None)
