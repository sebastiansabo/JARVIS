from core.approvals.handlers._shared import _approval_deeplink


def test_form_submission_uses_landing():
    assert _approval_deeplink('form_submission', 12, 99) == '/go/approval/99'


def test_other_entities_use_entity_link():
    # invoice keeps its existing deep link, not the approval landing
    assert _approval_deeplink('invoice', 7, 99) == '/app/accounting/invoices/7'
