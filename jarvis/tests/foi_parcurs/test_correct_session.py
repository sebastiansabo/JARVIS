"""Tests for the admin session-correction endpoint:
PUT /api/foi-parcurs/contracts/<id>/correct — lets a privileged user fix
data-entry anomalies (wrong drive date / odometer) on any session, any status.

Auth is exercised with a FakeUser + request_loader (mirrors
jarvis/tests/happy/test_admin_permissions.py) rather than monkeypatching a gate
helper — the reliable way to test the real decorator/guard. The ADMIN fixture
carries BOTH role_name='admin' (satisfies the legacy _is_admin() gate) and
is_admin=True (satisfies the @v2_permission_required decorator), so this test is
correct whether the endpoint is matrix-gated or role-name gated.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask
from flask_login import LoginManager, UserMixin

from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.contracts as contracts_mod


class FakeUser(UserMixin):
    def __init__(self, uid, role_name='', role_id=None, is_admin=False, can_access_settings=False):
        self.id = uid
        self.role_name = role_name
        self.role_id = role_id
        self.is_admin = is_admin
        self.can_access_settings = can_access_settings
        self.email = None


ADMIN = FakeUser(2, role_name='admin', is_admin=True)   # passes both gate styles
UNPRIV = FakeUser(1)                                     # authenticated, neither -> 403


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
        'km_start': 1236, 'km_end': 1258,
        'departure_datetime': '2026-08-03T09:00', 'return_datetime': '2026-08-03T10:00',
    }
    base.update(kw)
    return base


@pytest.fixture(autouse=True)
def _stub_side_effects(monkeypatch):
    # Keep the happy path off the DB: revive is called unconditionally and its
    # result is used; log_history is best-effort. Repo reads/writes are stubbed
    # per-test.
    monkeypatch.setattr(contracts_mod._fp_repo, 'revive_to_active_if_window_open', lambda id: None)
    monkeypatch.setattr(contracts_mod, 'log_history', lambda *a, **k: None)


def test_correct_requires_authentication(client):
    # No user loaded -> 401 before any work.
    resp = client.put('/api/foi-parcurs/contracts/1/correct', json={'km_end': 1300})
    assert resp.status_code == 401


def test_correct_denied_without_permission(client):
    # Authenticated but not privileged/granted -> 403.
    resp = client.put('/api/foi-parcurs/contracts/1/correct', json={'km_end': 1300}, headers=_hdr('unpriv'))
    assert resp.status_code == 403


def test_correct_404_when_missing(client, monkeypatch):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: None)
    resp = client.put('/api/foi-parcurs/contracts/9/correct', json={'km_end': 1300}, headers=_hdr('admin'))
    assert resp.status_code == 404


def test_correct_requires_at_least_one_field(client, monkeypatch):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: _contract())
    resp = client.put('/api/foi-parcurs/contracts/1/correct', json={}, headers=_hdr('admin'))
    assert resp.status_code == 400


def test_correct_rejects_km_end_below_km_start(client, monkeypatch):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: _contract(km_start=1236))
    resp = client.put('/api/foi-parcurs/contracts/1/correct', json={'km_start': 1236, 'km_end': 900}, headers=_hdr('admin'))
    assert resp.status_code == 400
    assert 'km_end' in resp.get_json()['error']


def test_correct_rejects_km_end_below_existing_start(client, monkeypatch):
    # Only km_end supplied → validated against the existing km_start.
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: _contract(km_start=1236))
    resp = client.put('/api/foi-parcurs/contracts/1/correct', json={'km_end': 1000}, headers=_hdr('admin'))
    assert resp.status_code == 400


def test_correct_rejects_non_numeric_km(client, monkeypatch):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: _contract())
    resp = client.put('/api/foi-parcurs/contracts/1/correct', json={'km_end': 'abc'}, headers=_hdr('admin'))
    assert resp.status_code == 400


def test_correct_rejects_unparseable_date(client, monkeypatch):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: _contract())
    resp = client.put('/api/foi-parcurs/contracts/1/correct', json={'departure_datetime': 'not-a-date'}, headers=_hdr('admin'))
    assert resp.status_code == 400


def test_correct_rejects_return_before_departure(client, monkeypatch):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: _contract())
    resp = client.put('/api/foi-parcurs/contracts/1/correct',
                      json={'departure_datetime': '2026-08-05T10:00', 'return_datetime': '2026-08-05T09:00'},
                      headers=_hdr('admin'))
    assert resp.status_code == 400
    assert 'return' in resp.get_json()['error'].lower()


def test_correct_tolerates_tzaware_stored_dates(client, monkeypatch):
    # REGRESSION: stored departure/return come back tz-AWARE from the DB; a
    # km-only correction still runs the date-order check against them and must
    # not raise TypeError → 500 when compared to a naive submitted value.
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id',
                        lambda id: _contract(departure_datetime='2026-08-03T09:00:00+03:00',
                                             return_datetime='2026-08-03T10:00:00+03:00'))
    monkeypatch.setattr(contracts_mod._fp_repo, 'correct_session',
                        lambda cid, fields, modified_by=None: _contract())
    resp = client.put('/api/foi-parcurs/contracts/1/correct',
                      json={'departure_datetime': '2026-08-03T08:00'}, headers=_hdr('admin'))
    assert resp.status_code == 200


def test_correct_km_happy_path(client, monkeypatch):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: _contract())
    captured = {}

    def fake_correct(cid, fields, modified_by=None):
        captured['cid'] = cid
        captured['fields'] = dict(fields)
        return _contract(km_start=1258, km_end=1300)

    monkeypatch.setattr(contracts_mod._fp_repo, 'correct_session', fake_correct)
    monkeypatch.setattr(contracts_mod._vehicle_repo, 'get_by_vin', lambda vin: {'id': 7, 'odometer_km': 1000})
    updated_veh = {}
    monkeypatch.setattr(contracts_mod._vehicle_repo, 'update', lambda vid, data: updated_veh.update({vid: data}))

    resp = client.put('/api/foi-parcurs/contracts/1/correct', json={'km_start': 1258, 'km_end': 1300}, headers=_hdr('admin'))
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert captured['cid'] == 1
    assert captured['fields'] == {'km_start': 1258, 'km_end': 1300}
    # km_end (1300) raised above the vehicle odometer (1000) → floor advanced.
    assert updated_veh == {7: {'odometer_km': 1300}}


def test_correct_dates_happy_path(client, monkeypatch):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: _contract())
    captured = {}
    monkeypatch.setattr(contracts_mod._fp_repo, 'correct_session',
                        lambda cid, fields, modified_by=None: captured.update(fields) or _contract())
    resp = client.put('/api/foi-parcurs/contracts/1/correct',
                      json={'departure_datetime': '2026-08-06T09:00', 'return_datetime': '2026-08-06T11:00'},
                      headers=_hdr('admin'))
    assert resp.status_code == 200
    assert captured == {'departure_datetime': '2026-08-06T09:00', 'return_datetime': '2026-08-06T11:00'}
