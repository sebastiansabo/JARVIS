"""Tests for the admin drive-type reclassification endpoint:
PUT /api/foi-parcurs/contracts/<id>/drive-type — flips a session between internal
(company driving) and external (client), fixing rows a colleague mis-marked.
Flag-only: client identity is preserved so it's reversible.

Gated by the role matrix permission `test_drive.contracts.drive_type` via
@v2_permission_required (admins bypass). Tested with a FakeUser + request_loader,
mirroring jarvis/tests/happy/test_admin_permissions.py — the reliable way to
exercise the decorator (the older _is_admin-monkeypatch style does NOT).
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask
from flask_login import LoginManager, UserMixin

from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.contracts as contracts_mod


class FakeUser(UserMixin):
    def __init__(self, uid, role_id=None, is_admin=False, can_access_settings=False):
        self.id = uid
        self.role_id = role_id
        self.is_admin = is_admin
        self.can_access_settings = can_access_settings


UNPRIV = FakeUser(1)                          # authenticated, no role/bypass -> 403
ADMIN = FakeUser(2, is_admin=True)            # admin bypass in the decorator
GRANTED = FakeUser(3, role_id=5)              # role granted via matrix -> allowed


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
        return {'admin': ADMIN, 'unpriv': UNPRIV, 'granted': GRANTED}.get(req.headers.get('X-Test-User'))

    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    return app.test_client()


def _hdr(kind):
    return {'X-Test-User': kind}


def _contract(**kw):
    base = {'id': 1, 'route_type': 'TD', 'status': 'COMPLETED', 'vin': 'VIN1', 'is_internal': False}
    base.update(kw)
    return base


def test_drive_type_requires_authentication(client):
    # No user loaded -> decorator returns 401 before any work.
    resp = client.put('/api/foi-parcurs/contracts/1/drive-type', json={'is_internal': True})
    assert resp.status_code == 401


def test_drive_type_denied_without_permission(client):
    # Authenticated but no role/permission -> 403.
    resp = client.put('/api/foi-parcurs/contracts/1/drive-type', json={'is_internal': True}, headers=_hdr('unpriv'))
    assert resp.status_code == 403


def test_drive_type_404_when_missing(client, monkeypatch):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: None)
    resp = client.put('/api/foi-parcurs/contracts/9/drive-type', json={'is_internal': True}, headers=_hdr('admin'))
    assert resp.status_code == 404


def test_drive_type_requires_is_internal(client, monkeypatch):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: _contract())
    resp = client.put('/api/foi-parcurs/contracts/1/drive-type', json={}, headers=_hdr('admin'))
    assert resp.status_code == 400


def test_drive_type_rejects_non_boolean(client, monkeypatch):
    # An integer/string must not slip through — the column is a strict boolean.
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: _contract())
    resp = client.put('/api/foi-parcurs/contracts/1/drive-type', json={'is_internal': 1}, headers=_hdr('admin'))
    assert resp.status_code == 400


def test_mark_internal_happy_path(client, monkeypatch):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: _contract(is_internal=False))
    captured = {}

    def fake_set_flag(cid, is_internal, modified_by=None):
        captured.update({'cid': cid, 'is_internal': is_internal})
        return _contract(is_internal=is_internal)

    logged = {}
    monkeypatch.setattr(contracts_mod._fp_repo, 'set_internal_flag', fake_set_flag)
    monkeypatch.setattr(contracts_mod, 'log_history', lambda sid, action: logged.update({'sid': sid, 'action': action}))

    resp = client.put('/api/foi-parcurs/contracts/1/drive-type', json={'is_internal': True}, headers=_hdr('admin'))
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert body['contract']['is_internal'] is True
    assert captured == {'cid': 1, 'is_internal': True}
    assert logged == {'sid': 1, 'action': 'mark_internal'}


def test_mark_external_happy_path(client, monkeypatch):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: _contract(is_internal=True))
    logged = {}
    monkeypatch.setattr(contracts_mod._fp_repo, 'set_internal_flag',
                        lambda cid, is_internal, modified_by=None: _contract(is_internal=is_internal))
    monkeypatch.setattr(contracts_mod, 'log_history', lambda sid, action: logged.update({'action': action}))

    resp = client.put('/api/foi-parcurs/contracts/1/drive-type', json={'is_internal': False}, headers=_hdr('admin'))
    assert resp.status_code == 200
    assert resp.get_json()['contract']['is_internal'] is False
    assert logged == {'action': 'mark_external'}


def test_drive_type_allowed_for_granted_role(client, monkeypatch):
    # A non-admin role granted test_drive.contracts.drive_type in the matrix passes.
    from core.roles.repositories import PermissionRepository
    monkeypatch.setattr(PermissionRepository, 'check_permission_v2',
                        lambda self, role_id, m, e, a: {'has_permission': True, 'scope': 'all'})
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda id: _contract())
    monkeypatch.setattr(contracts_mod._fp_repo, 'set_internal_flag',
                        lambda cid, is_internal, modified_by=None: _contract(is_internal=is_internal))
    monkeypatch.setattr(contracts_mod, 'log_history', lambda sid, action: None)

    resp = client.put('/api/foi-parcurs/contracts/1/drive-type', json={'is_internal': True}, headers=_hdr('granted'))
    assert resp.status_code == 200
