"""Event-TD reservation is a SOFT confirm, not a hard block.

A car committed to an active Event TD page is reserved for that page's windows,
so a classic driving session over one of those windows is refused with a 409
`event_reserved`. The advisor may proceed after confirming (allow_event_reserved);
when they do, the event page's owners are notified that a session was booked over
their reserved window.

Route-level tests mirror the fixtures/monkeypatching in test_vehicle_lockout.py
(find_event_reservation is stubbed, so no DB row is needed).
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


_RESV = [{
    'page_id': 7, 'slug': 'caravana-volvo', 'title': 'Caravana Volvo',
    'window_date': '2026-08-01', 'start_time': '09:00', 'end_time': '18:00',
}]


def _stub_create(monkeypatch, captured):
    def fake_create(data):
        captured.update(data)
        return {'id': 101, **data}
    monkeypatch.setattr(td_routes._fp_repo, 'create_from_td_form', fake_create)
    monkeypatch.setattr(td_routes._crm_client_repo, 'get_by_id', lambda i: {'display_name': 'Ion', 'phone': '07'})
    monkeypatch.setattr(td_routes._vehicle_repo, 'get_lock_by_vin', lambda vin: None)


def test_submit_rejected_when_event_reserved(client, monkeypatch):
    """No override flag → the reservation still blocks the create (soft 409)."""
    monkeypatch.setattr(td_routes._vehicle_repo, 'get_lock_by_vin', lambda vin: None)
    monkeypatch.setattr(td_routes._fp_repo, 'find_event_reservation', lambda vin, frm, to: _RESV)
    resp = client.post('/api/foi-parcurs/test-drive', json=_body())
    assert resp.status_code == 409, resp.get_json()
    j = resp.get_json()
    assert j['event_reserved'] is True
    assert 'Caravana Volvo' in j['error']


def test_submit_allowed_when_event_reserved_override(client, monkeypatch):
    """allow_event_reserved → the session is created AND the owners are notified."""
    captured = {}
    _stub_create(monkeypatch, captured)
    monkeypatch.setattr(td_routes._fp_repo, 'find_event_reservation', lambda vin, frm, to: _RESV)
    notified = {}
    monkeypatch.setattr(td_routes, '_notify_event_reservation_override',
                        lambda resv, contract, actor=None: notified.update(resv=resv, contract=contract))
    resp = client.post('/api/foi-parcurs/test-drive', json=_body(allow_event_reserved=True))
    assert resp.status_code == 200, resp.get_json()
    assert notified['resv'][0]['page_id'] == 7
    assert notified['contract']['id'] == 101


def test_no_override_notify_when_not_reserved(client, monkeypatch):
    """A free car never triggers the override notification."""
    captured = {}
    _stub_create(monkeypatch, captured)
    monkeypatch.setattr(td_routes._fp_repo, 'find_event_reservation', lambda vin, frm, to: [])
    called = {'n': 0}
    monkeypatch.setattr(td_routes, '_notify_event_reservation_override',
                        lambda *a, **k: called.update(n=called['n'] + 1))
    resp = client.post('/api/foi-parcurs/test-drive', json=_body(allow_event_reserved=True))
    assert resp.status_code == 200, resp.get_json()
    assert called['n'] == 0
