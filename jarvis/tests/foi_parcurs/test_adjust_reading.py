"""Tests for the inline odometer-boundary editor:
PUT /api/foi-parcurs/contracts/<id>/reading — moves ONE session's KM reading
(and, where the chain is contiguous, the shared reading on the adjacent
session). Nothing else on the row changes. Enforces the odometer chain stays
monotonic (a moved reading stays strictly between its neighbours) and the
earliest reading never drops below the prior session's close (last month's
ending odometer). Reuses the test_drive.contracts.correct permission.

Auth harness mirrors test_correct_session.py: a FakeUser + request_loader
exercises the real @v2_permission_required decorator.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask
from flask_login import LoginManager, UserMixin

from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.contracts as contracts_mod


class FakeUser(UserMixin):
    def __init__(self, uid, role_name='', role_id=None, is_admin=False):
        self.id = uid
        self.role_name = role_name
        self.role_id = role_id
        self.is_admin = is_admin
        self.email = 'admin@test'


ADMIN = FakeUser(2, role_name='admin', is_admin=True)
UNPRIV = FakeUser(1)


@pytest.fixture
def client():
    app = Flask(__name__)
    app.secret_key = 'test'
    lm = LoginManager()
    lm.init_app(app)

    @lm.user_loader
    def _load(uid):
        return None

    @lm.request_loader
    def _load_req(req):
        return {'admin': ADMIN, 'unpriv': UNPRIV}.get(req.headers.get('X-Test-User'))

    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    return app.test_client()


def _hdr(kind):
    return {'X-Test-User': kind}


def _contract(**kw):
    base = {
        'id': 1, 'route_type': 'TD', 'status': 'COMPLETED', 'vin': 'VIN1',
        'km_start': 120, 'km_end': 150,
    }
    base.update(kw)
    return base


# Vehicle odometer chain (KM-ordered): A(100-120) · C(120-150) · B(150-170).
# C is the edited session; it is contiguous with A at 120 and B at 150.
def _chain():
    return [
        {'id': 10, 'status': 'COMPLETED', 'km_start': 100, 'km_end': 120},
        {'id': 1, 'status': 'COMPLETED', 'km_start': 120, 'km_end': 150},
        {'id': 20, 'status': 'COMPLETED', 'km_start': 150, 'km_end': 170},
    ]


@pytest.fixture(autouse=True)
def _stub_side_effects(monkeypatch):
    monkeypatch.setattr(contracts_mod, 'log_history', lambda *a, **k: None)
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_odometer_readings', lambda vin: _chain())
    # Default vehicle: odometer already at the chain top so no floor advance fires
    # unless a test raises the end above it.
    monkeypatch.setattr(contracts_mod._vehicle_repo, 'get_by_vin', lambda vin: {'id': 7, 'odometer_km': 170})
    monkeypatch.setattr(contracts_mod._vehicle_repo, 'update', lambda vid, data: None)


def _stub_read(monkeypatch, contract):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda cid: contract)


def _capture_writes(monkeypatch):
    """Capture the updates handed to adjust_boundary_readings; return the written
    ids (its real contract) so the route can log + echo them."""
    captured = {}

    def fake_adjust(updates, modified_by=None):
        captured['updates'] = [dict(u) for u in updates]
        captured['modified_by'] = modified_by
        return [u['id'] for u in updates]

    monkeypatch.setattr(contracts_mod._fp_repo, 'adjust_boundary_readings', fake_adjust)
    return captured


def test_reading_requires_authentication(client):
    resp = client.put('/api/foi-parcurs/contracts/1/reading', json={'km_end': 160})
    assert resp.status_code == 401


def test_reading_denied_without_permission(client):
    resp = client.put('/api/foi-parcurs/contracts/1/reading', json={'km_end': 160}, headers=_hdr('unpriv'))
    assert resp.status_code == 403


def test_reading_404_when_missing(client, monkeypatch):
    _stub_read(monkeypatch, None)
    resp = client.put('/api/foi-parcurs/contracts/9/reading', json={'km_end': 160}, headers=_hdr('admin'))
    assert resp.status_code == 404


def test_reading_rejects_planned_session(client, monkeypatch):
    _stub_read(monkeypatch, _contract(status='PLANNED'))
    resp = client.put('/api/foi-parcurs/contracts/1/reading', json={'km_end': 160}, headers=_hdr('admin'))
    assert resp.status_code == 400


def test_reading_rejects_missed_session(client, monkeypatch):
    # A MISSED (Ratat) row never drove — no real odometer span to edit.
    _stub_read(monkeypatch, _contract(status='MISSED'))
    resp = client.put('/api/foi-parcurs/contracts/1/reading', json={'km_end': 160}, headers=_hdr('admin'))
    assert resp.status_code == 400


def test_reading_rejects_non_numeric(client, monkeypatch):
    _stub_read(monkeypatch, _contract())
    resp = client.put('/api/foi-parcurs/contracts/1/reading', json={'km_end': 'abc'}, headers=_hdr('admin'))
    assert resp.status_code == 400


def test_reading_rejects_end_below_start(client, monkeypatch):
    _stub_read(monkeypatch, _contract())
    resp = client.put('/api/foi-parcurs/contracts/1/reading', json={'km_start': 145, 'km_end': 130}, headers=_hdr('admin'))
    assert resp.status_code == 400


def test_reading_contiguous_end_moves_next_start(client, monkeypatch):
    # C.km_end 150 -> 160; B is contiguous at 150 so B.km_start moves to 160 too.
    _stub_read(monkeypatch, _contract())
    cap = _capture_writes(monkeypatch)
    resp = client.put('/api/foi-parcurs/contracts/1/reading', json={'km_end': 160}, headers=_hdr('admin'))
    assert resp.status_code == 200, resp.get_json()
    ups = {u['id']: u for u in cap['updates']}
    assert ups[1].get('km_end') == 160
    assert ups[20].get('km_start') == 160  # shared reading on the next session moved


def test_reading_contiguous_start_moves_prev_end(client, monkeypatch):
    # C.km_start 120 -> 110; A is contiguous at 120 so A.km_end moves to 110 too.
    _stub_read(monkeypatch, _contract())
    cap = _capture_writes(monkeypatch)
    resp = client.put('/api/foi-parcurs/contracts/1/reading', json={'km_start': 110}, headers=_hdr('admin'))
    assert resp.status_code == 200, resp.get_json()
    ups = {u['id']: u for u in cap['updates']}
    assert ups[1].get('km_start') == 110
    assert ups[10].get('km_end') == 110


def test_reading_rejects_end_above_next_session(client, monkeypatch):
    # C.km_end 150 -> 180 would overrun B's end (170): chronological violation.
    _stub_read(monkeypatch, _contract())
    _capture_writes(monkeypatch)
    resp = client.put('/api/foi-parcurs/contracts/1/reading', json={'km_end': 180}, headers=_hdr('admin'))
    assert resp.status_code == 400


def test_reading_rejects_start_below_prev_session(client, monkeypatch):
    # C.km_start 120 -> 90 would drop below A's start (100): chronological /
    # "not below last month" violation.
    _stub_read(monkeypatch, _contract())
    _capture_writes(monkeypatch)
    resp = client.put('/api/foi-parcurs/contracts/1/reading', json={'km_start': 90}, headers=_hdr('admin'))
    assert resp.status_code == 400


def test_reading_gap_end_moves_only_this_session(client, monkeypatch):
    # Chain with a gap after C: B starts at 160, not 150. Editing C.km_end to 155
    # stays under the gap ceiling (160) and must NOT touch B.
    gapped = [
        {'id': 10, 'status': 'COMPLETED', 'km_start': 100, 'km_end': 120},
        {'id': 1, 'status': 'COMPLETED', 'km_start': 120, 'km_end': 150},
        {'id': 20, 'status': 'COMPLETED', 'km_start': 160, 'km_end': 190},
    ]
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_odometer_readings', lambda vin: gapped)
    _stub_read(monkeypatch, _contract())
    cap = _capture_writes(monkeypatch)
    resp = client.put('/api/foi-parcurs/contracts/1/reading', json={'km_end': 155}, headers=_hdr('admin'))
    assert resp.status_code == 200, resp.get_json()
    ids = {u['id'] for u in cap['updates']}
    assert ids == {1}  # only C, the next session is untouched across the gap


def test_reading_gap_end_rejects_above_next_start(client, monkeypatch):
    gapped = [
        {'id': 1, 'status': 'COMPLETED', 'km_start': 120, 'km_end': 150},
        {'id': 20, 'status': 'COMPLETED', 'km_start': 160, 'km_end': 190},
    ]
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_odometer_readings', lambda vin: gapped)
    _stub_read(monkeypatch, _contract())
    _capture_writes(monkeypatch)
    resp = client.put('/api/foi-parcurs/contracts/1/reading', json={'km_end': 165}, headers=_hdr('admin'))
    assert resp.status_code == 400


def test_reading_earliest_session_start_edit_allowed(client, monkeypatch):
    # C is the only/earliest session for the vin (no prior close to floor against).
    solo = [{'id': 1, 'status': 'COMPLETED', 'km_start': 120, 'km_end': 150}]
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_odometer_readings', lambda vin: solo)
    _stub_read(monkeypatch, _contract())
    cap = _capture_writes(monkeypatch)
    resp = client.put('/api/foi-parcurs/contracts/1/reading', json={'km_start': 100}, headers=_hdr('admin'))
    assert resp.status_code == 200, resp.get_json()
    assert {u['id'] for u in cap['updates']} == {1}


def test_reading_advances_vehicle_odometer_when_top_rises(client, monkeypatch):
    # C is the last session; raising its end above the vehicle odometer advances it.
    solo = [{'id': 1, 'status': 'COMPLETED', 'km_start': 120, 'km_end': 150}]
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_odometer_readings', lambda vin: solo)
    _stub_read(monkeypatch, _contract())
    _capture_writes(monkeypatch)
    monkeypatch.setattr(contracts_mod._vehicle_repo, 'get_by_vin', lambda vin: {'id': 7, 'odometer_km': 150})
    updated = {}
    monkeypatch.setattr(contracts_mod._vehicle_repo, 'update', lambda vid, data: updated.update({vid: data}))
    resp = client.put('/api/foi-parcurs/contracts/1/reading', json={'km_end': 200}, headers=_hdr('admin'))
    assert resp.status_code == 200, resp.get_json()
    assert updated == {7: {'odometer_km': 200}}
