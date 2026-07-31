"""The start-of-session test-drive email is a simplified mail: client greeting +
consilier contact + the contract PDF only — no review request/QR, offer doc, or
thank-you-for-today framing. The full mail (completion / manual send) is unchanged.
"""
from foi_parcurs.routes.pdf import _render_td_email

_CONTRACT = {
    'contract_id': 'TD-1', 'client_name': 'Ion Pop', 'vin': 'WVWX', 'id': 1,
    'vehicle_mark': 'Volvo', 'vehicle_model': 'XC60', 'departure_datetime': '2026-07-01T10:00:00',
}
_DEALER = {'review_url': 'https://g.page/r/review', 'address': 'Str X', 'phone': '0700'}
_CONSILIER = {'name': 'Ana Consultant', 'phone': '0711222333', 'email': 'ana@autoworld.ro'}


def test_simple_email_has_client_and_consultant_no_review():
    subject, text, html = _render_td_email(_CONTRACT, _DEALER, _CONSILIER, simple=True)
    assert 'test drive' in subject.lower()
    # client greeting + consultant data present
    assert 'Ion Pop' in text and 'Ion Pop' in html
    assert 'Ana Consultant' in text and 'ana@autoworld.ro' in text
    assert 'contract' in text.lower()
    # no review request / QR / marketing
    for body in (text, html):
        assert 'g.page' not in body
        assert 'recenzie' not in body.lower()
        assert 'astăzi' not in body.lower()  # dropped the "today's drive" framing


def test_full_email_keeps_review_request():
    subject, text, html = _render_td_email(_CONTRACT, _DEALER, _CONSILIER)  # simple=False default
    assert 'g.page' in html and 'recenzie' in text.lower()
    assert 'Ana Consultant' in text
