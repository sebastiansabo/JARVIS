import pytest
from core.connectors.connecteam.services import leave_permit_actions as lpa

def _sub(status='approved', uid=9):
    return {'id': 42, 'respondent_user_id': uid, 'status': status,
            'answers': {'f_bi_hours': 1.5}, 'form_id': 7}

def test_cancel_not_owner_raises(monkeypatch):
    monkeypatch.setattr(lpa, '_get_submission', lambda sid: _sub(uid=1))
    with pytest.raises(PermissionError):
        lpa.cancel_leave_permit(42, user_id=9)

def test_cancel_pending_withdraws(monkeypatch):
    monkeypatch.setattr(lpa, '_get_submission', lambda sid: _sub(status='flagged'))
    monkeypatch.setattr(lpa, '_pending_request_id', lambda sid: 100)
    called = {}
    monkeypatch.setattr(lpa, '_engine_cancel', lambda rid, uid: called.setdefault('cancel', (rid, uid)))
    out = lpa.cancel_leave_permit(42, user_id=9)
    assert out == {'status': 'cancelled'} and called['cancel'] == (100, 9)

def test_cancel_approved_opens_cancellation(monkeypatch):
    monkeypatch.setattr(lpa, '_get_submission', lambda sid: _sub(status='approved'))
    monkeypatch.setattr(lpa, '_pending_request_id', lambda sid: None)
    opened = {}
    monkeypatch.setattr(lpa, '_open_cancellation_approval', lambda sub, uid: opened.setdefault('open', sub['id']))
    monkeypatch.setattr(lpa, '_set_status', lambda sid, st: opened.setdefault('status', (sid, st)))
    out = lpa.cancel_leave_permit(42, user_id=9)
    assert out == {'status': 'cancellation_pending'} and opened['status'] == (42, 'cancellation_pending')

def test_cancel_already_cancelled_raises(monkeypatch):
    monkeypatch.setattr(lpa, '_get_submission', lambda sid: _sub(status='cancelled'))
    monkeypatch.setattr(lpa, '_pending_request_id', lambda sid: None)
    with pytest.raises(ValueError):
        lpa.cancel_leave_permit(42, user_id=9)

def test_modify_non_pending_raises(monkeypatch):
    monkeypatch.setattr(lpa, '_get_submission', lambda sid: _sub(status='approved'))
    monkeypatch.setattr(lpa, '_pending_request_id', lambda sid: None)
    with pytest.raises(ValueError):
        lpa.update_leave_permit(42, user_id=9, answers={'f_bi_duration_hours': '1'})
