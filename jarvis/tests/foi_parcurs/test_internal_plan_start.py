"""Internal (QuickSession) sessions get a real planned → start lifecycle,
mirroring the customer draft → activate flow.

- Creation with `is_internal:true` + `status:'PLANNED'` makes a PLANNED draft
  that defers the odometer/km to start (advisor + car + date are enough).
- A dedicated `PUT /test-drive/<id>/start` flips that PLANNED internal draft to
  FILLED, capturing the real km plecare — with NO client/signature/GDPR/PDF
  (the internal counterpart to `/activate`).

Fixtures mirror test_test_drive_internal.py / test_plan_session.py.
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
def _hermetic(monkeypatch):
    # Keep the create/start paths off the DB: general-conditions lookup, lock
    # check, single-open-session guard, privilege check and the status/history
    # log all run unconditionally and would otherwise touch Postgres.
    monkeypatch.setattr(td._vehicle_repo, 'get_by_vin', lambda vin: {'brand': ''})
    monkeypatch.setattr(td._dealer_repo, 'get_general_conditions', lambda cid, b: '')
    monkeypatch.setattr(td._vehicle_repo, 'get_lock_by_vin', lambda vin: None, raising=False)
    monkeypatch.setattr(td, 'open_session_block', lambda *a, **k: None, raising=False)
    monkeypatch.setattr(td, 'is_privileged', lambda: False, raising=False)
    monkeypatch.setattr(td, 'log_history', lambda *a, **k: None, raising=False)
    monkeypatch.setattr(td, 'log_status_change', lambda *a, **k: None, raising=False)


def _draft_payload(**overrides):
    """A planned internal session — car, driver and date only; km deferred."""
    payload = {
        'is_internal': True,
        'status': 'PLANNED',
        'company_id': 1,
        'vin': 'WVWZZZ1JZXW000001',
        'departure_datetime': '2026-09-28T11:55:00',
        'return_datetime': '2026-10-07T12:55:00',
        'advisor_name': 'Ana Pop',
        # NOTE: no odometer_start — deferred to start.
    }
    payload.update(overrides)
    return payload


# ── creation: internal + PLANNED = a draft with km deferred ──────────────────

def test_internal_draft_creates_planned_without_odometer(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(td._fp_repo, 'create_from_td_form',
                        lambda data: captured.update(data) or {**data, 'id': 51})

    resp = client.post('/api/foi-parcurs/test-drive', json=_draft_payload())

    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()['success'] is True
    assert captured['is_internal'] is True
    assert captured['status'] == 'PLANNED'
    assert captured['client_id'] is None
    assert captured['km_start'] == 0  # deferred to start


def test_internal_live_still_requires_odometer(client):
    # A live (non-draft) internal session still needs the km at handover.
    resp = client.post('/api/foi-parcurs/test-drive',
                       json=_draft_payload(status=None, odometer_start=None))
    assert resp.status_code == 400
    assert 'odometer_start' in resp.get_json()['error']


# ── start: PLANNED internal draft → FILLED, no signature/PDF ──────────────────

def _planned_internal_row(**overrides):
    row = {'id': 51, 'route_type': 'TD', 'status': 'PLANNED', 'is_internal': True,
           'vin': 'WVWZZZ1JZXW000001', 'km_start': 0}
    row.update(overrides)
    return row


def test_start_flips_planned_internal_to_filled(client, monkeypatch):
    monkeypatch.setattr(td._fp_repo, 'get_contract_by_id', lambda i: _planned_internal_row())
    monkeypatch.setattr(td._fp_repo, 'get_mileage_floor', lambda vin, exclude_id=None: 0)
    seen = {}
    monkeypatch.setattr(td._fp_repo, 'record_activation',
                        lambda i, d: seen.update(d) or {**_planned_internal_row(id=i), 'status': 'FILLED', 'km_start': d.get('km_start')})

    resp = client.put('/api/foi-parcurs/test-drive/51/start', json={'odometer_start': 4200})

    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()['contract']['status'] == 'FILLED'
    assert seen['km_start'] == 4200  # real km captured at start


def test_start_refuses_non_internal(client, monkeypatch):
    monkeypatch.setattr(td._fp_repo, 'get_contract_by_id',
                        lambda i: _planned_internal_row(is_internal=False))
    resp = client.put('/api/foi-parcurs/test-drive/51/start', json={'odometer_start': 4200})
    assert resp.status_code == 400


def test_start_refuses_non_planned(client, monkeypatch):
    monkeypatch.setattr(td._fp_repo, 'get_contract_by_id',
                        lambda i: _planned_internal_row(status='FILLED'))
    resp = client.put('/api/foi-parcurs/test-drive/51/start', json={'odometer_start': 4200})
    assert resp.status_code == 400
