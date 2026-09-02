"""Tests for the "Ore Libere din Eveniment" leave reason — always offered by the
Invoire module, but only valid while the pooled Time Bank balance is > 0."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from forms.services.form_service import FormService

EVENT = FormService.EVENT_HOURS_REASON


# ---- config: the reason is always present ----

class TestLeaveFormConfigReasons:
    def test_event_reason_appended_to_defaults(self):
        cfg = FormService._leave_form_config_from_schema([])
        assert EVENT in cfg['reasons']
        assert cfg['event_hours_reason'] == EVENT

    def test_event_reason_appended_after_schema_reasons(self):
        schema = [{'id': 'f_bi_reason', 'options': ['Personal', 'Pauza de masa']}]
        cfg = FormService._leave_form_config_from_schema(schema)
        assert cfg['reasons'] == ['Personal', 'Pauza de masa', EVENT]

    def test_not_duplicated_when_schema_already_lists_it(self):
        schema = [{'id': 'f_bi_reason', 'options': ['Personal', EVENT]}]
        cfg = FormService._leave_form_config_from_schema(schema)
        assert cfg['reasons'].count(EVENT) == 1

    def test_dedup_is_case_insensitive(self):
        schema = [{'id': 'f_bi_reason', 'options': [EVENT.lower()]}]
        cfg = FormService._leave_form_config_from_schema(schema)
        assert cfg['reasons'].count(EVENT) == 0  # keeps the schema's own casing, no extra
        assert len(cfg['reasons']) == 1


# ---- submit guard: event reason needs a positive balance ----

class TestEventReasonBalanceGuard:
    def _valid_event_answers(self):
        return {
            'f_bi_leave_date': '2026-09-10',
            'f_bi_start_time': '09:00',
            'f_bi_duration_hours': '2',
            'f_bi_reason': EVENT,
            'f_bi_terms_accepted': True,
            'signature_image': 'data:image/png;base64,AAAA',
        }

    def _service_with_event(self, monkeypatch, event_balance):
        svc = FormService()
        monkeypatch.setattr(svc, 'get_leave_form_config',
                            lambda: {'reasons': ['Personal', EVENT], 'terms_text': 'x'})
        monkeypatch.setattr(svc, 'get_time_bank_split',
                            lambda uid: {'total': event_balance, 'event': event_balance, 'personal': 0.0})
        return svc

    def test_rejected_when_event_balance_zero(self, monkeypatch):
        svc = self._service_with_event(monkeypatch, 0.0)
        with pytest.raises(ValueError, match='disponibile'):
            svc.validate_and_normalize_leave_answers(1, self._valid_event_answers())

    def test_event_duration_capped_to_balance(self, monkeypatch):
        svc = self._service_with_event(monkeypatch, 6.0)
        answers = {**self._valid_event_answers(), 'f_bi_duration_hours': '8'}
        with pytest.raises(ValueError, match='cel mult'):
            svc.validate_and_normalize_leave_answers(1, answers)

    def test_event_within_cap_passes_event_gate(self, monkeypatch):
        # 4h requested against a 6h event balance must clear the event guard
        # (may still fail later on the DB-backed schedule lookup).
        svc = self._service_with_event(monkeypatch, 6.0)
        answers = {**self._valid_event_answers(), 'f_bi_duration_hours': '4'}
        try:
            svc.validate_and_normalize_leave_answers(1, answers)
        except ValueError as e:
            assert 'disponibile' not in str(e) and 'cel mult' not in str(e)

    def test_personal_reason_not_capped_by_event(self, monkeypatch):
        """Personal leave must not hit the event cap even with a 0 event balance."""
        svc = self._service_with_event(monkeypatch, 0.0)
        answers = {**self._valid_event_answers(), 'f_bi_reason': 'Personal', 'f_bi_duration_hours': '8'}
        try:
            svc.validate_and_normalize_leave_answers(1, answers)
        except ValueError as e:
            assert 'disponibile' not in str(e) and 'cel mult' not in str(e)


# ---- which reasons debit the Time Bank ----

class TestReasonCountsAgainstBank:
    def test_personal_counts(self):
        assert FormService.reason_counts_against_bank('Personal') is True

    def test_event_reason_counts(self):
        assert FormService.reason_counts_against_bank(EVENT) is True

    def test_lunch_does_not_count(self):
        assert FormService.reason_counts_against_bank('Pauza de masa') is False

    def test_lunch_case_and_diacritic_insensitive(self):
        assert FormService.reason_counts_against_bank('  PAUZĂ DE MASĂ ') is False

    def test_config_exposes_non_counting_reasons(self):
        cfg = FormService._leave_form_config_from_schema([])
        assert 'Pauza de masa' in cfg['non_counting_reasons']


# ---- Corectie Ore backdate guard ----

class TestCorrectionBackdateGuard:
    def _answers(self, date_str):
        return {
            'f_bi_leave_date': date_str,
            'f_bi_start_time': '09:00',
            'f_bi_duration_hours': '2',
            'f_bi_reason': 'Personal',
            'f_bi_terms_accepted': True,
            'signature_image': 'data:image/png;base64,AAAA',
            'f_bi_is_correction': True,
        }

    def _svc(self, monkeypatch):
        svc = FormService()
        monkeypatch.setattr(svc, 'get_leave_form_config',
                            lambda: {'reasons': ['Personal'], 'terms_text': 'x'})
        monkeypatch.setattr(svc, 'get_time_bank_balance', lambda uid: 10.0)
        return svc

    def test_first_of_current_month_format(self):
        s = FormService._first_of_current_month()
        assert len(s) == 10 and s.endswith('-01')


    def test_rejects_date_before_current_month(self, monkeypatch):
        svc = self._svc(monkeypatch)
        with pytest.raises(ValueError, match='luna curent'):
            svc.validate_and_normalize_leave_answers(1, self._answers('2020-01-01'))

    def test_today_correction_passes_the_backdate_gate(self, monkeypatch):
        # A today-dated correction must NOT trip the backdate guard (it may fail
        # later on the DB-backed schedule lookup, but not with the backdate message).
        from datetime import date
        svc = self._svc(monkeypatch)
        try:
            svc.validate_and_normalize_leave_answers(1, self._answers(date.today().isoformat()))
        except ValueError as e:
            assert 'luna curent' not in str(e)


# ---- leave duration day-cap (full workday, not norma − lunch) ----

class TestLeaveDayCap:
    def test_full_workday_cap_equals_norma(self):
        from core.connectors.connecteam.services.leave_schedule import _day_cap
        # 8h contracted work + 1h lunch → a full-day leave is still 8h (not 7h).
        assert _day_cap(8.0, 60) == 8.0

    def test_part_time_cap(self):
        from core.connectors.connecteam.services.leave_schedule import _day_cap
        assert _day_cap(4.0, 60) == 4.0

    def test_default_cap_is_eight(self):
        from core.connectors.connecteam.services.leave_schedule import _day_cap, DEFAULT_CAP
        assert DEFAULT_CAP == 8.0 and _day_cap(None) == 8.0

    def test_cap_clamped_at_max(self):
        from core.connectors.connecteam.services.leave_schedule import _day_cap
        assert _day_cap(12.0, 0) == 8.0

    def test_full_day_return_adds_lunch(self):
        from core.connectors.connecteam.services.leave_schedule import compute_return, _full_day_lunch
        sched = {'day_cap_hours': 8.0, 'lunch_break_minutes': 60}
        assert _full_day_lunch(8.0, sched) == 60
        assert compute_return('08:00', 8.0, _full_day_lunch(8.0, sched)) == '17:00'

    def test_partial_leave_no_lunch(self):
        from core.connectors.connecteam.services.leave_schedule import compute_return, _full_day_lunch
        sched = {'day_cap_hours': 8.0, 'lunch_break_minutes': 60}
        assert _full_day_lunch(4.0, sched) == 0
        assert compute_return('08:00', 4.0, _full_day_lunch(4.0, sched)) == '12:00'

    def test_full_day_return_no_lunch_when_zero(self):
        from core.connectors.connecteam.services.leave_schedule import compute_return, _full_day_lunch
        sched = {'day_cap_hours': 4.0, 'lunch_break_minutes': 0}
        assert _full_day_lunch(4.0, sched) == 0
        assert compute_return('08:00', 4.0, 0) == '12:00'
