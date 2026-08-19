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


def test_open_cancellation_approval_resolves_approver_with_submission_company_id(monkeypatch):
    # Minor A fix: resolve_approver's 2nd arg is company_id, used ONLY as a fallback
    # when the requester has no org_unit_id parent (e.g. a leave that was granted
    # via an explicit second approver with no org-structure parent). Passing None
    # broke that L0 fallback, stranding the cancellation request with no approver.
    from accounting.vouchers.services.voucher_service import VoucherService
    from core.approvals.engine import ApprovalEngine

    calls = {}

    def fake_resolve_approver(self, user_id, company_id, explicit_approver_id):
        calls['resolve_approver'] = (user_id, company_id, explicit_approver_id)
        return {'id': 55, 'name': 'Manager', 'email': 'm@x.com'}

    def fake_submit(self, entity_type, entity_id, context, requested_by):
        calls['submit_context'] = context
        return {'id': 999}

    monkeypatch.setattr(VoucherService, 'resolve_approver', fake_resolve_approver)
    monkeypatch.setattr(ApprovalEngine, 'submit', fake_submit)

    sub = _sub(status='approved', uid=9, company_id=17)
    lpa._open_cancellation_approval(sub, user_id=9)

    assert calls['resolve_approver'] == (9, 17, None)
    assert calls['submit_context']['cancellation'] is True


def test_cancel_approved_passes_submission_company_id_to_approver_resolution(monkeypatch):
    # End-to-end through cancel_leave_permit: the real _open_cancellation_approval
    # (not monkeypatched away) must be reachable and forward sub['company_id'].
    from accounting.vouchers.services.voucher_service import VoucherService
    from core.approvals.engine import ApprovalEngine

    monkeypatch.setattr(lpa, '_get_submission', lambda sid: _sub(status='approved', company_id=23))
    monkeypatch.setattr(lpa, '_pending_request_id', lambda sid: None)
    monkeypatch.setattr(lpa, '_set_status', lambda sid, st: None)

    calls = {}
    monkeypatch.setattr(VoucherService, 'resolve_approver',
                         lambda self, user_id, company_id, explicit_approver_id:
                         calls.setdefault('args', (user_id, company_id, explicit_approver_id)) and None)
    monkeypatch.setattr(ApprovalEngine, 'submit', lambda self, **kw: {'id': 1})

    out = lpa.cancel_leave_permit(42, user_id=9)

    assert out == {'status': 'cancellation_pending'}
    assert calls['args'] == (9, 23, None)
