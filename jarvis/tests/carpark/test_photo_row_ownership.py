"""Tenant-scoping tests for the single-row photo endpoints
(`PUT /photos/<photo_id>`, `DELETE /photos/<photo_id>` in
carpark/routes/photos.py). These routes are keyed by photo_id and used to
resolve the photo's vehicle before acting, so a guessed photo_id could
mutate/delete another company's photo — this verifies the ownership scope
closes that cross-tenant IDOR.

Uses the real Flask app (mirrors test_photo_upload.py / test_acting_company.py):
the top-level conftest.py mocks psycopg2 before `app` is imported, and we
patch `app._user_repo.get_by_id` per-test so session login carries the right
company_id + carpark flags. Each test uses a unique uid to dodge the 60s
user_loader cache.
"""
import os
from unittest import mock

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest

import app as app_module
from app import app as flask_app
from carpark.routes import photos as photos_module
from carpark.routes import vehicles as vehicles_module


@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    return flask_app.test_client()


def _login(client, monkeypatch, uid, company_id=1, **perm_overrides):
    user = {'id': uid, 'email': f't{uid}@x.com', 'name': 'T', 'company_id': company_id,
            'can_access_carpark': True, 'can_edit_carpark': True, 'can_delete_carpark': True}
    user.update(perm_overrides)
    monkeypatch.setattr(app_module._user_repo, 'get_by_id', lambda _u: user)
    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)


# ── UPDATE (PUT /photos/<id>) ────────────────────────────────────────────

def test_update_photo_cross_tenant_blocked_404(client, monkeypatch):
    """A photo whose vehicle is in a company OUTSIDE the caller's actable set
    404s, and the repo update is never called."""
    _login(client, monkeypatch, uid=97101, company_id=1)
    monkeypatch.setattr(vehicles_module, 'get_actable_company_ids', lambda _u: {1})
    monkeypatch.setattr(photos_module._photo_repo, 'get_by_id',
                        lambda pid: {'id': pid, 'vehicle_id': 42})
    monkeypatch.setattr(vehicles_module._vehicle_service, 'get_vehicle',
                        lambda vid: {'id': vid, 'company_id': 999})
    updated = []
    monkeypatch.setattr(photos_module._photo_repo, 'update',
                        lambda pid, data: updated.append(pid))
    r = client.put('/api/carpark/photos/5', json={'caption': 'x'})
    assert r.status_code == 404
    assert updated == []


def test_update_photo_own_company_allowed(client, monkeypatch):
    """A photo on the caller's own-company vehicle updates normally."""
    _login(client, monkeypatch, uid=97102, company_id=1)
    monkeypatch.setattr(photos_module._photo_repo, 'get_by_id',
                        lambda pid: {'id': pid, 'vehicle_id': 42})
    monkeypatch.setattr(vehicles_module._vehicle_service, 'get_vehicle',
                        lambda vid: {'id': vid, 'company_id': 1})
    monkeypatch.setattr(photos_module._photo_repo, 'update',
                        lambda pid, data: {'id': pid, 'caption': data.get('caption')})
    r = client.put('/api/carpark/photos/5', json={'caption': 'x'})
    assert r.status_code == 200
    assert r.get_json()['photo']['caption'] == 'x'


def test_update_photo_unknown_returns_404(client, monkeypatch):
    _login(client, monkeypatch, uid=97103, company_id=1)
    monkeypatch.setattr(photos_module._photo_repo, 'get_by_id', lambda pid: None)
    r = client.put('/api/carpark/photos/999', json={'caption': 'x'})
    assert r.status_code == 404


# ── DELETE (DELETE /photos/<id>) ─────────────────────────────────────────

def test_delete_photo_cross_tenant_blocked_404(client, monkeypatch):
    """A photo whose vehicle is in a company OUTSIDE the caller's actable set
    404s, and soft_delete is never called."""
    _login(client, monkeypatch, uid=97104, company_id=1)
    monkeypatch.setattr(vehicles_module, 'get_actable_company_ids', lambda _u: {1})
    monkeypatch.setattr(photos_module._photo_repo, 'get_by_id',
                        lambda pid: {'id': pid, 'vehicle_id': 42})
    monkeypatch.setattr(vehicles_module._vehicle_service, 'get_vehicle',
                        lambda vid: {'id': vid, 'company_id': 999})
    deleted = []
    monkeypatch.setattr(photos_module._photo_repo, 'soft_delete',
                        lambda ids: deleted.append(ids) or len(ids))
    r = client.delete('/api/carpark/photos/5')
    assert r.status_code == 404
    assert deleted == []


def test_delete_photo_own_company_allowed(client, monkeypatch):
    """A photo on the caller's own-company vehicle soft-deletes normally."""
    _login(client, monkeypatch, uid=97105, company_id=1)
    monkeypatch.setattr(photos_module._photo_repo, 'get_by_id',
                        lambda pid: {'id': pid, 'vehicle_id': 42})
    monkeypatch.setattr(vehicles_module._vehicle_service, 'get_vehicle',
                        lambda vid: {'id': vid, 'company_id': 1})
    deleted = []
    monkeypatch.setattr(photos_module._photo_repo, 'soft_delete',
                        lambda ids: deleted.append(ids) or len(ids))
    r = client.delete('/api/carpark/photos/5')
    assert r.status_code == 200
    assert deleted == [[5]]
