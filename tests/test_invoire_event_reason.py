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

    def _service_with_balance(self, monkeypatch, balance):
        svc = FormService()
        monkeypatch.setattr(svc, 'get_leave_form_config',
                            lambda: {'reasons': [EVENT], 'terms_text': 'x'})
        monkeypatch.setattr(svc, 'get_time_bank_balance', lambda uid: balance)
        return svc

    def test_rejected_when_balance_zero(self, monkeypatch):
        svc = self._service_with_balance(monkeypatch, 0.0)
        with pytest.raises(ValueError, match='ore disponibile'):
            svc.validate_and_normalize_leave_answers(1, self._valid_event_answers())

    def test_rejected_when_balance_negative(self, monkeypatch):
        svc = self._service_with_balance(monkeypatch, -3.5)
        with pytest.raises(ValueError, match='ore disponibile'):
            svc.validate_and_normalize_leave_answers(1, self._valid_event_answers())

    def test_other_reason_not_gated_by_balance(self, monkeypatch):
        """A non-event reason must not hit the balance guard (would fail later on
        the DB-backed schedule lookup, not on the balance message)."""
        svc = FormService()
        monkeypatch.setattr(svc, 'get_leave_form_config',
                            lambda: {'reasons': ['Personal', EVENT], 'terms_text': 'x'})
        # If the balance guard wrongly fired, it would raise the 'ore disponibile'
        # message; assert we get past it (any other failure is acceptable here).
        monkeypatch.setattr(svc, 'get_time_bank_balance', lambda uid: 0.0)
        answers = {**self._valid_event_answers(), 'f_bi_reason': 'Personal'}
        try:
            svc.validate_and_normalize_leave_answers(1, answers)
        except ValueError as e:
            assert 'ore disponibile' not in str(e)
