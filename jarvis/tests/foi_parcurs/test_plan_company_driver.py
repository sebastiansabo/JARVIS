"""Planning a company-client Test Drive must persist the chosen driver contact
so the PLANNED session shows the actual driver (not the company name).

Root cause this guards: api_submit_test_drive deferred the company->contact
resolution to activation (`if not is_draft`), so a PLANNED company booking
stored driver_name = client_name (the company). The Hub list/detail derive the
driver from driver_name (clientCell), so the driver was invisible until
activation. The fix resolves the contact best-effort for a draft too — without
enforcing the hard gate, which stays deferred to activation.

Self-contained harness (the shared test_td_company_gate FakeFp predates the
event-reservation gate and lacks find_event_reservation).
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import foi_parcurs.routes.test_drive as td_mod
from flask import Flask
from foi_parcurs import foi_parcurs_bp


class FakeFp:
    def find_event_reservation(self, vin, dep, ret):
        return None

    def create_from_td_form(self, data):
        self.last = data
        return {'id': 99, **data}


class FakeCrm:
    def __init__(self, client_type, name):
        self.client_type = client_type
        self.name = name

    def get_by_id(self, cid):
        return {'id': cid, 'display_name': self.name, 'phone': '072', 'email': 'co@b.ro',
                'client_type': self.client_type}

    def execute(self, *a, **k):
        return None


class FakeContacts:
    def __init__(self, contact):
        self.contact = contact

    def get(self, cid):
        return self.contact


CONTACT = {'id': 7, 'client_id': 5, 'full_name': 'Ion Driver', 'email': 'ion@b.ro',
           'phone': '0733', 'driver_license_photo': 'data:...', 'driver_license_serie': 'CJ',
           'driver_license_number': '555'}

PLAN_PAYLOAD = {
    'status': 'PLANNED', 'company_id': 11, 'vin': 'WVW1', 'client_id': 5,
    'departure_datetime': '2999-08-18T10:00',
}


def _client(monkeypatch, client_type='company', contact=CONTACT):
    monkeypatch.setattr(td_mod, '_fp_repo', FakeFp())
    monkeypatch.setattr(td_mod, '_crm_client_repo', FakeCrm(client_type, 'SEBA TEST COMPANY S.R.L.'))
    monkeypatch.setattr(td_mod, '_contact_repo', FakeContacts(contact))
    monkeypatch.setattr(td_mod._vehicle_repo, 'get_lock_by_vin', lambda vin: None, raising=False)
    app = Flask(__name__)
    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    tc = app.test_client()
    tc._fp = td_mod._fp_repo
    return tc


def test_planned_company_booking_persists_driver_from_contact(monkeypatch):
    tc = _client(monkeypatch)
    r = tc.post('/api/foi-parcurs/test-drive', json={**PLAN_PAYLOAD, 'driver_contact_id': 7})
    assert r.status_code == 200, r.get_json()
    stored = tc._fp.last
    assert stored['driver_name'] == 'Ion Driver'      # the contact, not the company
    assert stored['driver_contact_id'] == 7


def test_planned_company_booking_without_contact_defers(monkeypatch):
    # No contact chosen → unchanged behavior: driver falls back to the client
    # (company), gate still deferred to activation. No crash.
    tc = _client(monkeypatch)
    r = tc.post('/api/foi-parcurs/test-drive', json=dict(PLAN_PAYLOAD))
    assert r.status_code == 200, r.get_json()
    assert tc._fp.last['driver_contact_id'] is None
