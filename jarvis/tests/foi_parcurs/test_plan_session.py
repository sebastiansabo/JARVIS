"""Tests for Task 1 of "Plan a Driving Session": POST /api/foi-parcurs/test-drive
accepts status='PLANNED' to create a draft contract without signature/GDPR/PDF.

Mirrors the fixtures/monkeypatching pattern in test_test_drive_submit.py.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.test_drive as td_routes
import foi_parcurs.routes.vehicles as veh_routes


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


def test_draft_create_omits_signature_and_pdf(client, monkeypatch):
    # Arrange: capture what create_from_td_form receives, stub CRM client lookup.
    captured = {}

    def fake_create(data):
        captured.update(data)
        return {'id': 101, **data}
    monkeypatch.setattr(td_routes._fp_repo, 'create_from_td_form', fake_create)
    monkeypatch.setattr(td_routes._crm_client_repo, 'get_by_id', lambda i: {'display_name': 'Ion Pop', 'phone': '0700000000'})
    called = {'pdf': False}
    # If PDF generation is imported inside the handler, patch it to flip the flag.
    import foi_parcurs.services.pdf_service as pdf
    monkeypatch.setattr(pdf, 'generate_legal_pdf', lambda c: called.__setitem__('pdf', True) or '/tmp/x.pdf')
    monkeypatch.setattr(pdf, 'generate_custom_pdf', lambda c: '/tmp/y.pdf')

    body = {
        'company_id': 11, 'vin': 'WAUZZZF4T1021365', 'client_id': 5,
        'odometer_start': 1000, 'estimated_km': 30,
        'fuel_gauge_start_level': '1', 'departure_datetime': '2026-08-01T10:00:00',
        'advisor_name': 'Consilier X', 'status': 'PLANNED',
        # NOTE: no client_signature, no gdpr_consent
    }
    resp = client.post('/api/foi-parcurs/test-drive', json=body)
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()['success'] is True
    assert captured['status'] == 'PLANNED'
    assert called['pdf'] is False   # no PDF for a draft


def test_draft_create_skips_general_conditions(client, monkeypatch):
    # Company has general conditions configured, but a PLANNED draft must not
    # require or record acceptance — that's deferred to activation.
    captured = {}

    def fake_create(data):
        captured.update(data)
        return {'id': 102, **data}
    monkeypatch.setattr(td_routes._fp_repo, 'create_from_td_form', fake_create)
    monkeypatch.setattr(td_routes._crm_client_repo, 'get_by_id', lambda i: {'display_name': 'Ion Pop', 'phone': '0700000000'})
    monkeypatch.setattr(td_routes._vehicle_repo, 'get_by_vin', lambda vin: {'brand': 'VW'})
    monkeypatch.setattr(td_routes._dealer_repo, 'get_general_conditions', lambda company_id, brand: 'Some GC text')

    body = {
        'company_id': 11, 'vin': 'WAUZZZF4T1021365', 'client_id': 5,
        'odometer_start': 1000, 'estimated_km': 30,
        'fuel_gauge_start_level': '1', 'departure_datetime': '2026-08-01T10:00:00',
        'advisor_name': 'Consilier X', 'status': 'PLANNED',
        # NOTE: no general_conditions_accepted
    }
    resp = client.post('/api/foi-parcurs/test-drive', json=body)
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()['success'] is True
    assert 'general_conditions_accepted' not in captured
    assert 'general_conditions_accepted_at' not in captured
    assert 'general_conditions_text' not in captured


def test_activate_requires_signature(client, monkeypatch):
    monkeypatch.setattr(td_routes._fp_repo, 'get_contract_by_id',
                        lambda i: {'id': i, 'route_type': 'TD', 'status': 'PLANNED', 'vin': 'V1', 'km_start': 1000})
    resp = client.put('/api/foi-parcurs/test-drive/101/activate', json={'km_start': 1000})
    assert resp.status_code == 400
    assert 'signature' in resp.get_json()['error'].lower()


def test_activate_fills_and_generates_pdf(client, monkeypatch):
    row = {'id': 101, 'route_type': 'TD', 'status': 'PLANNED', 'vin': 'V1',
           'km_start': 1000, 'fuel_tank_capacity_liters': 50}
    monkeypatch.setattr(td_routes._fp_repo, 'get_contract_by_id', lambda i: dict(row))
    seen = {}
    monkeypatch.setattr(td_routes._fp_repo, 'record_activation',
                        lambda i, d: seen.update(d) or {**row, 'id': i, 'status': 'FILLED'})
    monkeypatch.setattr(td_routes._fp_repo, 'execute', lambda *a, **k: None)
    import foi_parcurs.services.pdf_service as pdf
    made = {'pdf': False}
    monkeypatch.setattr(pdf, 'generate_legal_pdf', lambda c: made.__setitem__('pdf', True) or '/tmp/l.pdf')
    monkeypatch.setattr(pdf, 'generate_custom_pdf', lambda c: '/tmp/c.pdf')
    body = {'client_signature': 'data:sig', 'advisor_signature': 'data:adv',
            'gdpr_consent': True, 'odometer_start': 1005, 'fuel_gauge_start_level': '1/2',
            'departure_datetime': '2026-08-01T10:00:00'}
    resp = client.put('/api/foi-parcurs/test-drive/101/activate', json=body)
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()['contract']['status'] == 'FILLED'
    assert made['pdf'] is True


def test_activate_requires_general_conditions(client, monkeypatch):
    row = {'id': 101, 'route_type': 'TD', 'status': 'PLANNED', 'vin': 'V1',
           'company_id': 11, 'km_start': 1000, 'fuel_tank_capacity_liters': 50}
    monkeypatch.setattr(td_routes._fp_repo, 'get_contract_by_id', lambda i: dict(row))
    monkeypatch.setattr(td_routes._vehicle_repo, 'get_by_vin', lambda vin: {'brand': 'VW'})
    monkeypatch.setattr(td_routes._dealer_repo, 'get_general_conditions', lambda company_id, brand: 'Some GC text')
    body = {'client_signature': 'data:sig', 'advisor_signature': 'data:adv',
            'gdpr_consent': True, 'odometer_start': 1005, 'fuel_gauge_start_level': '1/2',
            'departure_datetime': '2026-08-01T10:00:00'}
    resp = client.put('/api/foi-parcurs/test-drive/101/activate', json=body)
    assert resp.status_code == 400
    assert 'general conditions' in resp.get_json()['error'].lower()


def test_activate_captures_general_conditions(client, monkeypatch):
    row = {'id': 101, 'route_type': 'TD', 'status': 'PLANNED', 'vin': 'V1',
           'company_id': 11, 'km_start': 1000, 'fuel_tank_capacity_liters': 50}
    monkeypatch.setattr(td_routes._fp_repo, 'get_contract_by_id', lambda i: dict(row))
    monkeypatch.setattr(td_routes._vehicle_repo, 'get_by_vin', lambda vin: {'brand': 'VW'})
    monkeypatch.setattr(td_routes._dealer_repo, 'get_general_conditions', lambda company_id, brand: 'Some GC text')
    seen = {}
    monkeypatch.setattr(td_routes._fp_repo, 'record_activation',
                        lambda i, d: seen.update(d) or {**row, 'id': i, 'status': 'FILLED'})
    monkeypatch.setattr(td_routes._fp_repo, 'execute', lambda *a, **k: None)
    import foi_parcurs.services.pdf_service as pdf
    monkeypatch.setattr(pdf, 'generate_legal_pdf', lambda c: '/tmp/l.pdf')
    monkeypatch.setattr(pdf, 'generate_custom_pdf', lambda c: '/tmp/c.pdf')
    body = {'client_signature': 'data:sig', 'advisor_signature': 'data:adv',
            'gdpr_consent': True, 'odometer_start': 1005, 'fuel_gauge_start_level': '1/2',
            'departure_datetime': '2026-08-01T10:00:00', 'general_conditions_accepted': True}
    resp = client.put('/api/foi-parcurs/test-drive/101/activate', json=body)
    assert resp.status_code == 200, resp.get_json()
    assert seen.get('general_conditions_accepted') is True
    assert seen.get('general_conditions_text') == 'Some GC text'


def test_activate_race_returns_409_no_pdf(client, monkeypatch):
    # Row reads as PLANNED, but a concurrent activation flipped it first, so the
    # guarded UPDATE matches zero rows and record_activation returns falsy.
    monkeypatch.setattr(td_routes._fp_repo, 'get_contract_by_id',
                        lambda i: {'id': i, 'route_type': 'TD', 'status': 'PLANNED', 'vin': 'V1',
                                   'km_start': 1000, 'fuel_tank_capacity_liters': 50})
    monkeypatch.setattr(td_routes._fp_repo, 'record_activation', lambda i, d: None)
    import foi_parcurs.services.pdf_service as pdf
    made = {'pdf': False}
    monkeypatch.setattr(pdf, 'generate_legal_pdf', lambda c: made.__setitem__('pdf', True) or '/tmp/l.pdf')
    resp = client.put('/api/foi-parcurs/test-drive/101/activate',
                      json={'client_signature': 'data:sig', 'fuel_gauge_start_level': '1/2'})
    assert resp.status_code == 409
    assert made['pdf'] is False


def test_discard_deletes_planned(client, monkeypatch):
    monkeypatch.setattr(td_routes._fp_repo, 'get_contract_by_id',
                        lambda i: {'id': i, 'route_type': 'TD', 'status': 'PLANNED'})
    deleted = {}
    monkeypatch.setattr(td_routes._fp_repo, 'delete_contract', lambda i: deleted.__setitem__('id', i))
    resp = client.delete('/api/foi-parcurs/test-drive/101')
    assert resp.status_code == 200 and resp.get_json()['success'] is True
    assert deleted['id'] == 101


def test_discard_refuses_non_planned(client, monkeypatch):
    monkeypatch.setattr(td_routes._fp_repo, 'get_contract_by_id',
                        lambda i: {'id': i, 'route_type': 'TD', 'status': 'FILLED'})
    resp = client.delete('/api/foi-parcurs/test-drive/101')
    assert resp.status_code == 409


def test_find_conflicts_overlap(monkeypatch):
    from foi_parcurs.repositories.foi_parcurs_repository import FoiParcursRepository
    repo = FoiParcursRepository.__new__(FoiParcursRepository)
    captured = {}
    def fake_query_all(sql, params):
        captured['sql'] = sql; captured['params'] = params
        return [{'id': 9, 'status': 'PLANNED'}]
    repo.query_all = fake_query_all
    rows = repo.find_conflicts('V1', '2026-08-01T09:00:00', '2026-08-01T11:00:00', exclude_id=5)
    assert rows and rows[0]['id'] == 9
    # VIN + window + exclude_id all bound
    assert 'V1' in captured['params'] and 5 in captured['params']
    assert 'PLANNED' in captured['sql']


def test_conflicts_route_requires_from_and_to(client):
    resp = client.get('/api/foi-parcurs/vehicles/V1/conflicts')
    assert resp.status_code == 400


def test_conflicts_route_returns_conflicts(client, monkeypatch):
    captured = {}
    def fake_find_conflicts(vin, frm, to, exclude_id=None):
        captured.update(vin=vin, frm=frm, to=to, exclude_id=exclude_id)
        return [{'id': 9, 'status': 'PLANNED'}]
    monkeypatch.setattr(veh_routes._fp_repo, 'find_conflicts', fake_find_conflicts)
    resp = client.get('/api/foi-parcurs/vehicles/V1/conflicts',
                       query_string={'from': '2026-08-01T09:00:00', 'to': '2026-08-01T11:00:00', 'exclude_id': 5})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['conflicts'] == [{'id': 9, 'status': 'PLANNED'}]
    assert captured['vin'] == 'V1'
    assert captured['exclude_id'] == 5
