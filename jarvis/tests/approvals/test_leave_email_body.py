"""The approver email for a Bilet de Învoire shows the full leave summary and two
one-tap action buttons (Aprobă / Respinge) that point at the signed decide links."""
from core.approvals.handlers.leave_email import leave_approval_email_body

SUMMARY = {'requester_name': 'Seba', 'leave_date': '2026-08-20', 'start': '07:00',
           'end': '10:00', 'hours': 3, 'reason': 'Personal', 'notes': 'la medic'}


def test_body_has_interval_reason_and_both_signed_action_links():
    html = leave_approval_email_body(
        'Manager X', SUMMARY,
        'https://j.ro/go/approval/act?token=APPROVE_TOK',
        'https://j.ro/go/approval/act?token=REJECT_TOK')
    assert 'Manager X' in html                       # greeting to the approver
    assert 'Seba' in html                            # who is asking
    assert '07:00' in html and '10:00' in html       # the interval that was "off"
    assert 'Personal' in html and 'la medic' in html
    assert 'token=APPROVE_TOK' in html and 'token=REJECT_TOK' in html
    assert 'Aprob' in html and 'Respinge' in html    # both buttons labelled


def test_body_without_urls_keeps_summary_but_omits_buttons():
    # No app context to sign tokens → still send the details, just no action buttons.
    html = leave_approval_email_body('Manager X', SUMMARY, '', '')
    assert '07:00' in html and 'Personal' in html
    assert 'href' not in html                         # no action links rendered
