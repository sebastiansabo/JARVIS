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


def test_submit_allowed_when_locked_but_override(client, monkeypatch):
    """A blocked car proceeds when the form sends the confirmed allow_locked flag."""
    captured = {}
    _stub_create(monkeypatch, captured)
    monkeypatch.setattr(td_routes._vehicle_repo, 'get_lock_by_vin',
                        lambda vin: {'locked_out': True, 'lockout_category': 'service', 'lockout_note': 'x'})
    resp = client.post('/api/foi-parcurs/test-drive', json=_body(allow_locked=True))
    assert resp.status_code == 200, resp.get_json()


# ── Configurable lockout reasons ────────────────────────────────────────────

def test_lockout_reasons_list(client, monkeypatch):
    monkeypatch.setattr(
        td_routes._vehicle_repo, 'list_lockout_reasons',
        lambda active_only=False: [{'id': 1, 'slug': 'service', 'label': 'În service', 'sort_order': 1, 'is_active': True}],
    )
    resp = client.get('/api/foi-parcurs/lockout-reasons')
    assert resp.status_code == 200
    assert resp.get_json()['reasons'][0]['slug'] == 'service'


def test_create_lockout_reason_derives_slug(client, monkeypatch):
    monkeypatch.setattr(td_routes._vehicle_repo, 'slug_exists', lambda slug: False)
    captured = {}
    def fake_create(slug, label, sort_order=0):
        captured.update(slug=slug, label=label)
        return {'id': 9, 'slug': slug, 'label': label, 'sort_order': sort_order, 'is_active': True}
    monkeypatch.setattr(td_routes._vehicle_repo, 'create_lockout_reason', fake_create)
    resp = client.post('/api/foi-parcurs/lockout-reasons', json={'label': 'Rezervat / VIP'})
    assert resp.status_code == 200, resp.get_json()
    assert captured['slug'] == 'rezervat-vip'
    assert captured['label'] == 'Rezervat / VIP'


def test_create_lockout_reason_requires_label(client):
    resp = client.post('/api/foi-parcurs/lockout-reasons', json={'label': '   '})
    assert resp.status_code == 400


def test_lock_rejects_unknown_category(client, monkeypatch):
    monkeypatch.setattr(td_routes._vehicle_repo, 'get_active_lockout_slugs', lambda: {'service', 'damage'})
    resp = client.post('/api/foi-parcurs/vehicles/1/lock', json={'category': 'nonsense'})
    assert resp.status_code == 400


def test_lock_accepts_active_db_category(client, monkeypatch):
    monkeypatch.setattr(td_routes._vehicle_repo, 'get_active_lockout_slugs', lambda: {'service', 'reserved'})
    monkeypatch.setattr(td_routes._vehicle_repo, 'lock_vehicle', lambda *a, **k: {'id': 1, 'locked_out': True})
    resp = client.post('/api/foi-parcurs/vehicles/1/lock', json={'category': 'reserved'})
    assert resp.status_code == 200, resp.get_json()


# ── Lock/unlock history log (fp_vehicle_lock_events) ────────────────────────

def test_unlock_passes_actor_to_repo(client, monkeypatch):
    """The unlock route must record WHO unblocked the car, so unlock_vehicle is
    called with the acting user id — not just the vehicle id."""
    captured = {}
    def fake_unlock(*args, **kwargs):
        captured['args'] = args
        return {'id': 7, 'locked_out': False}
    monkeypatch.setattr(td_routes._vehicle_repo, 'unlock_vehicle', fake_unlock)
    resp = client.post('/api/foi-parcurs/vehicles/7/unlock')
    assert resp.status_code == 200, resp.get_json()
    assert captured['args'][0] == 7
    assert len(captured['args']) == 2  # (vehicle_id, actor_id)


def test_lock_events_endpoint_returns_history(client, monkeypatch):
    """GET .../lock-events returns the car's block/unblock audit trail, newest first."""
    monkeypatch.setattr(
        td_routes._vehicle_repo, 'get_lock_events',
        lambda vid: [
            {'id': 2, 'action': 'unlock', 'category': None, 'note': None,
             'actor_name': 'Ion Pop', 'created_at': '2026-08-28T09:12:00+00:00'},
            {'id': 1, 'action': 'lock', 'category': 'service', 'note': 'în service',
             'actor_name': 'Sebastian Sabo', 'created_at': '2026-08-31T14:05:00+00:00'},
        ],
    )
    resp = client.get('/api/foi-parcurs/vehicles/7/lock-events')
    assert resp.status_code == 200, resp.get_json()
    events = resp.get_json()['events']
    assert events[0]['action'] == 'unlock'
    assert events[1]['actor_name'] == 'Sebastian Sabo'
