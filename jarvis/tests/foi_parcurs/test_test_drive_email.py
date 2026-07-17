"""Tests for the Test Drive contract EMAIL endpoint:
POST /api/foi-parcurs/contracts/<id>/email.

Verifies the rendered subject + plain-text body (template, per company+brand
personalisation, graceful omission of missing placeholders), the QR + PDF
attachments, and UTF-8 diacritics. send_email is captured, not actually sent.
"""
import os
import tempfile

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.pdf as pdf_mod
import core.services.notification_service as notif_mod


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True  # login_required no-op; current_user is anonymous
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _sample_contract(**overrides):
    c = {
        'id': 1,
        'contract_id': 'TD-AWP-0001',
        'client_name': 'Horațiu Nicolae Ioan',
        'client_email': 'onfile@example.com',
        'vin': 'LSJWC4394TZ523412',
        'vehicle_mark': 'MG',
        'vehicle_model': 'MG3 1.5 GSL 5MT Excite',
        'vehicle_fuel_type': 'Benzina',
        'vehicle_brand': 'MG Motor',
        'company_name': 'Autoworld PLUS S.R.L.',
        'advisor_name': 'Ana Pop',
        'departure_datetime': '2026-07-26T10:00:00',
        'pdf_legal_path': None,
    }
    c.update(overrides)
    return c


@pytest.fixture
def captured(monkeypatch):
    """Wire the endpoint's collaborators and capture the send_email call."""
    box = {}

    monkeypatch.setattr(pdf_mod._fp_repo, 'get_contract_by_id', lambda _id: _sample_contract())

    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    tmp.write(b'%PDF-1.4 fake')
    tmp.close()
    monkeypatch.setattr(pdf_mod, '_ensure_pdf_path', lambda contract, cid, ptype: tmp.name)
    monkeypatch.setattr(pdf_mod, '_qr_png', lambda url: b'PNGDATA' if url else None)
    # Consilier resolved from the users table (by advisor_name) — stubbed here.
    monkeypatch.setattr(pdf_mod, '_consilier_contact',
                        lambda name: {'name': name or 'Ana Pop',
                                      'email': 'ana.pop@autoworld.ro', 'phone': '0740 111 222'})

    monkeypatch.setattr(notif_mod, 'is_smtp_configured', lambda: True)

    def fake_send(**kwargs):
        box.update(kwargs)
        return True, ''

    monkeypatch.setattr(notif_mod, 'send_email', fake_send)
    return box


def test_email_subject_and_body(client, captured):
    resp = client.post('/api/foi-parcurs/contracts/1/email', json={'to_email': 'client@example.com'})
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True

    subject = captured['subject']
    text = captured['text_body']
    html = captured['html_body']

    assert subject == 'Mulțumim pentru test drive!'

    # Greeting + details (plain text)
    assert 'Bună ziua Horațiu Nicolae Ioan,' in text
    assert 'Detalii test drive' in text
    assert 'Contract: TD-AWP-0001' in text
    assert 'MG3 1.5 GSL 5MT Excite' in text          # Vehicul (marca model motorizare)
    assert 'LSJWC4394TZ523412' in text                # VIN
    assert '26.07.2026' in text                       # Data (dd.mm.yyyy)

    # HTML: standard paragraphs (no <pre>/monospace, no icons) + a review link
    assert '<p>' in html and '<pre' not in html
    assert '🚗' not in subject and '⭐' not in text and '⭐' not in html
    assert '<a href="https://g.page/r/CQxsCUMofMlJEBM/review">' in html

    # Consilier: name + phone + email resolved from the users table
    assert 'Ana Pop' in text
    assert 'Telefon: 0740 111 222' in text
    assert 'ana.pop@autoworld.ro' in text

    # Per company+brand review link + dealer footer
    assert 'https://g.page/r/CQxsCUMofMlJEBM/review' in text
    assert 'Calea Clujului 4B-4C' in text
    assert 'www.autoworld.ro' in text

    # UTF-8 diacritics survive
    assert 'Vă mulțumim' in text


def test_email_attachments_pdf_and_qr(client, captured):
    client.post('/api/foi-parcurs/contracts/1/email', json={'to_email': 'client@example.com'})
    names = [fn for (fn, _bytes) in captured['attachments']]
    assert 'foaie-parcurs-TD-AWP-0001.pdf' in names
    assert 'recenzie-google-qr.png' in names
    # A plain-text alternative is sent (not just html)
    assert captured['text_body'] and isinstance(captured['text_body'], str)


def test_email_omits_consilier_contact_when_missing(client, monkeypatch, captured):
    # Consilier found by name but with no email/phone → those lines are omitted.
    monkeypatch.setattr(pdf_mod, '_consilier_contact',
                        lambda name: {'name': 'Ana Pop', 'email': '', 'phone': ''})
    client.post('/api/foi-parcurs/contracts/1/email', json={'to_email': 'client@example.com'})
    text = captured['text_body']
    assert 'Ana Pop' in text
    assert 'Telefon:' not in text
    assert 'Email:' not in text


def test_email_omits_review_when_unconfigured(client, monkeypatch, captured):
    # A company/brand with no config and no env vars → review section omitted
    monkeypatch.setattr(pdf_mod._fp_repo, 'get_contract_by_id',
                        lambda _id: _sample_contract(company_name='Autoworld ONE S.R.L.', vehicle_brand='Toyota'))
    monkeypatch.delenv('GOOGLE_REVIEW_URL', raising=False)
    client.post('/api/foi-parcurs/contracts/1/email', json={'to_email': 'client@example.com'})
    text = captured['text_body']
    assert 'Părerea dumneavoastră contează' not in text
    # QR not attached when there's no review URL
    names = [fn for (fn, _b) in captured['attachments']]
    assert 'recenzie-google-qr.png' not in names
