"""Fast-follow: modify must not silently drop notes / 2nd approver.
get_leave_permit exposes the full stored answers for the edit prefill, and
update_leave_permit merges over the stored answers so untouched fields survive."""
import pytest
from core.connectors.connecteam.services import leave_permit_actions as lpa


def _sub_full(status='flagged', uid=9):
    return {'id': 42, 'respondent_user_id': uid, 'status': status, 'form_id': 7, 'company_id': 11,
            'answers': {'f_bi_leave_date': '2026-08-25', 'f_bi_start_time': '09:00',
                        'f_bi_duration_hours': '1.5', 'f_bi_reason': 'Personal',
                        'f_bi_second_approver': '7', 'f_bi_notes': 'la medic', 'f_bi_destination': 'X'}}


def test_get_leave_permit_returns_notes_and_second_approver(monkeypatch):
    monkeypatch.setattr(lpa, '_get_submission', lambda sid: _sub_full())
    out = lpa.get_leave_permit(42, user_id=9)
    assert out['answers']['f_bi_notes'] == 'la medic'
    assert out['answers']['f_bi_second_approver'] == '7'
    assert out['status'] == 'flagged'


def test_get_leave_permit_non_owner_raises(monkeypatch):
    monkeypatch.setattr(lpa, '_get_submission', lambda sid: _sub_full(uid=1))
    with pytest.raises(PermissionError):
        lpa.get_leave_permit(42, user_id=9)


def test_get_leave_permit_missing_raises(monkeypatch):
    monkeypatch.setattr(lpa, '_get_submission', lambda sid: None)
    with pytest.raises(ValueError):
        lpa.get_leave_permit(42, user_id=9)


def test_update_merges_over_existing_preserving_untouched_fields(monkeypatch):
    monkeypatch.setattr(lpa, '_get_submission', lambda sid: _sub_full())
    monkeypatch.setattr(lpa, '_pending_request_id', lambda sid: 100)
    import forms.services.form_service as fs
    monkeypatch.setattr(fs.FormService, 'validate_and_normalize_leave_answers',
                        lambda self, uid, ans: {'f_bi_hours': 1.5, 'f_bi_notes': 'edited'})
    captured = {}
    import forms.repositories as fr

    class Repo:
        def update_answers(self, sid, ans):
            captured['ans'] = ans
            return True
    monkeypatch.setattr(fr, 'SubmissionRepository', lambda: Repo(), raising=False)
    lpa.update_leave_permit(42, user_id=9, answers={'f_bi_notes': 'edited'})
    assert captured['ans']['f_bi_destination'] == 'X'   # preserved from stored answers
    assert captured['ans']['f_bi_notes'] == 'edited'    # edited value wins over stored
    assert captured['ans']['f_bi_hours'] == 1.5
