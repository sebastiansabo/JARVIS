"""Tests for the hard company->contact gate + driver snapshot on
POST /api/foi-parcurs/test-drive.

A company client (crm_clients.client_type == 'company') cannot submit a live
test drive without naming a gate-valid driver contact (a person with the six
gate fields: full_name, email, phone, driver_license_photo,
driver_license_serie, driver_license_number) belonging to that same client.
A person client (or an internal QuickSession) needs no contact — the driver
snapshot mirrors the client directly.

Uses the Flask test client against a minimal app registering foi_parcurs_bp,
with _fp_repo/_crm_client_repo/_contact_repo mocked at the module level where
they are imported into foi_parcurs.routes.test_drive (mirrors
test_mkt_project_search.py / test_test_drive_submit.py).
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
import pytest
from flask import Flask
from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.test_drive as td_mod


class FakeFp:
    def create_from_td_form(self, data):
        self.last = data
        return {'id': 99, **data}

    def execute(self, *a, **k):
        return None


class FakeCrm:
    def __init__(self, client_type):
        self.client_type = client_type

    def get_by_id(self, cid):
        return {'id': cid, 'display_name': 'ACME SRL', 'phone': '072',
                'email': 'acme@example.ro', 'client_type': self.client_type}

    def execute(self, *a, **k):
        return None


class FakeContacts:
    def __init__(self, contact):
        self.contact = contact

    def get(self, cid):
        return self.contact


def make_app(monkeypatch, client_type, contact):
    monkeypatch.setattr(td_mod, '_fp_repo', FakeFp())
    monkeypatch.setattr(td_mod, '_crm_client_repo', FakeCrm(client_type))
    monkeypatch.setattr(td_mod, '_contact_repo', FakeContacts(contact))
    app = Flask(__name__)
    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    return app.test_client()


# Complete payload for a NON-draft, NON-internal live submit: all of
# company_id, vin, client_id, odometer_start, estimated_km,
# fuel_gauge_start_level, departure_datetime, advisor_name, client_signature
# are required by api_submit_test_drive's `required` list before the route
# ever reaches the company->contact gate. Missing any of these would 400 with
# a generic "Missing: ..." error instead of exercising the gate.
BASE_PAYLOAD = {
    'vin': 'WVW1', 'company_id': 11, 'client_id': 5, 'registration_number': 'CJ 12 ABC',
    'departure_datetime': '2026-08-18T10:00', 'odometer_start': 1000,
    'estimated_km': 50, 'fuel_gauge_start_level': '1',
    'advisor_name': 'Adv', 'client_signature': 'data:sig',
    'driver_license_photo': 'data:...', 'driver_license_number': '123456',
    'fuel_tank_capacity_liters': 50,
}
VALID_CONTACT = {'id': 7, 'client_id': 5, 'full_name': 'Ion', 'email': 'i@b.ro', 'phone': '072',
                 'driver_license_photo': 'data:...', 'driver_license_serie': 'CJ',
                 'driver_license_number': '123456'}


def test_company_without_contact_is_rejected(monkeypatch):
    c = make_app(monkeypatch, 'company', None)
    r = c.post('/api/foi-parcurs/test-drive', json=dict(BASE_PAYLOAD))
    assert r.status_code == 400
    assert 'contact' in r.get_json()['error'].lower() or 'persoan' in r.get_json()['error'].lower()


def test_company_with_valid_contact_is_accepted(monkeypatch):
    c = make_app(monkeypatch, 'company', VALID_CONTACT)
    r = c.post('/api/foi-parcurs/test-drive',
               json={**BASE_PAYLOAD, 'driver_contact_id': 7})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    contract = body['contract']
    assert contract['driver_contact_id'] == 7
    assert contract['driver_name'] == 'Ion'
    assert contract['driver_email'] == 'i@b.ro'
    assert contract['driver_phone'] == '072'
    assert contract['driver_license_serie'] == 'CJ'


def test_person_client_needs_no_contact(monkeypatch):
    c = make_app(monkeypatch, 'person', None)
    r = c.post('/api/foi-parcurs/test-drive', json=dict(BASE_PAYLOAD))
    assert r.status_code == 200, r.get_json()
    contract = r.get_json()['contract']
    assert contract['driver_contact_id'] is None
    assert contract['driver_name'] == 'ACME SRL'
    assert contract['driver_phone'] == '072'


def test_company_contact_mismatched_client_is_rejected(monkeypatch):
    """A contact belonging to a DIFFERENT client must not satisfy the gate."""
    other_client_contact = {**VALID_CONTACT, 'client_id': 999}
    c = make_app(monkeypatch, 'company', other_client_contact)
    r = c.post('/api/foi-parcurs/test-drive',
               json={**BASE_PAYLOAD, 'driver_contact_id': 7})
    assert r.status_code == 400
    assert 'contact' in r.get_json()['error'].lower() or 'persoan' in r.get_json()['error'].lower()


def test_company_contact_missing_gate_field_is_rejected(monkeypatch):
    """A contact missing one of the six gate-required fields must be rejected."""
    incomplete_contact = {**VALID_CONTACT, 'driver_license_serie': None}
    c = make_app(monkeypatch, 'company', incomplete_contact)
    r = c.post('/api/foi-parcurs/test-drive',
               json={**BASE_PAYLOAD, 'driver_contact_id': 7})
    assert r.status_code == 400
    assert 'contact' in r.get_json()['error'].lower() or 'persoan' in r.get_json()['error'].lower()
