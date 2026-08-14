"""Tests for INTERNAL (QuickSession) creation via POST /api/foi-parcurs/test-drive.

An internal session (`is_internal: true`) is a slim FILLED TD with no customer
and no signature: the create endpoint skips client_id/signature/GDPR/general-
conditions and skips PDF generation. Fixtures mirror test_test_drive_submit.py.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.test_drive as td


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _hermetic_conditions(monkeypatch):
    # The general-conditions lookup runs unconditionally at submit — keep it
    # off the DB so these tests are hermetic. The lock check + single-open-session
    # guard also run for internal sessions (this branch has them); stub them out.
    monkeypatch.setattr(td._vehicle_repo, 'get_by_vin', lambda vin: {'brand': ''})
    monkeypatch.setattr(td._dealer_repo, 'get_general_conditions', lambda cid, b: '')
    monkeypatch.setattr(td._vehicle_repo, 'get_lock_by_vin', lambda vin: None, raising=False)
    monkeypatch.setattr(td, 'open_session_block', lambda *a, **k: None, raising=False)
    monkeypatch.setattr(td, 'is_privileged', lambda: False, raising=False)


def _internal_payload(**overrides):
    payload = {
        'is_internal': True,
        'company_id': 1,
        'vin': 'WVWZZZ1JZXW000001',
        'departure_datetime': '2026-08-14T10:00:00Z',
        'return_datetime': '2026-08-14T14:00:00Z',
        'odometer_start': 1000,
        'advisor_name': 'Ana Pop',
        'itinerary': 'Livrare piese',
    }
    payload.update(overrides)
    return payload


def test_internal_create_succeeds_without_client_or_signature(client, monkeypatch):
    calls = []

    def fake_create(data):
        calls.append(data)
        return {**data, 'id': 7}

    monkeypatch.setattr(td._fp_repo, 'create_from_td_form', fake_create)

    resp = client.post('/api/foi-parcurs/test-drive', json=_internal_payload())

    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()['success'] is True
    assert len(calls) == 1
    row = calls[0]
    assert row['is_internal'] is True
    assert row['client_id'] is None
    assert row['client_name'] is None
    assert row['status'] == 'FILLED'
    assert row['route_type'] == 'TD'
    assert row['advisor_name'] == 'Ana Pop'
    assert row['km_start'] == 1000


def test_internal_create_requires_vehicle_and_km(client):
    resp = client.post(
        '/api/foi-parcurs/test-drive',
        json=_internal_payload(vin='', odometer_start=None),
    )
    assert resp.status_code == 400
    err = resp.get_json()['error'].lower()
    assert 'vin' in err
    assert 'odometer_start' in err


def test_non_internal_still_requires_client_signature(client):
    resp = client.post('/api/foi-parcurs/test-drive', json={
        'company_id': 1, 'vin': 'WVWZZZ1JZXW000001', 'client_id': 42,
        'odometer_start': 1000, 'estimated_km': 10,
        'fuel_gauge_start_level': 'full', 'departure_datetime': '2026-08-14T10:00:00Z',
        'advisor_name': 'Ana',
    })
    assert resp.status_code == 400
    assert 'client_signature' in resp.get_json()['error']
