"""Leave-permit multi-approver routing: f_bi_second_approver is a comma-separated
list of picked user ids that REPLACE the default direct manager (all can approve);
empty falls back to the org-hierarchy manager."""
from forms.services.form_service import FormService
import core.approvals.engine as eng
import accounting.vouchers.services as vouchers


def test_parse_approver_ids_multi_single_and_junk():
    assert FormService._parse_approver_ids({'f_bi_second_approver': '7,12,7'}) == [7, 12]
    assert FormService._parse_approver_ids({'f_bi_second_approver': '9'}) == [9]
    assert FormService._parse_approver_ids({'f_bi_second_approver': ''}) == []
    assert FormService._parse_approver_ids({}) == []
    assert FormService._parse_approver_ids({'f_bi_second_approver': 'x, 3 , '}) == [3]


def _stub(monkeypatch, svc, cap):
    monkeypatch.setattr(svc, '_resolve_form_approver', lambda *a, **k: 99)  # direct manager
    monkeypatch.setattr(svc.submission_repo, 'set_approval_request', lambda *a, **k: None, raising=False)
    monkeypatch.setattr(svc.submission_repo, 'update_status', lambda *a, **k: None, raising=False)
    monkeypatch.setattr(svc, '_send_submit_notifications', lambda *a, **k: None, raising=False)

    class FakeEngine:
        def submit(self, **kw):
            cap.update(kw)
            return {'request_id': 1}
    monkeypatch.setattr(eng, 'ApprovalEngine', FakeEngine)


def test_picked_approvers_replace_direct_manager(monkeypatch):
    svc = FormService()
    monkeypatch.setattr(svc.submission_repo, 'get_by_id',
                        lambda sid: {'answers': {'f_bi_second_approver': '7,12'}}, raising=False)
    cap = {}
    _stub(monkeypatch, svc, cap)
    svc._trigger_approval({'id': 5, 'company_id': 11, 'approval_config': {}}, 5,
                          {'user_id': 3, 'explicit_approver_id': None})
    ctx = cap['context']
    assert ctx['stakeholder_approver_ids'] == [7, 12]   # picked replace; 99 excluded
    assert ctx['approver_user_id'] == 7


def test_no_pick_falls_back_to_direct_manager(monkeypatch):
    svc = FormService()
    monkeypatch.setattr(svc.submission_repo, 'get_by_id',
                        lambda sid: {'answers': {}}, raising=False)
    cap = {}
    _stub(monkeypatch, svc, cap)
    svc._trigger_approval({'id': 5, 'company_id': 11, 'approval_config': {}}, 5,
                          {'user_id': 3, 'explicit_approver_id': None})
    ctx = cap['context']
    assert ctx['stakeholder_approver_ids'] == [99]      # direct manager only
    assert ctx['approver_user_id'] == 99


def _fake_voucher(monkeypatch, result):
    class FakeVoucher:
        def resolve_approver(self, uid, cid, explicit_approver_id=None):
            return result
    monkeypatch.setattr(vouchers, 'VoucherService', FakeVoucher)


def test_default_leave_approver_shape(monkeypatch):
    """The auto-selected chip data is {id, name} from the SAME resolver the
    approval trigger uses, using the leave form's company_id."""
    svc = FormService()
    seen = {}
    monkeypatch.setattr(svc.form_repo, 'get_by_slug',
                        lambda slug: {'company_id': 11}, raising=False)

    class FakeVoucher:
        def resolve_approver(self, uid, cid, explicit_approver_id=None):
            seen['uid'], seen['cid'] = uid, cid
            return {'id': 99, 'name': 'Manager X', 'email': 'm@x.ro'}
    monkeypatch.setattr(vouchers, 'VoucherService', FakeVoucher)

    assert svc.get_default_leave_approver(3) == {'id': 99, 'name': 'Manager X'}
    assert seen == {'uid': 3, 'cid': 11}


def test_default_leave_approver_none_when_unresolved(monkeypatch):
    svc = FormService()
    monkeypatch.setattr(svc.form_repo, 'get_by_slug', lambda slug: None, raising=False)
    _fake_voucher(monkeypatch, None)
    assert svc.get_default_leave_approver(3) is None
