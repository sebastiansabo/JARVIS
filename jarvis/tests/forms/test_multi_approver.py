"""Leave-permit multi-approver routing: f_bi_second_approver is a comma-separated
list of picked user ids that REPLACE the default direct manager (all can approve);
empty falls back to the direct manager. The leave default manager is resolved from
the Sincron organigram (get_direct_manager); other forms keep the JARVIS tree
(VoucherService)."""
from forms.services.form_service import FormService
import core.approvals.engine as eng
import accounting.vouchers.services as vouchers
import core.organization.manager_utils as mu


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


def _engine_repo_stubs(monkeypatch, svc, cap):
    monkeypatch.setattr(svc.submission_repo, 'set_approval_request', lambda *a, **k: None, raising=False)
    monkeypatch.setattr(svc.submission_repo, 'update_status', lambda *a, **k: None, raising=False)
    monkeypatch.setattr(svc, '_send_submit_notifications', lambda *a, **k: None, raising=False)

    class FakeEngine:
        def submit(self, **kw):
            cap.update(kw)
            return {'request_id': 1}
    monkeypatch.setattr(eng, 'ApprovalEngine', FakeEngine)


def test_default_leave_approver_reads_sincron(monkeypatch):
    """The auto-selected chip is the Sincron direct manager (get_direct_manager),
    not the JARVIS voucher tree."""
    svc = FormService()
    seen = {}

    def fake_mgr(uid):
        seen['uid'] = uid
        return {'id': 99, 'name': 'Manager X', 'email': 'm@x.ro'}
    monkeypatch.setattr(mu, 'get_direct_manager', fake_mgr)

    class BoomVoucher:
        def resolve_approver(self, *a, **k):
            raise AssertionError('leave must not use the voucher/JARVIS tree')
    monkeypatch.setattr(vouchers, 'VoucherService', BoomVoucher)

    assert svc.get_default_leave_approver(3) == {'id': 99, 'name': 'Manager X'}
    assert seen == {'uid': 3}


def test_default_leave_approver_none_when_no_sincron_manager(monkeypatch):
    svc = FormService()
    monkeypatch.setattr(mu, 'get_direct_manager', lambda uid: None)  # unmapped / no responsable
    assert svc.get_default_leave_approver(3) is None


def test_leave_trigger_uses_sincron_manager(monkeypatch):
    """No pick on the leave form → default approver is the Sincron manager."""
    svc = FormService()
    monkeypatch.setattr(svc.submission_repo, 'get_by_id',
                        lambda sid: {'answers': {}}, raising=False)
    cap = {}
    _engine_repo_stubs(monkeypatch, svc, cap)
    monkeypatch.setattr(mu, 'get_direct_manager', lambda uid: {'id': 77, 'name': 'S', 'email': 'e'})

    class BoomVoucher:
        def resolve_approver(self, *a, **k):
            raise AssertionError('leave must not use the voucher tree')
    monkeypatch.setattr(vouchers, 'VoucherService', BoomVoucher)

    svc._trigger_approval(
        {'id': 5, 'company_id': 11, 'slug': svc.LEAVE_FORM_SLUG, 'approval_config': {}}, 5,
        {'user_id': 3, 'explicit_approver_id': None})
    ctx = cap['context']
    assert ctx['approver_user_id'] == 77 and ctx['stakeholder_approver_ids'] == [77]


def test_non_leave_trigger_uses_voucher_tree(monkeypatch):
    """A non-leave form keeps the JARVIS voucher-tree resolution."""
    svc = FormService()
    monkeypatch.setattr(svc.submission_repo, 'get_by_id',
                        lambda sid: {'answers': {}}, raising=False)
    cap = {}
    _engine_repo_stubs(monkeypatch, svc, cap)
    # Sincron would say 77, but a non-leave form must use the voucher tree (55).
    monkeypatch.setattr(mu, 'get_direct_manager', lambda uid: {'id': 77, 'name': 'S', 'email': 'e'})

    class FakeVoucher:
        def resolve_approver(self, uid, cid, explicit_approver_id=None):
            return {'id': 55, 'name': 'V', 'email': 'v@x.ro'}
    monkeypatch.setattr(vouchers, 'VoucherService', FakeVoucher)

    svc._trigger_approval(
        {'id': 5, 'company_id': 11, 'slug': 'some-other-form', 'approval_config': {}}, 5,
        {'user_id': 3, 'explicit_approver_id': None})
    ctx = cap['context']
    assert ctx['approver_user_id'] == 55
