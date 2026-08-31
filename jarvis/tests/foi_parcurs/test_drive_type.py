"""Tests for the admin drive-type reclassification endpoint:
PUT /api/foi-parcurs/contracts/<id>/drive-type — lets an admin flip a session
between internal (company driving) and external (client), fixing rows a
colleague mis-marked. Flag-only: client identity is preserved so it's reversible.

Flask test client against a minimal app registering foi_parcurs_bp, with the
repo + admin gate mocked at module level (mirrors test_correct_session.py).
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
    base = {'id': 1, 'route_type': 'TD', 'status': 'COMPLETED', 'vin': 'VIN1',
            'is_internal': False}
    base.update(kw)
    return base


def test_drive_type_requires_admin(client, monkeypatch):
    # Non-admin is rejected before any repo work.
    monkeypatch.setattr(contracts_mod, '_is_admin', lambda: False)
    resp = client.put('/api/foi-parcurs/contracts/1/drive-type', json={'is_internal': True})
    assert resp.status_code == 403


def test_drive_type_404_when_missing(client, as_admin, monkeypatch):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: None)
    resp = client.put('/api/foi-parcurs/contracts/9/drive-type', json={'is_internal': True})
    assert resp.status_code == 404


def test_drive_type_requires_is_internal(client, as_admin, monkeypatch):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: _contract())
    resp = client.put('/api/foi-parcurs/contracts/1/drive-type', json={})
    assert resp.status_code == 400


def test_drive_type_rejects_non_boolean(client, as_admin, monkeypatch):
    # An integer/string must not slip through — the column is a strict boolean.
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: _contract())
    resp = client.put('/api/foi-parcurs/contracts/1/drive-type', json={'is_internal': 1})
    assert resp.status_code == 400


def test_mark_internal_happy_path(client, as_admin, monkeypatch):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: _contract(is_internal=False))
    captured = {}

    def fake_set_flag(cid, is_internal, modified_by=None):
        captured['cid'] = cid
        captured['is_internal'] = is_internal
        captured['by'] = modified_by
        return _contract(is_internal=is_internal)

    logged = {}
    monkeypatch.setattr(contracts_mod._fp_repo, 'set_internal_flag', fake_set_flag)
    monkeypatch.setattr(contracts_mod, 'log_history', lambda sid, action: logged.update({'sid': sid, 'action': action}))

    resp = client.put('/api/foi-parcurs/contracts/1/drive-type', json={'is_internal': True})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert body['contract']['is_internal'] is True
    assert captured == {'cid': 1, 'is_internal': True, 'by': None}
    assert logged == {'sid': 1, 'action': 'mark_internal'}


def test_mark_external_happy_path(client, as_admin, monkeypatch):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: _contract(is_internal=True))
    logged = {}
    monkeypatch.setattr(contracts_mod._fp_repo, 'set_internal_flag',
                        lambda cid, is_internal, modified_by=None: _contract(is_internal=is_internal))
    monkeypatch.setattr(contracts_mod, 'log_history', lambda sid, action: logged.update({'action': action}))

    resp = client.put('/api/foi-parcurs/contracts/1/drive-type', json={'is_internal': False})
    assert resp.status_code == 200
    assert resp.get_json()['contract']['is_internal'] is False
    assert logged == {'action': 'mark_external'}
