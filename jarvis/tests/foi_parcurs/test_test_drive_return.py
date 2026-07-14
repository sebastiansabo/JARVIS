"""Tests for the Test Drive RETURN endpoint:
PUT /api/foi-parcurs/test-drive/<id>/return.

Uses the Flask test client against a minimal app registering foi_parcurs_bp,
with FoiParcursRepository mocked at the module level where it is imported
into foi_parcurs.routes.test_drive (mirrors jarvis/tests/auth/test_mobile_login_otp.py).
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


def _td_contract(id=1, km_start=1000, route_type='TD'):
    return {
        'id': id,
        'contract_id': f'TD-{id}',
        'route_type': route_type,
        'km_start': km_start,
        'km_end': km_start,
        'status': 'FILLED',
    }


def test_missing_advisor_signature_returns_400(client, monkeypatch):
    monkeypatch.setattr(test_drive_mod._fp_repo, 'get_contract_by_id', lambda id: _td_contract())

    resp = client.put('/api/foi-parcurs/test-drive/1/return', json={
        'km_end': 1200,
        'client_signature': 'data:image/png;base64,client-only',
    })
    assert resp.status_code == 400
    assert 'signature' in resp.get_json()['error'].lower()


def test_missing_client_signature_returns_400(client, monkeypatch):
    monkeypatch.setattr(test_drive_mod._fp_repo, 'get_contract_by_id', lambda id: _td_contract())

    resp = client.put('/api/foi-parcurs/test-drive/1/return', json={
        'km_end': 1200,
        'advisor_signature': 'data:image/png;base64,advisor-only',
    })
    assert resp.status_code == 400
    assert 'signature' in resp.get_json()['error'].lower()


def test_km_end_less_than_km_start_returns_400(client, monkeypatch):
    monkeypatch.setattr(test_drive_mod._fp_repo, 'get_contract_by_id', lambda id: _td_contract(km_start=1000))

    resp = client.put('/api/foi-parcurs/test-drive/1/return', json={
        'km_end': 900,
        'advisor_signature': 'sig-advisor',
        'client_signature': 'sig-client',
    })
    assert resp.status_code == 400
    body = resp.get_json()
    assert body['success'] is False
    assert 'km_end' in body['error']


def test_missing_km_end_returns_400(client, monkeypatch):
    monkeypatch.setattr(test_drive_mod._fp_repo, 'get_contract_by_id', lambda id: _td_contract())

    resp = client.put('/api/foi-parcurs/test-drive/1/return', json={
        'advisor_signature': 'sig-advisor',
        'client_signature': 'sig-client',
    })
    assert resp.status_code == 400


def test_contract_not_found_returns_404(client, monkeypatch):
    monkeypatch.setattr(test_drive_mod._fp_repo, 'get_contract_by_id', lambda id: None)

    resp = client.put('/api/foi-parcurs/test-drive/99/return', json={
        'km_end': 100,
        'advisor_signature': 'sig-advisor',
        'client_signature': 'sig-client',
    })
    assert resp.status_code == 404


def test_non_td_contract_returns_400(client, monkeypatch):
    monkeypatch.setattr(
        test_drive_mod._fp_repo, 'get_contract_by_id',
        lambda id: _td_contract(route_type='COMODAT'),
    )

    resp = client.put('/api/foi-parcurs/test-drive/1/return', json={
        'km_end': 1200,
        'advisor_signature': 'sig-advisor',
        'client_signature': 'sig-client',
    })
    assert resp.status_code == 400


def test_valid_return_calls_record_return_and_returns_completed_contract(client, monkeypatch):
    monkeypatch.setattr(
        test_drive_mod._fp_repo, 'get_contract_by_id',
        lambda id: _td_contract(km_start=1000),
    )

    calls = []

    def fake_record_return(contract_id, data):
        calls.append((contract_id, data))
        return {**_td_contract(km_start=1000), 'km_end': data['km_end'], 'status': 'COMPLETED'}

    monkeypatch.setattr(test_drive_mod._fp_repo, 'record_return', fake_record_return)

    resp = client.put('/api/foi-parcurs/test-drive/1/return', json={
        'km_end': 1250,
        'fuel_gauge_end_level': '3/4',
        'return_damage': [{'zone': 'front-bumper', 'severity': 'minor', 'note': 'scratch'}],
        'return_notes': 'All good',
        'advisor_signature': 'data:image/png;base64,advisor',
        'client_signature': 'data:image/png;base64,client',
    })

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert body['contract']['status'] == 'COMPLETED'
    assert body['contract']['km_end'] == 1250

    assert len(calls) == 1
    contract_id, data = calls[0]
    assert contract_id == 1
    assert data == {
        'km_end': 1250,
        'fuel_gauge_end_level': '3/4',
        'return_datetime': None,
        'return_damage': [{'zone': 'front-bumper', 'severity': 'minor', 'note': 'scratch'}],
        'return_notes': 'All good',
        'return_advisor_signature': 'data:image/png;base64,advisor',
        'return_client_signature': 'data:image/png;base64,client',
    }
