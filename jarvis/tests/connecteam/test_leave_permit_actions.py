import pytest
from core.connectors.connecteam.services import leave_permit_actions as lpa

def _sub(status='approved', uid=9, company_id=11):
    return {'id': 42, 'respondent_user_id': uid, 'status': status,
            'answers': {'f_bi_hours': 1.5}, 'form_id': 7, 'company_id': company_id}

def test_cancel_not_owner_raises(monkeypatch):
    monkeypatch.setattr(lpa, '_get_submission', lambda sid: _sub(uid=1))
    with pytest.raises(PermissionError):
        lpa.cancel_leave_permit(42, user_id=9)

def test_cancel_pending_withdraws(monkeypatch):
    monkeypatch.setattr(lpa, '_get_submission', lambda sid: _sub(status='flagged'))
    monkeypatch.setattr(lpa, '_pending_request_id', lambda sid: 100)
    called = {}
    monkeypatch.setattr(lpa, '_engine_cancel',
                        lambda rid, uid, reason=None: called.setdefault('cancel', (rid, uid, reason)))
    out = lpa.cancel_leave_permit(42, user_id=9, reason='m-am răzgândit')
    assert out == {'status': 'cancelled'} and called['cancel'] == (100, 9, 'm-am răzgândit')

def test_cancel_approved_opens_cancellation(monkeypatch):
    monkeypatch.setattr(lpa, '_get_submission', lambda sid: _sub(status='approved'))
    monkeypatch.setattr(lpa, '_pending_request_id', lambda sid: None)
    opened = {}
    monkeypatch.setattr(lpa, '_open_cancellation_approval',
                        lambda sub, uid, reason=None: opened.setdefault('open', (sub['id'], reason)))
    monkeypatch.setattr(lpa, '_set_status', lambda sid, st: opened.setdefault('status', (sid, st)))
    out = lpa.cancel_leave_permit(42, user_id=9, reason='nu mai am nevoie')
    assert out == {'status': 'cancellation_pending'}
    assert opened['open'] == (42, 'nu mai am nevoie') and opened['status'] == (42, 'cancellation_pending')

def test_cancel_already_cancelled_raises(monkeypatch):
    monkeypatch.setattr(lpa, '_get_submission', lambda sid: _sub(status='cancelled'))
    monkeypatch.setattr(lpa, '_pending_request_id', lambda sid: None)
    with pytest.raises(ValueError):
        lpa.cancel_leave_permit(42, user_id=9)

def test_cancel_second_time_while_cancellation_pending_raises(monkeypatch):
    # Carried-over fix: a submission already in 'cancellation_pending' has an
    # open cancellation-approval request, so without a status guard the old
    # code would take the pending->withdraw branch and wrongly report
    # {'status': 'cancelled'}, leaving the submission STUCK at
    # 'cancellation_pending'. The guard must reject before that branch runs.
    monkeypatch.setattr(lpa, '_get_submission', lambda sid: _sub(status='cancellation_pending'))
    engine_called = {}
    monkeypatch.setattr(lpa, '_pending_request_id', lambda sid: 100)  # cancellation-approval is pending
    monkeypatch.setattr(lpa, '_engine_cancel', lambda rid, uid: engine_called.setdefault('cancel', (rid, uid)))
    with pytest.raises(ValueError):
        lpa.cancel_leave_permit(42, user_id=9)
    assert 'cancel' not in engine_called

def test_modify_non_pending_raises(monkeypatch):
    monkeypatch.setattr(lpa, '_get_submission', lambda sid: _sub(status='approved'))
    monkeypatch.setattr(lpa, '_pending_request_id', lambda sid: None)
    with pytest.raises(ValueError):
        lpa.update_leave_permit(42, user_id=9, answers={'f_bi_duration_hours': '1'})


def test_open_cancellation_approval_resolves_approver_from_sincron(monkeypatch):
    # Leave cancellation resolves the manager from the Sincron organigram
    # (get_direct_manager by user), aligned with leave approval.
    import core.organization.manager_utils as mu
    from core.approvals.engine import ApprovalEngine

    calls = {}

    def fake_mgr(user_id):
        calls['mgr_uid'] = user_id
        return {'id': 55, 'name': 'Manager', 'email': 'm@x.com'}

    def fake_submit(self, entity_type, entity_id, context, requested_by):
        calls['submit_context'] = context
        return {'id': 999}

    monkeypatch.setattr(mu, 'get_direct_manager', fake_mgr)
    monkeypatch.setattr(ApprovalEngine, 'submit', fake_submit)

    sub = _sub(status='approved', uid=9, company_id=17)
    lpa._open_cancellation_approval(sub, user_id=9)

    assert calls['mgr_uid'] == 9
    assert calls['submit_context']['approver_user_id'] == 55
    assert calls['submit_context']['cancellation'] is True


def test_cancel_approved_resolves_approver_from_sincron(monkeypatch):
    # End-to-end through cancel_leave_permit: the real _open_cancellation_approval
    # must be reachable and resolve the manager from Sincron (by user).
    import core.organization.manager_utils as mu
    from core.approvals.engine import ApprovalEngine

    monkeypatch.setattr(lpa, '_get_submission', lambda sid: _sub(status='approved', company_id=23))
    monkeypatch.setattr(lpa, '_pending_request_id', lambda sid: None)
    monkeypatch.setattr(lpa, '_set_status', lambda sid, st: None)

    calls = {}

    def fake_mgr(user_id):
        calls['uid'] = user_id
        return {'id': 7, 'name': 'M', 'email': 'e'}
    monkeypatch.setattr(mu, 'get_direct_manager', fake_mgr)
    monkeypatch.setattr(ApprovalEngine, 'submit', lambda self, **kw: {'id': 1})

    out = lpa.cancel_leave_permit(42, user_id=9)

    assert out == {'status': 'cancellation_pending'}
    assert calls['uid'] == 9
