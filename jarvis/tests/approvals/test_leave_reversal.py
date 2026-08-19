"""Tests for leave permit reversal functionality."""
from core.approvals.handlers import entity_form


class FakeSubRepo:
    def get_by_id(self, sid):
        return {'id': sid, 'form_id': 7, 'respondent_user_id': 9,
                'answers': {'f_bi_hours': 1.5, 'f_bi_leave_date': '2026-08-25'}}


def test_reverse_posts_credit_with_distinct_reference(monkeypatch):
    calls = {}

    # Mock FormRepository
    import forms.repositories as fr
    monkeypatch.setattr(fr, 'FormRepository',
        lambda: type('F', (), {'get_by_id': lambda self, fid: {'slug': 'bilet-de-invoire'}})(),
        raising=False)

    # Mock TimeBankService.credit
    import hr.time_bank.service as tbs
    def fake_credit(self, user_id, amount, tx_type, description=None,
                    reference_type=None, reference_id=None, created_by=None):
        calls.update(dict(user_id=user_id, amount=amount, tx_type=tx_type,
                          reference_type=reference_type, reference_id=reference_id))
        return {'id': 1}
    monkeypatch.setattr(tbs.TimeBankService, 'credit', fake_credit)

    entity_form._reverse_leave_permit_hours(42, FakeSubRepo())

    assert calls == dict(user_id=9, amount=1.5, tx_type='leave_permit_reversal',
                         reference_type='form_submission_cancel', reference_id=42)
