"""Vehicle lockout (block a locked car from new sessions) + general_observation persistence.

Mirrors the fixtures/monkeypatching pattern in test_plan_session.py.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.test_drive as td_routes


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


def _body(**over):
    b = {
        'company_id': 11, 'vin': 'WAUZZZF4T1021365', 'client_id': 5,
        'odometer_start': 1000, 'estimated_km': 30,
        'fuel_gauge_start_level': '1', 'departure_datetime': '2026-08-01T10:00:00',
        'advisor_name': 'Consilier X', 'status': 'PLANNED',
    }
    b.update(over)
    return b


def _stub_create(monkeypatch, captured):
    def fake_create(data):
        captured.update(data)
        return {'id': 101, **data}
    monkeypatch.setattr(td_routes._fp_repo, 'create_from_td_form', fake_create)
    monkeypatch.setattr(td_routes._crm_client_repo, 'get_by_id', lambda i: {'display_name': 'Ion', 'phone': '07'})


def test_submit_rejected_when_vehicle_locked(client, monkeypatch):
    monkeypatch.setattr(td_routes._vehicle_repo, 'get_lock_by_vin',
                        lambda vin: {'locked_out': True, 'lockout_category': 'service', 'lockout_note': 'în service'})
    resp = client.post('/api/foi-parcurs/test-drive', json=_body())
    assert resp.status_code == 409, resp.get_json()
    j = resp.get_json()
    assert j['locked_out'] is True
    assert 'service' in j['error'] and 'în service' in j['error']


def test_submit_ok_when_not_locked(client, monkeypatch):
    captured = {}
    _stub_create(monkeypatch, captured)
    monkeypatch.setattr(td_routes._vehicle_repo, 'get_lock_by_vin', lambda vin: None)
    resp = client.post('/api/foi-parcurs/test-drive', json=_body())
    assert resp.status_code == 200, resp.get_json()


def test_general_observation_persisted_and_trimmed(client, monkeypatch):
    captured = {}
    _stub_create(monkeypatch, captured)
    monkeypatch.setattr(td_routes._vehicle_repo, 'get_lock_by_vin', lambda vin: None)
    resp = client.post('/api/foi-parcurs/test-drive', json=_body(general_observation='  zgârietură portieră  '))
    assert resp.status_code == 200, resp.get_json()
    assert captured['general_observation'] == 'zgârietură portieră'
