"""Generic PUT /vehicles/<id> must not write `status` directly.

`status` is in VEHICLE_UPDATABLE_FIELDS, so a raw field PUT could otherwise
flip a vehicle's status straight into the DB — bypassing change_status()'s
TRANSITIONS validation, the RESERVED/SOLD/DELIVERED Dispo-action guards, and
status-history logging. The route must pull `status` out and, only when it
actually changes, apply it via VehicleService.change_status().

Uses the real Flask app (mirrors test_finance_strip.py) so the actual
permission-decorator + Flask-Login wiring runs.
"""
import os
from unittest import mock

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest

import app as app_module
from app import app as flask_app
from carpark.routes import vehicles as vehicles_module


@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    return flask_app.test_client()


def _login(client, monkeypatch, uid):
    user = {'id': uid, 'email': f't{uid}@x.com', 'name': 'T', 'company_id': 1,
            'can_access_carpark': True, 'can_edit_carpark': True,
            'can_view_carpark_finance': True}
    monkeypatch.setattr(app_module._user_repo, 'get_by_id', lambda _u: user)
    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)


def _patch_services(monkeypatch, base_vehicle, change_status_impl=None):
    """Capture change_status + update_vehicle calls; return the records dict."""
    rec = {'change_status': [], 'update_data': None}

    def _change_status(vehicle_id, new_status, **kwargs):
        rec['change_status'].append((vehicle_id, new_status, kwargs))
        if change_status_impl:
            return change_status_impl(vehicle_id, new_status, **kwargs)
        return {**base_vehicle, 'status': new_status}

    def _update(vehicle_id, data, **kwargs):
        rec['update_data'] = dict(data)
        return {**base_vehicle, **data}

    monkeypatch.setattr(vehicles_module._vehicle_service, 'change_status', _change_status)
    monkeypatch.setattr(vehicles_module._vehicle_service, 'update_vehicle', _update)
    monkeypatch.setattr(vehicles_module, '_verify_vehicle_ownership',
                        lambda vid: (base_vehicle, None))
    # Neutralize the best-effort autosync side effect.
    import tasks.listing_autosync as autosync
    monkeypatch.setattr(autosync, 'maybe_instant_resync', lambda vid: None)
    return rec


BASE = {'id': 1, 'company_id': 1, 'vin': 'X' * 17, 'status': 'LISTED'}


def test_changed_status_routes_through_change_status(client, monkeypatch):
    _login(client, monkeypatch, uid=94011)
    rec = _patch_services(monkeypatch, BASE)
    r = client.put('/api/carpark/vehicles/1', json={'status': 'RESERVED', 'model': 'X5'})
    assert r.status_code == 200
    # status went through the guarded path...
    assert rec['change_status'] == [(1, 'RESERVED', {'changed_by': 94011, 'notes': None})]
    # ...and was NOT written via the raw field update.
    assert 'status' not in rec['update_data']
    assert rec['update_data']['model'] == 'X5'


def test_unchanged_status_does_not_call_change_status(client, monkeypatch):
    _login(client, monkeypatch, uid=94012)
    rec = _patch_services(monkeypatch, BASE)
    r = client.put('/api/carpark/vehicles/1', json={'status': 'LISTED', 'model': 'X5'})
    assert r.status_code == 200
    assert rec['change_status'] == []          # same status → no-op
    assert 'status' not in rec['update_data']   # still never written raw
    assert rec['update_data']['model'] == 'X5'


def test_illegal_transition_returns_400_and_skips_field_update(client, monkeypatch):
    _login(client, monkeypatch, uid=94013)

    def _boom(vehicle_id, new_status, **kwargs):
        raise ValueError('Tranziție interzisă: LISTED → SOLD')

    rec = _patch_services(monkeypatch, BASE, change_status_impl=_boom)
    r = client.put('/api/carpark/vehicles/1', json={'status': 'SOLD', 'model': 'X5'})
    assert r.status_code == 400
    # change_status was attempted first, so the raw field update never ran.
    assert rec['update_data'] is None


def test_put_without_status_never_touches_change_status(client, monkeypatch):
    # Regression guard for the normal editor save path (which sends no status).
    _login(client, monkeypatch, uid=94014)
    rec = _patch_services(monkeypatch, BASE)
    r = client.put('/api/carpark/vehicles/1', json={'model': 'X5', 'current_price': 18000})
    assert r.status_code == 200
    assert rec['change_status'] == []
    assert rec['update_data']['model'] == 'X5'
    assert rec['update_data']['current_price'] == 18000
