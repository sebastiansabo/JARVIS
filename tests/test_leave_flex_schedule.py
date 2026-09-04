"""Per-employee flexible schedule for the Bilet de Invoire form.

A flexible employee's selectable window widens to their personal flex interval
(e.g. 08:00-18:00) instead of the Sincron program window. The day cap (norma)
and lunch are UNCHANGED — flexibility is about WHEN the workday sits, not its
length. Because get_leave_schedule is the single source of truth (form slots,
mobile slots, and submit-time validate_leave all read it), the widening flows
everywhere from here.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from core.connectors.connecteam.services import leave_schedule as ls


# ---- pure _apply_flex helper ----

class TestApplyFlex:
    def _sincron_result(self):
        return {
            'schedule_start': '09:00',
            'schedule_end': '17:00',
            'day_cap_hours': 8.0,
            'lunch_break_minutes': 60,
            'source': 'sincron',
            'selected_company': 'ACME',
            'flexible': False,
            'companies': [
                {'company_name': 'ACME', 'schedule_start': '09:00',
                 'schedule_end': '17:00', 'day_cap_hours': 8.0,
                 'lunch_break_minutes': 60, 'norma_lucru': 8.0},
            ],
        }

    def test_widens_top_level_window(self):
        out = ls._apply_flex(self._sincron_result(),
                             {'schedule_flexible': True, 'flex_start': '08:00', 'flex_end': '18:00'})
        assert out['schedule_start'] == '08:00'
        assert out['schedule_end'] == '18:00'
        assert out['flexible'] is True

    def test_keeps_day_cap_and_lunch(self):
        out = ls._apply_flex(self._sincron_result(),
                             {'schedule_flexible': True, 'flex_start': '08:00', 'flex_end': '18:00'})
        assert out['day_cap_hours'] == 8.0
        assert out['lunch_break_minutes'] == 60

    def test_widens_each_company_entry(self):
        out = ls._apply_flex(self._sincron_result(),
                             {'schedule_flexible': True, 'flex_start': '08:00', 'flex_end': '18:00'})
        c = out['companies'][0]
        assert c['schedule_start'] == '08:00' and c['schedule_end'] == '18:00'
        # per-company cap/lunch untouched
        assert c['day_cap_hours'] == 8.0 and c['lunch_break_minutes'] == 60

    def test_noop_when_not_flexible(self):
        out = ls._apply_flex(self._sincron_result(),
                             {'schedule_flexible': False, 'flex_start': '08:00', 'flex_end': '18:00'})
        assert out['schedule_start'] == '09:00' and out['schedule_end'] == '17:00'
        assert out['flexible'] is False

    def test_noop_when_flex_config_missing(self):
        out = ls._apply_flex(self._sincron_result(), None)
        assert out['schedule_start'] == '09:00' and out['schedule_end'] == '17:00'

    def test_ignores_invalid_window(self):
        # start >= end is nonsense — must not widen
        out = ls._apply_flex(self._sincron_result(),
                             {'schedule_flexible': True, 'flex_start': '18:00', 'flex_end': '08:00'})
        assert out['schedule_start'] == '09:00' and out['schedule_end'] == '17:00'

    def test_ignores_missing_bounds(self):
        out = ls._apply_flex(self._sincron_result(),
                             {'schedule_flexible': True, 'flex_start': None, 'flex_end': None})
        assert out['schedule_start'] == '09:00' and out['schedule_end'] == '17:00'


# ---- get_leave_schedule end-to-end (fetchers monkeypatched) ----

class TestGetLeaveScheduleFlex:
    def _patch(self, monkeypatch, rows, flex):
        monkeypatch.setattr(ls, '_fetch_company_schedules', lambda uid, d: rows)
        monkeypatch.setattr(ls, '_fetch_flex_config', lambda uid: flex)

    def _sincron_rows(self):
        return [{'company_name': 'ACME', 'norma_lucru': 8.0,
                 'schedule_start': '09:00', 'schedule_end': '17:00',
                 'lunch_break_minutes': 60}]

    def test_flexible_user_gets_wide_window(self, monkeypatch):
        self._patch(monkeypatch, self._sincron_rows(),
                    {'schedule_flexible': True, 'flex_start': '08:00', 'flex_end': '18:00'})
        sched = ls.get_leave_schedule(1, '2026-09-10')
        assert sched['schedule_start'] == '08:00'
        assert sched['schedule_end'] == '18:00'
        assert sched['day_cap_hours'] == 8.0          # norma cap unchanged
        assert sched['companies'][0]['schedule_start'] == '08:00'

    def test_non_flexible_user_keeps_sincron_window(self, monkeypatch):
        self._patch(monkeypatch, self._sincron_rows(), None)
        sched = ls.get_leave_schedule(1, '2026-09-10')
        assert sched['schedule_start'] == '09:00'
        assert sched['schedule_end'] == '17:00'

    def test_flex_applies_even_without_sincron_contract(self, monkeypatch):
        # no sincron rows -> normally the 07:00-18:00 default; flex must still win
        self._patch(monkeypatch, [],
                    {'schedule_flexible': True, 'flex_start': '08:00', 'flex_end': '18:00'})
        sched = ls.get_leave_schedule(1, '2026-09-10')
        assert sched['schedule_start'] == '08:00'
        assert sched['schedule_end'] == '18:00'


# ---- validation inherits the widened window ----

class TestValidationWithFlex:
    def test_early_start_rejected_on_sincron_window(self):
        sched = {'schedule_start': '09:00', 'schedule_end': '17:00', 'day_cap_hours': 8.0}
        assert ls.validate_leave('08:00', 4.0, sched) is not None

    def test_early_start_allowed_on_flex_window(self):
        # same 08:00 start clears once the window is the flex 08:00-18:00
        sched = {'schedule_start': '08:00', 'schedule_end': '18:00', 'day_cap_hours': 8.0}
        assert ls.validate_leave('08:00', 4.0, sched) is None
