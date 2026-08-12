"""Tests for the advisor extend-return endpoint:
PUT /api/foi-parcurs/test-drive/<id>/extend — pushes an OPEN (FILLED) test
drive's return time. Any logged-in user; status/km unchanged.

Flask test client against a minimal app registering foi_parcurs_bp, with the
repo mocked at module level (mirrors test_test_drive_return.py).
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.test_drive as td_mod


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


def _open_td(**kw):
    base = {'id': 1, 'route_type': 'TD', 'status': 'FILLED',
            'departure_datetime': '2026-08-11T10:00', 'return_datetime': '2026-08-11T18:00'}
    base.update(kw)
    return base


def test_extend_requires_return_datetime(client, monkeypatch):
    monkeypatch.setattr(td_mod._fp_repo, 'get_contract_by_id', lambda id: _open_td())
    resp = client.put('/api/foi-parcurs/test-drive/1/extend', json={})
    assert resp.status_code == 400


def test_extend_404_when_missing(client, monkeypatch):
    monkeypatch.setattr(td_mod._fp_repo, 'get_contract_by_id', lambda id: None)
    resp = client.put('/api/foi-parcurs/test-drive/9/extend', json={'return_datetime': '2026-08-15T18:00'})
    assert resp.status_code == 404


def test_extend_rejects_completed_session(client, monkeypatch):
    monkeypatch.setattr(td_mod._fp_repo, 'get_contract_by_id', lambda id: _open_td(status='COMPLETED'))
    resp = client.put('/api/foi-parcurs/test-drive/1/extend', json={'return_datetime': '2026-08-15T18:00'})
    assert resp.status_code == 409


def test_extend_rejects_planned_session(client, monkeypatch):
    monkeypatch.setattr(td_mod._fp_repo, 'get_contract_by_id', lambda id: _open_td(status='PLANNED'))
    resp = client.put('/api/foi-parcurs/test-drive/1/extend', json={'return_datetime': '2026-08-15T18:00'})
    assert resp.status_code == 409


def test_extend_rejects_non_td(client, monkeypatch):
    monkeypatch.setattr(td_mod._fp_repo, 'get_contract_by_id', lambda id: _open_td(route_type='Comodat'))
    resp = client.put('/api/foi-parcurs/test-drive/1/extend', json={'return_datetime': '2026-08-15T18:00'})
    assert resp.status_code == 409


def test_extend_rejects_return_before_departure(client, monkeypatch):
    monkeypatch.setattr(td_mod._fp_repo, 'get_contract_by_id', lambda id: _open_td())
    resp = client.put('/api/foi-parcurs/test-drive/1/extend', json={'return_datetime': '2026-08-11T09:00'})
    assert resp.status_code == 400


def test_extend_rejects_invalid_date(client, monkeypatch):
    monkeypatch.setattr(td_mod._fp_repo, 'get_contract_by_id', lambda id: _open_td())
    resp = client.put('/api/foi-parcurs/test-drive/1/extend', json={'return_datetime': 'nope'})
    assert resp.status_code == 400


def test_extend_happy_path_records_who(client, monkeypatch):
    monkeypatch.setattr(td_mod._fp_repo, 'get_contract_by_id', lambda id: _open_td())
    captured = {}

    def fake_extend(cid, return_datetime, modified_by=None):
        captured.update(id=cid, ret=return_datetime, by=modified_by)
        return _open_td(return_datetime=return_datetime)

    monkeypatch.setattr(td_mod._fp_repo, 'extend_return', fake_extend)
    resp = client.put('/api/foi-parcurs/test-drive/1/extend', json={'return_datetime': '2026-08-21T11:06'})
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True
    assert captured['id'] == 1
    assert captured['ret'] == '2026-08-21T11:06'
    # modified_by is threaded (None under LOGIN_DISABLED anonymous user, but passed).
    assert 'by' in captured


def test_extend_tolerates_tzaware_departure_from_db(client, monkeypatch):
    # REGRESSION: dict_from_row returns departure_datetime as a tz-AWARE ISO
    # string (…+00:00), while the submitted return is a naive datetime-local
    # value. A direct compare raises TypeError → 500. Must normalize + succeed.
    monkeypatch.setattr(td_mod._fp_repo, 'get_contract_by_id',
                        lambda id: _open_td(departure_datetime='2026-08-11T10:00:00+00:00'))
    monkeypatch.setattr(td_mod._fp_repo, 'extend_return',
                        lambda cid, r, modified_by=None: _open_td(return_datetime=r))
    resp = client.put('/api/foi-parcurs/test-drive/1/extend', json={'return_datetime': '2026-08-21T11:06'})
    assert resp.status_code == 200


def test_extend_rejects_return_before_tzaware_departure(client, monkeypatch):
    monkeypatch.setattr(td_mod._fp_repo, 'get_contract_by_id',
                        lambda id: _open_td(departure_datetime='2026-08-11T10:00:00+00:00'))
    resp = client.put('/api/foi-parcurs/test-drive/1/extend', json={'return_datetime': '2026-08-11T09:00'})
    assert resp.status_code == 400


def test_list_columns_includes_modified_marker():
    # The badge reads corrected_at/corrected_by, but the list endpoint projects
    # _LIST_COLUMNS (lean=True) — the columns must be in that allowlist or the
    # "Modificat" badge can never render.
    from foi_parcurs.repositories import foi_parcurs_repository as repo_mod
    assert 'fp.corrected_at' in repo_mod._LIST_COLUMNS
    assert 'fp.corrected_by' in repo_mod._LIST_COLUMNS


def test_extend_409_when_repo_reports_not_extendable(client, monkeypatch):
    # Repo guard (status changed under us) → None → 409.
    monkeypatch.setattr(td_mod._fp_repo, 'get_contract_by_id', lambda id: _open_td())
    monkeypatch.setattr(td_mod._fp_repo, 'extend_return', lambda cid, r, modified_by=None: None)
    resp = client.put('/api/foi-parcurs/test-drive/1/extend', json={'return_datetime': '2026-08-21T11:06'})
    assert resp.status_code == 409
