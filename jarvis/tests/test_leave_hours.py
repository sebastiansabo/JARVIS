"""Unit tests for `_leave_hours` — the net work-hours shown in the HR Bilete list.

Regression guard for the "full-day bilet shows 9h instead of 8h" bug: the
canonical JARVIS flow bakes the lunch break into f_bi_end_time (08:00 + 8h work
+ 1h lunch = 17:00) and stores the true net duration in f_bi_duration_hours.
Recomputing hours from the raw start/end span re-adds the lunch and overstates
the duration, so the stored net duration must win.
"""
from core.connectors.connecteam.services.connecteam_service import _leave_hours


def test_full_day_canonical_row_excludes_lunch():
    # Ioana Babos's real submission #181: a full workday whose end time already
    # includes the 1h lunch. The list must show the net 8h, not the 9h span.
    answers = {
        'f_bi_start_time': '08:00',
        'f_bi_end_time': '17:00',
        'f_bi_hours': 8.0,
        'f_bi_duration_hours': 8,
    }
    assert _leave_hours(answers) == 8.0


def test_partial_leave_uses_stored_duration():
    answers = {
        'f_bi_start_time': '08:30',
        'f_bi_end_time': '16:00',
        'f_bi_hours': 7.5,
        'f_bi_duration_hours': 7.5,
    }
    assert _leave_hours(answers) == 7.5


def test_legacy_row_without_duration_falls_back_to_span():
    # Legacy/Connecteam rows carry no net duration and no lunch baked into the
    # end time, so the raw span is the intended value.
    answers = {'f_bi_start_time': '09:00', 'f_bi_end_time': '11:00'}
    assert _leave_hours(answers) == 2.0


def test_row_with_only_numeric_hours():
    answers = {'f_bi_hours': 4.0}
    assert _leave_hours(answers) == 4.0
