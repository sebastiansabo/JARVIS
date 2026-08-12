"""Tests for the admin session-correction endpoint:
PUT /api/foi-parcurs/contracts/<id>/correct — lets an admin fix data-entry
anomalies (wrong drive date / odometer) on any session, any status.

Flask test client against a minimal app registering foi_parcurs_bp, with the
repo + admin gate mocked at module level (mirrors test_test_drive_return.py).
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.contracts as contracts_mod


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True  # login_required is a no-op
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def as_admin(monkeypatch):
    monkeypatch.setattr(contracts_mod, '_is_admin', lambda: True)


def _contract(**kw):
    base = {
        'id': 1, 'route_type': 'TD', 'status': 'COMPLETED', 'vin': 'VIN1',
        'km_start': 1236, 'km_end': 1258,
        'departure_datetime': '2026-08-03T09:00', 'return_datetime': '2026-08-03T10:00',
    }
    base.update(kw)
    return base


def test_correct_requires_admin(client, monkeypatch):
    # Non-admin is rejected before any repo work.
    monkeypatch.setattr(contracts_mod, '_is_admin', lambda: False)
    resp = client.put('/api/foi-parcurs/contracts/1/correct', json={'km_end': 1300})
    assert resp.status_code == 403


def test_correct_404_when_missing(client, as_admin, monkeypatch):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: None)
    resp = client.put('/api/foi-parcurs/contracts/9/correct', json={'km_end': 1300})
    assert resp.status_code == 404


def test_correct_requires_at_least_one_field(client, as_admin, monkeypatch):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: _contract())
    resp = client.put('/api/foi-parcurs/contracts/1/correct', json={})
    assert resp.status_code == 400


def test_correct_rejects_km_end_below_km_start(client, as_admin, monkeypatch):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: _contract(km_start=1236))
    resp = client.put('/api/foi-parcurs/contracts/1/correct', json={'km_start': 1236, 'km_end': 900})
    assert resp.status_code == 400
    assert 'km_end' in resp.get_json()['error']


def test_correct_rejects_km_end_below_existing_start(client, as_admin, monkeypatch):
    # Only km_end supplied → validated against the existing km_start.
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: _contract(km_start=1236))
    resp = client.put('/api/foi-parcurs/contracts/1/correct', json={'km_end': 1000})
    assert resp.status_code == 400


def test_correct_rejects_non_numeric_km(client, as_admin, monkeypatch):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: _contract())
    resp = client.put('/api/foi-parcurs/contracts/1/correct', json={'km_end': 'abc'})
    assert resp.status_code == 400


def test_correct_rejects_unparseable_date(client, as_admin, monkeypatch):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: _contract())
    resp = client.put('/api/foi-parcurs/contracts/1/correct', json={'departure_datetime': 'not-a-date'})
    assert resp.status_code == 400


def test_correct_rejects_return_before_departure(client, as_admin, monkeypatch):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: _contract())
    resp = client.put('/api/foi-parcurs/contracts/1/correct',
                      json={'departure_datetime': '2026-08-05T10:00',
                            'return_datetime': '2026-08-05T09:00'})
    assert resp.status_code == 400
    assert 'return' in resp.get_json()['error'].lower()


def test_correct_tolerates_tzaware_stored_dates(client, as_admin, monkeypatch):
    # REGRESSION: stored departure/return come back tz-AWARE from the DB; a
    # km-only correction still runs the date-order check against them and must
    # not raise TypeError → 500 when compared to a naive submitted value.
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id',
                        lambda id: _contract(departure_datetime='2026-08-03T09:00:00+03:00',
                                             return_datetime='2026-08-03T10:00:00+03:00'))
    monkeypatch.setattr(contracts_mod._fp_repo, 'correct_session',
                        lambda cid, fields, modified_by=None: _contract())
    # naive submitted departure vs tz-aware stored return — must compare cleanly.
    resp = client.put('/api/foi-parcurs/contracts/1/correct',
                      json={'departure_datetime': '2026-08-03T08:00'})
    assert resp.status_code == 200


def test_correct_km_happy_path(client, as_admin, monkeypatch):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: _contract())
    captured = {}

    def fake_correct(cid, fields, modified_by=None):
        captured['cid'] = cid
        captured['fields'] = dict(fields)
        captured['by'] = modified_by
        return _contract(km_start=1258, km_end=1300)

    monkeypatch.setattr(contracts_mod._fp_repo, 'correct_session', fake_correct)
    monkeypatch.setattr(contracts_mod._vehicle_repo, 'get_by_vin', lambda vin: {'id': 7, 'odometer_km': 1000})
    updated_veh = {}
    monkeypatch.setattr(contracts_mod._vehicle_repo, 'update', lambda vid, data: updated_veh.update({vid: data}))

    resp = client.put('/api/foi-parcurs/contracts/1/correct', json={'km_start': 1258, 'km_end': 1300})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert captured['cid'] == 1
    assert captured['fields'] == {'km_start': 1258, 'km_end': 1300}
    # km_end (1300) raised above the vehicle odometer (1000) → floor advanced.
    assert updated_veh == {7: {'odometer_km': 1300}}


def test_correct_dates_happy_path(client, as_admin, monkeypatch):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: _contract())
    captured = {}
    monkeypatch.setattr(contracts_mod._fp_repo, 'correct_session',
                        lambda cid, fields, modified_by=None: captured.update(fields) or _contract())
    resp = client.put('/api/foi-parcurs/contracts/1/correct',
                      json={'departure_datetime': '2026-08-06T09:00',
                            'return_datetime': '2026-08-06T11:00'})
    assert resp.status_code == 200
    assert captured == {'departure_datetime': '2026-08-06T09:00',
                        'return_datetime': '2026-08-06T11:00'}
