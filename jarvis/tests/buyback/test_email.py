"""Tests for Task 13's buyback email builders + Notifier.

(a) test_offer_email_contains_amount_and_vehicle / test_offer_email_escapes_values:
    pure unit tests of build_offer_email() — no DB, no monkeypatching. Exact
    Step-1 test from the task brief, plus an escaping regression test.

(b) test_send_offer_email_swallows_raising_send_email /
    test_notify_sales_and_notify_acquisition_swallow_raising_send_email:
    prove Notifier's methods never propagate an exception raised by
    send_email — the CRITICAL non-fatal-to-post_offer requirement from the
    Task 8 review. No DB: the fake records below carry no company_id, so
    _company_name() (buyback/services/email.py) short-circuits before ever
    touching the DB, and _resolve_internal_recipient() is driven purely by
    the BUYBACK_*_EMAIL env vars via monkeypatch.

(c) test_post_offer_survives_raising_notifier_email (require_real_db):
    service-level regression — BuyBackService.post_offer() wired with the
    REAL Notifier (send_email monkeypatched to raise) still returns the
    posted offer, proving the guard holds at the actual call site the
    Task 13 brief cares about, not just against a hand-rolled FakeNotifier
    (which is what test_buyback_service.py's existing notifier tests use).
"""
import os

import pytest

from buyback.services import email as email_module
from buyback.services.email import Notifier, build_offer_email


def test_offer_email_contains_amount_and_vehicle():
    rec = {'brand': 'BMW', 'model': '320d', 'vin': 'WBA00000000000001', 'seller_name': 'Ion'}
    off = {'amount_eur': 9500, 'valid_until': '2026-10-01', 'offer_type': 'initial'}
    dealer = {'name': 'AUTOWORLD', 'phone': '+40...', 'address': '...'}
    subject, text, html = build_offer_email(rec, off, dealer)
    assert '9500' in html and 'BMW' in html and '320d' in html
    assert 'Ion' in html  # personalized
    assert subject
    assert 'inițială' in subject
    # text body carries the same info as the HTML body
    assert '9500' in text and 'BMW' in text and 'Ion' in text


def test_offer_email_final_round_subject():
    rec = {'brand': 'Audi', 'model': 'A4'}
    off = {'amount_eur': 8000, 'offer_type': 'final'}
    subject, _, _ = build_offer_email(rec, off, {})
    assert 'finală' in subject
    assert 'Audi' in subject and 'A4' in subject


def test_offer_email_escapes_values():
    rec = {
        'brand': '<b>BMW</b>',
        'model': '320d',
        'seller_name': '<script>alert(1)</script>',
    }
    off = {'amount_eur': 1000, 'offer_type': 'initial'}
    subject, text, html = build_offer_email(rec, off, {})
    assert '<script>' not in html
    assert '&lt;script&gt;' in html
    assert '<b>BMW</b>' not in html
    assert '&lt;b&gt;BMW&lt;/b&gt;' in html
    # subject itself is plain text (not HTML-rendered), but the HTML body's
    # rendering of it must still be escaped
    assert '&lt;b&gt;BMW&lt;/b&gt;' in html


def test_offer_email_omits_missing_lines():
    rec = {'brand': 'BMW', 'model': '320d'}  # no vin, no seller_name
    off = {'amount_eur': 1000, 'offer_type': 'initial'}  # no valid_until
    subject, text, html = build_offer_email(rec, off, {})  # no dealer contact
    assert 'VIN' not in html
    assert 'Valabilă' not in html
    assert 'Telefon dealer' not in html
    assert 'Bună ziua,' in html  # generic greeting, no name interpolated


def test_send_offer_email_swallows_raising_send_email(monkeypatch):
    def _raise(**kwargs):
        raise RuntimeError('SMTP is on fire')

    monkeypatch.setattr(email_module, 'send_email', _raise)

    # No company_id -> _company_name() short-circuits before any DB access.
    rec = {'id': 1, 'brand': 'BMW', 'model': '320d', 'seller_email': 'seller@example.com'}
    off = {'amount_eur': 1000, 'offer_type': 'initial'}

    # Must not raise despite send_email raising internally.
    Notifier().send_offer_email(rec, off)


