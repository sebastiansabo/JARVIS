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
    start, end, kind = compute_report_window(date(2026, 11, 9))
    assert (start, end, kind) == (date(2026, 11, 2), date(2026, 11, 6), 'weekly')


def test_midweek_day_without_month_end_is_noop():
    assert compute_report_window(date(2026, 10, 28)) == (None, None, None)


def test_month_end_wednesday_triggers_closing_report_next_morning():
    start, end, kind = compute_report_window(date(2026, 10, 1))
    assert kind == 'month_close'
    assert (start, end) == (date(2026, 9, 28), date(2026, 9, 30))


def test_month_end_thursday_triggers_closing_report_friday():
    start, end, kind = compute_report_window(date(2026, 5, 1))
    assert kind == 'month_close'
    assert (start, end) == (date(2026, 4, 27), date(2026, 4, 30))


def test_month_end_friday_has_no_separate_closing_report():
    assert compute_report_window(date(2026, 8, 1)) == (None, None, None)


def test_month_end_weekend_is_ignored():
    assert compute_report_window(date(2026, 11, 1)) == (None, None, None)
    start, end, kind = compute_report_window(date(2026, 11, 2))
    assert kind == 'weekly' and start == date(2026, 10, 26) and end == date(2026, 10, 30)


def test_monday_after_midweek_month_end_covers_only_new_month_days():
    start, end, kind = compute_report_window(date(2026, 10, 5))
    assert kind == 'weekly'
    assert (start, end) == (date(2026, 10, 1), date(2026, 10, 2))


def test_month_end_monday_closes_single_day_next_day():
    start, end, kind = compute_report_window(date(2026, 12, 1))
    assert kind == 'month_close'
    assert (start, end) == (date(2026, 11, 30), date(2026, 11, 30))


def test_previous_working_week():
    assert previous_working_week(date(2026, 10, 28)) == (date(2026, 10, 19), date(2026, 10, 23))


# ------------------------------------------- divergence rules (hours-based model)
MON = date(2026, 10, 19)
CONTRACT = {'static_start': '08:00', 'static_end': '17:00', 'lunch': 60, 'norma': 8}  # required = 480 min


def _svc():
    return PunchComplianceService.__new__(PunchComplianceService)  # no DB


def _punch(day, first, last, n):
    def at(hm):
        return datetime(day.year, day.month, day.day, int(hm[:2]), int(hm[3:5]))
    return {(1, day): {'first_p': at(first), 'last_p': at(last), 'n': n}}


def _day(punches, timesheets=None, permits=None, leave_codes=frozenset({'CO'}),
         contract=CONTRACT, tol=10):
    return _svc()._analyse_day(1, MON, contract, timesheets or {}, punches,
                               permits or set(), leave_codes, tol)


def test_hours_met_on_schedule_is_compliant():
    # 08:00-17:00 minus 1h lunch = 8h, on time → nothing to report.
    assert _day(_punch(MON, '08:00', '17:00', 4)) is None


def test_late_but_full_hours_is_mismatch_not_deficit():
    # Boștiog/Radoi pattern: 08:51→18:00 = ~8h08 worked, start shifted → OK-general list.
    r = _day(_punch(MON, '08:51', '18:00', 4))
    assert r['kind'] == 'mismatch'


def test_short_hours_is_deficit_with_missing_minutes():
    # 08:00-16:00 minus lunch = 7h → 60 min under norm.
    r = _day(_punch(MON, '08:00', '16:00', 4))
    assert r['kind'] == 'deficit' and r['missing'] == 60


def test_absence_flags_full_norma():
    r = _day({})  # no punch rows → n == 0
    assert r['kind'] == 'absent' and r['missing'] == 480


def test_single_punch_is_incomplete():
    r = _day(_punch(MON, '08:05', '08:05', 1))
    assert r['kind'] == 'incomplete' and r['missing'] is None


def test_small_hours_shortfall_within_tolerance_is_hidden():
    # worked 7h55 (5 min short), on-time start → within tolerance, compliant.
    assert _day(_punch(MON, '08:00', '16:55', 4)) is None


def test_early_arrival_with_full_hours_is_mismatch():
    # 07:30 start (30 min early), full hours → outside schedule but OK.
    assert _day(_punch(MON, '07:30', '17:30', 4))['kind'] == 'mismatch'


def test_overtime_with_on_time_start_is_compliant():
    # On-time arrival, leaves late → only a start shift triggers the mismatch list.
    assert _day(_punch(MON, '08:00', '18:00', 4)) is None


def test_full_day_leave_code_is_excused():
    ts = {(1, MON): [{'short_code': 'CO', 'program_in': None,
                      'program_out': None, 'program_break': None}]}
    assert _day({}, timesheets=ts) is None


def test_approved_permit_is_excused():
    assert _day(_punch(MON, '10:00', '14:00', 4), permits={(1, MON)}) is None


def test_worked_code_program_overrides_static_schedule():
    ts = {(1, MON): [{'short_code': 'OZ', 'program_in': '09:00',
                      'program_out': '18:00', 'program_break': 60}]}
    assert _day(_punch(MON, '09:05', '18:00', 4), timesheets=ts) is None


def test_no_schedule_cannot_be_assessed():
    assert _day(_punch(MON, '10:00', '11:00', 4), contract=None) is None
