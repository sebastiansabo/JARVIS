"""Cancelling a leave permit carries the requester's motive: a self-withdraw passes
it to the engine cancel; an approved-leave cancellation request stores it in the
approval context so the manager sees why."""
import core.approvals.engine as eng
import accounting.vouchers.services.voucher_service as vs
from core.connectors.connecteam.services import leave_permit_actions as lpa


def test_withdraw_passes_reason_to_engine(monkeypatch):
    seen = {}

    class FakeEngine:
        def cancel(self, rid, uid, reason=None):
            seen['cancel'] = (rid, uid, reason)
    monkeypatch.setattr(eng, 'ApprovalEngine', FakeEngine)
    monkeypatch.setattr(lpa, '_get_submission',
                        lambda sid: {'id': sid, 'respondent_user_id': 5, 'status': 'pending'})
    monkeypatch.setattr(lpa, '_pending_request_id', lambda sid: 99)

    assert lpa.cancel_leave_permit(7, 5, reason='plec la medic') == {'status': 'cancelled'}
    assert seen['cancel'] == (99, 5, 'plec la medic')


def test_cancellation_request_stores_reason_in_context(monkeypatch):
    seen = {}

    class FakeEngine:
        def submit(self, entity_type, entity_id, context, requested_by):
            seen['ctx'] = context
    monkeypatch.setattr(eng, 'ApprovalEngine', FakeEngine)

    class FakeVoucher:
        def resolve_approver(self, uid, cid, explicit=None):
            return {'id': 3, 'name': 'Manager'}
    monkeypatch.setattr(vs, 'VoucherService', FakeVoucher)
    monkeypatch.setattr(lpa, '_get_submission', lambda sid: {
        'id': sid, 'respondent_user_id': 5, 'status': 'approved', 'company_id': 11})
    monkeypatch.setattr(lpa, '_pending_request_id', lambda sid: None)
    monkeypatch.setattr(lpa, '_set_status', lambda sid, st: None)

    assert lpa.cancel_leave_permit(7, 5, reason='nu mai am nevoie') == {'status': 'cancellation_pending'}
    assert seen['ctx']['cancellation'] is True
    assert seen['ctx']['cancellation_reason'] == 'nu mai am nevoie'
