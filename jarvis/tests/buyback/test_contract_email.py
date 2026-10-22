"""P4 Task 2 — send_contract_email: best-effort delivery of the generated
contract PDF to the advisor. Pure (no DB); send_email + advisor lookup mocked."""
from unittest import mock

from buyback.services.email import send_contract_email


def test_sends_pdf_attachment_to_advisor():
    rec = {'id': 1, 'record_code': 'BB-1', 'brand': 'BMW', 'model': '320d'}
    with mock.patch('buyback.services.email.send_email', return_value=(True, None)) as se, \
         mock.patch('buyback.services.email._resolve_advisor_contact',
                    return_value={'name': 'A', 'phone': '', 'email': 'adv@x.ro'}):
        send_contract_email(rec, b'%PDF- data', 'Contract_BB-1.pdf')
    se.assert_called_once()
    kw = se.call_args.kwargs
    assert kw['to_email'] == 'adv@x.ro'
    assert kw['attachments'] == [('Contract_BB-1.pdf', b'%PDF- data')]


def test_swallows_raising_send_email():
    rec = {'id': 1}
    with mock.patch('buyback.services.email.send_email', side_effect=RuntimeError('smtp down')), \
         mock.patch('buyback.services.email._resolve_advisor_contact',
                    return_value={'name': 'A', 'phone': '', 'email': 'adv@x.ro'}):
        send_contract_email(rec, b'%PDF-', None)  # must not raise


def test_no_advisor_email_skips_send():
    rec = {'id': 1}
    with mock.patch('buyback.services.email.send_email') as se, \
         mock.patch('buyback.services.email._resolve_advisor_contact',
                    return_value={'name': '', 'phone': '', 'email': ''}):
        send_contract_email(rec, b'%PDF-', None)
    se.assert_not_called()


def test_default_filename_from_record_code():
    rec = {'id': 7, 'record_code': 'BB-XYZ'}
    with mock.patch('buyback.services.email.send_email', return_value=(True, None)) as se, \
         mock.patch('buyback.services.email._resolve_advisor_contact',
                    return_value={'name': 'A', 'phone': '', 'email': 'adv@x.ro'}):
        send_contract_email(rec, b'%PDF-')
    assert se.call_args.kwargs['attachments'][0][0] == 'Contract_BB-XYZ.pdf'
