"""Tests for the Test Drive SUBMIT endpoint:
POST /api/foi-parcurs/test-drive.

Focus: the client is resolved from the CRM (crm_clients) — not the legacy
fp_clients table — and the resolved name/phone are stored directly on the
contract row so the contract can be read back without depending on a
fp_clients join.

Uses the Flask test client against a minimal app registering foi_parcurs_bp,
with FoiParcursRepository and the CRM ClientRepository mocked at the module
level where they are imported into foi_parcurs.routes.test_drive (mirrors
jarvis/tests/foi_parcurs/test_test_drive_return.py).
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.test_drive as test_drive_mod


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    # login_required is a no-op under LOGIN_DISABLED — no LoginManager needed.
    app.config['LOGIN_DISABLED'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def _valid_payload(**overrides):
    payload = {
        'company_id': 1,
        'vin': 'WVWZZZ1JZXW000001',
        'client_id': 42,
        'odometer_start': 1000,
        'estimated_km': 20,
        'fuel_gauge_start_level': 'full',
        'departure_datetime': '2026-07-15T10:00:00Z',
        'itinerary': 'Cluj - Turda',
        'advisor_name': 'Ana Pop',
        'client_signature': 'data:image/png;base64,client-sig',
        'gdpr_consent': True,
    }
    payload.update(overrides)
    return payload


def _crm_client(id=42, display_name='Ion Popescu', phone='0722123456'):
    return {'id': id, 'display_name': display_name, 'phone': phone}


def test_submit_resolves_and_stores_crm_client_name_and_phone(client, monkeypatch):
    monkeypatch.setattr(test_drive_mod, '_crm_client_repo', _FakeCrmRepo(_crm_client()))

    calls = []

    def fake_create_from_td_form(data):
        calls.append(data)
        return {**data, 'id': 1}

    monkeypatch.setattr(test_drive_mod._fp_repo, 'create_from_td_form', fake_create_from_td_form)

    resp = client.post('/api/foi-parcurs/test-drive', json=_valid_payload())

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert body['contract']['client_name'] == 'Ion Popescu'
    assert body['contract']['client_phone'] == '0722123456'

    assert len(calls) == 1
    assert calls[0]['client_id'] == 42
    assert calls[0]['client_name'] == 'Ion Popescu'
    assert calls[0]['client_phone'] == '0722123456'


def test_submit_with_unknown_crm_client_still_succeeds(client, monkeypatch):
    monkeypatch.setattr(test_drive_mod, '_crm_client_repo', _FakeCrmRepo(None))

    calls = []

    def fake_create_from_td_form(data):
        calls.append(data)
        return {**data, 'id': 2}

    monkeypatch.setattr(test_drive_mod._fp_repo, 'create_from_td_form', fake_create_from_td_form)

    resp = client.post('/api/foi-parcurs/test-drive', json=_valid_payload(client_id=999))

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert body['contract']['client_name'] is None
    assert body['contract']['client_phone'] is None

    assert len(calls) == 1
    assert calls[0]['client_id'] == 999
    assert calls[0]['client_name'] is None
    assert calls[0]['client_phone'] is None


class _FakeCrmRepo:
    """Minimal stand-in for crm.repositories.ClientRepository.get_by_id."""

    def __init__(self, client_row):
        self._client_row = client_row

    def get_by_id(self, client_id):
        return self._client_row


import foi_parcurs.routes.test_drive as td


def test_submit_requires_conditions_when_text_exists(client, monkeypatch):
    monkeypatch.setattr(td._vehicle_repo, 'get_by_vin', lambda vin: {'brand': 'MG Motor'})
    monkeypatch.setattr(td._dealer_repo, 'get_general_conditions', lambda cid, b: 'Termeni...')
    resp = client.post('/api/foi-parcurs/test-drive', json=_valid_payload())  # no accept flag
    assert resp.status_code == 400
    assert 'general' in resp.get_json()['error'].lower()


def test_submit_snapshots_conditions_when_accepted(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(td._vehicle_repo, 'get_by_vin', lambda vin: {'brand': 'MG Motor'})
    monkeypatch.setattr(td._dealer_repo, 'get_general_conditions', lambda cid, b: 'Termeni generali...')
    monkeypatch.setattr(td._crm_client_repo, 'get_by_id', lambda cid: {'display_name': 'X', 'phone': '0700000000'})

    def fake_create(data):
        captured.update(data)
        return {'id': 1, 'contract_id': data['contract_id']}
    monkeypatch.setattr(td._fp_repo, 'create_from_td_form', fake_create)
    monkeypatch.setattr(td._fp_repo, 'execute', lambda *a, **k: None)

    resp = client.post('/api/foi-parcurs/test-drive',
                       json=_valid_payload(general_conditions_accepted=True))
    assert resp.status_code == 200
    assert captured['general_conditions_accepted'] is True
    assert captured['general_conditions_text'] == 'Termeni generali...'
    assert captured['general_conditions_accepted_at'] is not None


def test_submit_ok_without_conditions_when_none_configured(client, monkeypatch):
    monkeypatch.setattr(td._vehicle_repo, 'get_by_vin', lambda vin: {'brand': 'MG Motor'})
    monkeypatch.setattr(td._dealer_repo, 'get_general_conditions', lambda cid, b: '')
    monkeypatch.setattr(td._crm_client_repo, 'get_by_id', lambda cid: {'display_name': 'X', 'phone': '0700000000'})
    seen = {}
    monkeypatch.setattr(td._fp_repo, 'create_from_td_form', lambda d: (seen.update(d) or {'id': 2, 'contract_id': d['contract_id']}))
    monkeypatch.setattr(td._fp_repo, 'execute', lambda *a, **k: None)
    resp = client.post('/api/foi-parcurs/test-drive', json=_valid_payload())
    assert resp.status_code == 200
    assert 'general_conditions_text' not in seen


def test_submit_ok_without_gdpr_when_company_has_no_text(client, monkeypatch):
    monkeypatch.setattr(td, '_company_gdpr_text', lambda cid: '')
    monkeypatch.setattr(td._vehicle_repo, 'get_by_vin', lambda vin: {'brand': 'MG Motor'})
    monkeypatch.setattr(td._dealer_repo, 'get_general_conditions', lambda cid, b: '')
    monkeypatch.setattr(td._crm_client_repo, 'get_by_id', lambda cid: {'display_name': 'X', 'phone': '0700000000'})
    monkeypatch.setattr(td._fp_repo, 'create_from_td_form', lambda d: {'id': 1, 'contract_id': d['contract_id']})
    monkeypatch.setattr(td._fp_repo, 'execute', lambda *a, **k: None)
    payload = _valid_payload(); payload.pop('gdpr_consent', None)  # no consent sent
    r = client.post('/api/foi-parcurs/test-drive', json=payload)
    assert r.status_code == 200


def test_submit_requires_gdpr_when_company_has_text(client, monkeypatch):
    monkeypatch.setattr(td, '_company_gdpr_text', lambda cid: '## GDPR\n\ntext')
    monkeypatch.setattr(td._vehicle_repo, 'get_by_vin', lambda vin: {'brand': 'MG Motor'})
    monkeypatch.setattr(td._dealer_repo, 'get_general_conditions', lambda cid, b: '')
    payload = _valid_payload(); payload.pop('gdpr_consent', None)
    r = client.post('/api/foi-parcurs/test-drive', json=payload)
    assert r.status_code == 400
    assert 'gdpr' in r.get_json()['error'].lower()


def test_submit_gdpr_enforced_through_real_company_repository(client, monkeypatch):
    """Exercises the REAL _company_gdpr_text helper (not monkeypatched), mocking
    only at the CompanyRepository boundary it calls internally, to prove the
    actual wiring _company_gdpr_text -> CompanyRepository().get()['gdpr_text']
    enforces the GDPR consent gate.
    """
    monkeypatch.setattr(
        'core.organization.repositories.company_repository.CompanyRepository.get',
        lambda self, cid: {'gdpr_text': '## GDPR\n\ntext'},
    )
    monkeypatch.setattr(td._vehicle_repo, 'get_by_vin', lambda vin: {'brand': 'MG Motor'})
    monkeypatch.setattr(td._dealer_repo, 'get_general_conditions', lambda cid, b: '')
    payload = _valid_payload(); payload.pop('gdpr_consent', None)
    r = client.post('/api/foi-parcurs/test-drive', json=payload)
    assert r.status_code == 400
    assert 'gdpr' in r.get_json()['error'].lower()