def test_send_offer_email_noop_without_seller_email(monkeypatch):
    calls = []
    monkeypatch.setattr(email_module, 'send_email', lambda **kw: calls.append(kw) or (True, ''))

    rec = {'id': 1, 'brand': 'BMW', 'model': '320d', 'seller_email': ''}
    off = {'amount_eur': 1000, 'offer_type': 'initial'}
    Notifier().send_offer_email(rec, off)

    assert calls == []  # send_email never called — no-op, no crash


def test_notify_sales_and_notify_acquisition_swallow_raising_send_email(monkeypatch):
    def _raise(**kwargs):
        raise RuntimeError('SMTP is on fire')

    monkeypatch.setattr(email_module, 'send_email', _raise)
    monkeypatch.setenv('BUYBACK_SALES_EMAIL', 'sales@example.com')
    monkeypatch.setenv('BUYBACK_ACQUISITION_EMAIL', 'acquisition@example.com')

    rec = {'id': 1, 'brand': 'BMW', 'model': '320d', 'status': 'initial_offer', 'record_code': 'BB-1'}

    # Neither call may raise, despite send_email raising internally.
    Notifier().notify_sales(rec)
    Notifier().notify_acquisition(rec)


def test_notify_sales_noop_without_configured_recipient(monkeypatch):
    calls = []
    monkeypatch.setattr(email_module, 'send_email', lambda **kw: calls.append(kw) or (True, ''))
    monkeypatch.delenv('BUYBACK_SALES_EMAIL', raising=False)

    # No advisor_id/created_by either -> nothing resolvable -> no-op.
    rec = {'id': 1, 'brand': 'BMW', 'model': '320d', 'status': 'initial_offer'}
    Notifier().notify_sales(rec)

    assert calls == []


def test_notify_sales_sends_to_configured_address(monkeypatch):
    calls = []
    monkeypatch.setattr(email_module, 'send_email', lambda **kw: calls.append(kw) or (True, ''))
    monkeypatch.setenv('BUYBACK_SALES_EMAIL', 'sales@example.com')

    rec = {'id': 1, 'brand': 'BMW', 'model': '320d', 'status': 'initial_offer', 'record_code': 'BB-1'}
    Notifier().notify_sales(rec)

    assert len(calls) == 1
    assert calls[0]['to_email'] == 'sales@example.com'
    assert 'BMW' in calls[0]['subject']


# ---------------------------------------------------------------------------
# Service-level regression (real DB + real Notifier, send_email monkeypatched)
# ---------------------------------------------------------------------------

def _code(prefix='BB-EMAIL'):
    return f'{prefix}-{os.urandom(4).hex()}'


def _vin():
    return ('WBA' + os.urandom(7).hex().upper())[:17]


def test_post_offer_survives_raising_notifier_email(require_real_db, monkeypatch):
    from buyback import lifecycle
    from buyback.repositories.record_repository import RecordRepository
    from buyback.services.buyback_service import BuyBackService

    def _raise(**kwargs):
        raise RuntimeError('SMTP is on fire')

    monkeypatch.setattr(email_module, 'send_email', _raise)

    rec = RecordRepository().create({
        'record_code': _code(),
        'company_id': 1,
        'vin': _vin(),
        'brand': 'BMW',
        'model': '320d',
        'created_by': 1,
        'seller_email': 'seller@example.com',
    })

    svc = BuyBackService(notifier=Notifier())
    offer = svc.post_offer(rec, 'initial', {'amount_eur': 1000, 'vat_status': 'no_vat'}, actor=1)

    assert offer['id']
    assert offer['offer_type'] == 'initial'
    fresh = RecordRepository().get_by_id(rec['id'])
    assert fresh['status'] == lifecycle.INITIAL_OFFER
