"""Unit tests for the weekly punch-compliance digest.

DB-free: the scheduling window is a pure function, and the per-day divergence rule
is exercised on hand-built inputs (the service is instantiated via __new__ so no
DB connection is opened).
"""
from datetime import date, datetime

from tasks.punch_compliance_digest import compute_report_window, previous_working_week
from core.connectors.biostar.services.punch_compliance_service import PunchComplianceService


# --------------------------------------------------------------------- windows
def test_monday_reports_previous_full_working_week():
    # Mon 2026-11-09; the prior week (Nov 2–6) contains no mid-week month-end.
    start, end, kind = compute_report_window(date(2026, 11, 9))
    assert (start, end, kind) == (date(2026, 11, 2), date(2026, 11, 6), 'weekly')


def test_midweek_day_without_month_end_is_noop():
    # Wed 2026-10-28, yesterday not a month end, not a Monday → nothing to send.
    assert compute_report_window(date(2026, 10, 28)) == (None, None, None)


def test_month_end_wednesday_triggers_closing_report_next_morning():
    # Sep 2026 ends Wed 30th → closing report runs Thu Oct 1 for that partial week.
    start, end, kind = compute_report_window(date(2026, 10, 1))
    assert kind == 'month_close'
    assert (start, end) == (date(2026, 9, 28), date(2026, 9, 30))  # Mon..Wed


def test_month_end_thursday_triggers_closing_report_friday():
    # Apr 2026 ends Thu 30th → closing report runs Fri May 1 for Mon..Thu.
    start, end, kind = compute_report_window(date(2026, 5, 1))
    assert kind == 'month_close'
    assert (start, end) == (date(2026, 4, 27), date(2026, 4, 30))


def test_month_end_friday_has_no_separate_closing_report():
    # Jul 2026 ends Fri 31st (end of week) → Sat Aug 1 run sends nothing special.
    assert compute_report_window(date(2026, 8, 1)) == (None, None, None)


def test_month_end_weekend_is_ignored():
    # Oct 2026 ends Sat 31st → no mid-week closing; the next Monday covers the week.
    assert compute_report_window(date(2026, 11, 1)) == (None, None, None)  # Sunday, noop
    start, end, kind = compute_report_window(date(2026, 11, 2))           # Monday
    assert kind == 'weekly' and start == date(2026, 10, 26) and end == date(2026, 10, 30)


def test_monday_after_midweek_month_end_covers_only_new_month_days():
    # Sep 30 (Wed) was closed on Oct 1; Monday Oct 5 must report only Oct 1–2 of
    # the straddling week (Sep 28–Oct 2), never re-reporting Sep 28–30.
    start, end, kind = compute_report_window(date(2026, 10, 5))
    assert kind == 'weekly'
    assert (start, end) == (date(2026, 10, 1), date(2026, 10, 2))


def test_month_end_monday_closes_single_day_next_day():
    # Nov 2026 ends Mon 30th → Tue Dec 1 closing report for just that Monday.
    start, end, kind = compute_report_window(date(2026, 12, 1))
    assert kind == 'month_close'
    assert (start, end) == (date(2026, 11, 30), date(2026, 11, 30))


def test_previous_working_week():
    # Wed 2026-10-28 → previous full Mon–Fri is Oct 19–23.
    assert previous_working_week(date(2026, 10, 28)) == (date(2026, 10, 19), date(2026, 10, 23))


# ------------------------------------------------------------- divergence rules
MON = date(2026, 10, 19)  # a normal working Monday
CONTRACT = {'static_start': '08:00', 'static_end': '17:00', 'lunch': 60, 'norma': 8}


def _svc():
    return PunchComplianceService.__new__(PunchComplianceService)  # no DB


def _punch(day, first, last, n):
    def at(hm):
        h, m = map(int, hm.split(':'))
        return datetime(day.year, day.month, day.day, h, m)
    return {(1, day): {'first_p': at(first), 'last_p': at(last), 'n': n}}


def _day(punches, timesheets=None, permits=None, leave_codes=frozenset({'CO'}),
         contract=CONTRACT, tol=10):
    return _svc()._analyse_day(1, MON, contract, timesheets or {}, punches,
                               permits or set(), leave_codes, tol)


def test_late_beyond_tolerance_is_flagged_with_minutes():
    rows = _day(_punch(MON, '08:30', '17:05', 4))
    assert len(rows) == 1
    assert rows[0]['late'] == 30 and rows[0]['missing'] == 30
    assert 'Întârziere 30 min' in rows[0]['reasons']


def test_late_within_tolerance_is_not_flagged():
    assert _day(_punch(MON, '08:08', '16:55', 4)) == []


def test_exactly_tolerance_is_not_flagged():
    # 10 minutes late is not > 10 → clean.
    assert _day(_punch(MON, '08:10', '17:00', 4)) == []


def test_early_leave_beyond_tolerance_is_flagged():
    rows = _day(_punch(MON, '08:00', '16:30', 4))
    assert rows[0]['early'] == 30 and 'Plecare devreme 30 min' in rows[0]['reasons']


def test_overtime_is_not_a_divergence():
    # Early in, late out → respected the schedule, nothing flagged.
    assert _day(_punch(MON, '07:30', '18:00', 4)) == []


def test_absence_flags_full_norma_minutes():
    rows = _day({})  # no punch rows at all → n == 0
    assert rows[0]['absent'] == 480 and rows[0]['missing'] == 480
    assert 'Absent (fără pontaj)' in rows[0]['reasons']


def test_single_punch_is_incomplete():
    rows = _day(_punch(MON, '08:05', '08:05', 1))
    assert rows[0]['incomplete'] is True
    assert 'Pontaj incomplet (o singură marcare)' in rows[0]['reasons']


def test_full_day_leave_code_is_excused():
    ts = {(1, MON): [{'short_code': 'CO', 'program_in': None, 'program_out': None}]}
    assert _day({}, timesheets=ts) == []


def test_approved_permit_is_excused():
    assert _day(_punch(MON, '09:30', '17:00', 4), permits={(1, MON)}) == []


def test_worked_code_program_overrides_static_schedule():
    # Timesheet OZ program 09:00–18:00 overrides the 08:00 static start → 09:05 is fine.
    ts = {(1, MON): [{'short_code': 'OZ', 'program_in': '09:00', 'program_out': '18:00'}]}
    assert _day(_punch(MON, '09:05', '18:00', 4), timesheets=ts) == []


def test_no_schedule_cannot_be_assessed():
    assert _day(_punch(MON, '10:00', '11:00', 4), contract=None) == []


def test_weekend_and_holiday_days_are_skipped():
    svc = _svc()
    sat = date(2026, 10, 24)  # Saturday
    # Absent all week, but Saturday must never be analysed.
    rows = svc._analyse_user(1, sat, sat, CONTRACT, {}, {}, set(), set(),
                             frozenset({'CO'}), 10)
    assert rows == []
    # A weekday that is a public holiday is also skipped.
    rows = svc._analyse_user(1, MON, MON, CONTRACT, {}, {}, {MON}, set(),
                             frozenset({'CO'}), 10)
    assert rows == []
