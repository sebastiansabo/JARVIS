# jarvis/tests/carpark/test_autovit_routes_freshness.py
"""Task 3 of the Autovit publishing-panel plan: the per-vehicle status routes
(GET .../status and POST .../verify-status) must attach a `freshness` field
to each serialized listing, computed by compute_autovit_freshness (Task 2)
from the listing's `status`/`last_published_at` and the vehicle's
`updated_at`. Before this, the routes returned the raw listing rows with no
freshness signal — the UI had no way to tell a still-live 'active' advert
from one that's gone stale because the vehicle was edited after the last
publish.

Mirrors the app-client + auth-bypass setup in test_autovit_routes_auth.py;
mocks the module-level `_listing_repo`/`_vehicle_repo` (and ownership check)
instead of touching a real DB.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

import core.utils.api_helpers as api_helpers
import carpark.routes.vehicles as vehicles_mod
from carpark.connectors.autovit import autovit_bp
import carpark.connectors.autovit.routes as routes_mod


class CarparkUser:
    is_authenticated = True
    id = 1
    name = 'Mgr'
    company_id = 10
    can_access_carpark = True
    can_edit_carpark = True
    can_view_carpark_finance = True
    can_access_settings = True


def _set_user(monkeypatch, user):
    # api_login_required (GET status) reads current_user from api_helpers;
    # carpark_required/carpark_edit_required read it from the vehicles
    # module. POST verify-status's own @login_required is bypassed via
    # LOGIN_DISABLED instead (mirrors test_autovit_push.py).
    monkeypatch.setattr(api_helpers, 'current_user', user)
    monkeypatch.setattr(vehicles_mod, 'current_user', user)


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(autovit_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def authenticated_user(monkeypatch):
    _set_user(monkeypatch, CarparkUser())


@pytest.fixture(autouse=True)
def bypass_ownership(monkeypatch):
    """_verify_vehicle_ownership normally fetches the vehicle via
    VehicleService (real DB); stub it to the exists-only shape the routes
    need so these tests stay DB-free."""
    monkeypatch.setattr(routes_mod, '_verify_vehicle_ownership',
                        lambda vid: ({'id': vid}, None))


_NOW = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
_PUBLISHED_AT = _NOW - timedelta(days=2)


def _active_listing(**overrides):
    listing = {
        'id': 1, 'vehicle_id': 7, 'account_id': 1,
        'external_advert_id': 'A1', 'external_url': 'http://autovit/A1',
        'status': 'active', 'last_error': None,
        'last_published_at': _PUBLISHED_AT,
    }
    listing.update(overrides)
    return listing


def test_status_route_includes_freshness_stale(client, monkeypatch):
    """Vehicle edited (updated_at) AFTER the last publish → the live advert
    no longer reflects the current data: 'stale'."""
    monkeypatch.setattr(routes_mod._listing_repo, 'list_by_vehicle',
                        lambda vid: [_active_listing()])
    monkeypatch.setattr(routes_mod._vehicle_repo, 'get_by_id',
                        lambda vid: {'id': vid, 'updated_at': _PUBLISHED_AT + timedelta(days=1)})

    resp = client.get('/autovit/api/vehicles/7/status')

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['listings'][0]['freshness'] == 'stale'


def test_status_route_includes_freshness_up_to_date(client, monkeypatch):
    """Vehicle's last edit is OLDER than the last publish → the live advert
    still matches: 'up_to_date'."""
    monkeypatch.setattr(routes_mod._listing_repo, 'list_by_vehicle',
                        lambda vid: [_active_listing()])
    monkeypatch.setattr(routes_mod._vehicle_repo, 'get_by_id',
                        lambda vid: {'id': vid, 'updated_at': _PUBLISHED_AT - timedelta(days=1)})

    resp = client.get('/autovit/api/vehicles/7/status')

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['listings'][0]['freshness'] == 'up_to_date'


def test_verify_status_route_includes_freshness_and_does_not_stamp_published_at(client, monkeypatch):
    """The verify-status route's returned listings must carry freshness too,
    and the live-status refresh it performs along the way must NOT stamp
    last_published_at (only the publish path does)."""
    listing = _active_listing()
    monkeypatch.setattr(routes_mod._listing_repo, 'list_by_vehicle', lambda vid: [listing])
    monkeypatch.setattr(routes_mod._vehicle_repo, 'get_by_id',
                        lambda vid: {'id': vid, 'updated_at': _PUBLISHED_AT + timedelta(days=1)})
    monkeypatch.setattr(routes_mod._repo, 'get',
                        lambda aid: {'id': aid, 'connector_type': 'autovit'})

    class _FakeClient:
        timeout = 10
        def get_account_advert(self, advert_id, timeout=None):
            return {'status': 'active', 'url': 'http://autovit/A1'}

    monkeypatch.setattr(routes_mod, '_build_client', lambda conn: _FakeClient())

    recorded = {}

    def _fake_upsert(vehicle_id, account_id, **fields):
        recorded.update(fields)
        return {}

    monkeypatch.setattr(routes_mod._listing_repo, 'upsert', _fake_upsert)

    resp = client.post('/autovit/api/vehicles/7/verify-status', json={})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['refreshed'] == 1
    # The refresh writes status/external_url/last_error but must never stamp
    # last_published_at — that's the publish path's job only.
    assert 'last_published_at' not in recorded
    assert data['listings'][0]['freshness'] == 'stale'
