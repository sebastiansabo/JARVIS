"""Leave-summary shaping for the Bilet de Învoire approval surfaces.

`format_leave_summary` is pure (row in → dict out) so it can be unit-tested without a
DB; `build_leave_summary` pairs it with the existing submission loader for callers
(the approver email, the in-app detail). Non-leave submissions return None so callers
keep their generic rendering.
"""


def format_leave_summary(row):
    """Row from `_load_leave_submission` → summary dict, or None if not a leave permit."""
    if not row or row.get('slug') != 'bilet-de-invoire':
        return None
    a = row.get('answers') or {}
    return {
        'requester_name': row.get('requester_name') or 'Un angajat',
        'leave_date': a.get('f_bi_leave_date', ''),
        'start': a.get('f_bi_start_time', ''),
        'end': a.get('f_bi_end_time', ''),
        'hours': a.get('f_bi_hours', ''),
        'reason': a.get('f_bi_reason', ''),
        'notes': a.get('f_bi_notes', ''),
        'is_correction': bool(a.get('f_bi_is_correction')),
        'company': a.get('f_bi_company') or None,
    }


def build_leave_summary(submission_id):
    """Fetch + format a submission's leave summary, or None. Never raises."""
    try:
        from .event_handlers import _load_leave_submission
        return format_leave_summary(_load_leave_submission(submission_id))
    except Exception:
        return None
