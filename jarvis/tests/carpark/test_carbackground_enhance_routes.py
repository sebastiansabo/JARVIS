# jarvis/tests/carpark/test_carbackground_enhance_routes.py
"""CarBackground enhance/publish/delete route tests.

These three routes stack `@login_required` + `@carpark_edit_required`
(mirroring carpark/routes/photos.py exactly). `carpark_edit_required` reads
`current_user` from its *own* defining module (carpark.routes.vehicles) at
call time, same as test_carbackground_routes.py / test_autovit_routes_auth.py
rely on. `login_required` is flask_login's real decorator: its closure reads
`current_user` from `flask_login.utils`'s own globals (a LocalProxy that -
absent a real LoginManager on the app - would AttributeError on
`current_app.login_manager`). So the auth-stub here additionally monkeypatches
`flask_login.utils.current_user` to a fake authenticated user; that is enough
to satisfy `login_required` without standing up the real app.py/LoginManager
machinery (confirmed empirically: unpatched -> 500 AttributeError, patched ->
200). This keeps the test lightweight like Task 5's, rather than switching to
the heavyweight real-session approach used in test_photo_upload.py.

`_verify_vehicle_ownership` (imported into the routes module, same as
carpark.routes.photos._verify_vehicle_ownership in test_photo_upload.py) is
monkeypatched per-test to avoid hitting a real DB.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask
import flask_login.utils as flu

import carpark.routes.vehicles as vehicles_mod
from carpark.connectors.carbackground import carbackground_bp
from carpark.connectors.carbackground.service import CarBackgroundError
import carpark.connectors.carbackground.routes as routes_mod


class EditUser:
    is_authenticated = True
    id = 1
    can_access_carpark = True
    can_edit_carpark = True


class NoEditUser:
    # CarPark access but not edit: must not enhance/publish/delete.
    is_authenticated = True
    id = 2
    can_access_carpark = True
    can_edit_carpark = False


def _set_user(monkeypatch, user):
    monkeypatch.setattr(flu, 'current_user', user)
    monkeypatch.setattr(vehicles_mod, 'current_user', user)


def _own_vehicle(monkeypatch, vid=9):
    # Bypass the real DB-backed VehicleService._verify_vehicle_ownership lookup.
    monkeypatch.setattr(routes_mod, '_verify_vehicle_ownership',
                        lambda v: ({'id': v}, None))


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(carbackground_bp)
    app.config['TESTING'] = True
    return app.test_client()


# ── auth gating ──

def test_enhance_forbidden_without_edit(client, monkeypatch):
    _set_user(monkeypatch, NoEditUser())
    r = client.post('/carbackground/api/vehicles/9/enhance', json={'photo_ids': [1]})
    assert r.status_code == 403


def test_publish_forbidden_without_edit(client, monkeypatch):
    _set_user(monkeypatch, NoEditUser())
    r = client.put('/carbackground/api/photos/1/publish', json={'published': True})
    assert r.status_code == 403


def test_delete_enhanced_forbidden_without_edit(client, monkeypatch):
    _set_user(monkeypatch, NoEditUser())
    r = client.delete('/carbackground/api/photos/1/enhanced')
    assert r.status_code == 403


# ── POST /api/vehicles/<vid>/enhance ──

def test_enhance_requires_photo_ids(client, monkeypatch):
    _set_user(monkeypatch, EditUser())
    _own_vehicle(monkeypatch, 9)
    r = client.post('/carbackground/api/vehicles/9/enhance', json={'photo_ids': []})
    assert r.status_code == 400


def test_enhance_vehicle_not_found_propagates_404(client, monkeypatch):
    _set_user(monkeypatch, EditUser())
    monkeypatch.setattr(routes_mod, '_verify_vehicle_ownership',
                        lambda v: (None, (routes_mod.jsonify(
                            {'success': False, 'error': 'Vehicle not found'}), 404)))
    r = client.post('/carbackground/api/vehicles/9/enhance', json={'photo_ids': [1]})
    assert r.status_code == 404


def test_enhance_skips_photo_ids_whose_vehicle_id_differs(client, monkeypatch):
    _set_user(monkeypatch, EditUser())
    _own_vehicle(monkeypatch, 9)
    monkeypatch.setattr(routes_mod, '_photos', _FakePhotos({
        1: {'id': 1, 'vehicle_id': 9},
        2: {'id': 2, 'vehicle_id': 777},  # belongs to a different vehicle
    }))
    monkeypatch.setattr(routes_mod, '_service', _FakeService(results=[{'id': 1}]))
    monkeypatch.setattr(routes_mod._repo, 'get_by_type', lambda t: None)

    r = client.post('/carbackground/api/vehicles/9/enhance', json={'photo_ids': [1, 2]})
    body = r.get_json()
    assert r.status_code == 200
    assert body['created'] == 1
    assert len(body['errors']) == 1
    assert 'not found for vehicle 9' in body['errors'][0]
    assert routes_mod._service.calls == [1]  # pid 2 was never attempted


def test_enhance_reports_partial_on_out_of_credits(client, monkeypatch):
    """Review Focus: a 402 mid-batch must not abort the whole request — the
    route returns 200 with whatever succeeded plus the per-photo errors."""
    _set_user(monkeypatch, EditUser())
    _own_vehicle(monkeypatch, 9)
    monkeypatch.setattr(routes_mod, '_photos', _FakePhotos({
        1: {'id': 1, 'vehicle_id': 9},
        2: {'id': 2, 'vehicle_id': 9},
    }))
    monkeypatch.setattr(routes_mod, '_service',
                        _FakeService(results=[{'id': 1}, CarBackgroundError('out of credits', 402)]))
    logged = {}
    monkeypatch.setattr(routes_mod._repo, 'get_by_type', lambda t: {'id': 7})
    monkeypatch.setattr(routes_mod._repo, 'add_sync_log',
                        lambda *a, **kw: logged.update(kw) or 1)

    r = client.post('/carbackground/api/vehicles/9/enhance', json={'photo_ids': [1, 2]})
    body = r.get_json()
    assert r.status_code == 200
    assert body['created'] == 1
    assert len(body['errors']) == 1
    assert '402' in body['errors'][0] and 'out of credits' in body['errors'][0]
    # sync log recorded as a partial failure, not silently dropped
    assert logged['details']['created'] == 1
    assert logged['details']['errors'] == body['errors']


def test_enhance_unexpected_exception_is_caught_not_500(client, monkeypatch):
    _set_user(monkeypatch, EditUser())
    _own_vehicle(monkeypatch, 9)
    monkeypatch.setattr(routes_mod, '_photos', _FakePhotos({1: {'id': 1, 'vehicle_id': 9}}))
    monkeypatch.setattr(routes_mod, '_service', _FakeService(results=[RuntimeError('boom')]))
    monkeypatch.setattr(routes_mod._repo, 'get_by_type', lambda t: None)

    r = client.post('/carbackground/api/vehicles/9/enhance', json={'photo_ids': [1]})
    body = r.get_json()
    assert r.status_code == 200
    assert body['created'] == 0
    assert 'boom' in body['errors'][0]


# ── PUT /api/photos/<pid>/publish ──

def test_publish_404_when_photo_missing(client, monkeypatch):
    _set_user(monkeypatch, EditUser())
    monkeypatch.setattr(routes_mod._photos, 'get_by_id', lambda pid: None)
    r = client.put('/carbackground/api/photos/1/publish', json={'published': True})
    assert r.status_code == 404


def test_publish_400_without_enhanced_variant(client, monkeypatch):
    _set_user(monkeypatch, EditUser())
    monkeypatch.setattr(routes_mod._photos, 'get_by_id',
                        lambda pid: {'id': pid, 'enhanced_url': None})
    r = client.put('/carbackground/api/photos/1/publish', json={'published': True})
    assert r.status_code == 400


def test_publish_true_succeeds_when_enhanced_variant_exists(client, monkeypatch):
    _set_user(monkeypatch, EditUser())
    monkeypatch.setattr(routes_mod._photos, 'get_by_id',
                        lambda pid: {'id': pid, 'enhanced_url': 'private/x.jpg'})
    monkeypatch.setattr(routes_mod._photos, 'set_enhanced_published',
                        lambda pid, published: {'id': pid, 'enhanced_published': published})
    r = client.put('/carbackground/api/photos/1/publish', json={'published': True})
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is True
    assert body['photo']['enhanced_published'] is True


def test_publish_false_allowed_even_without_enhanced_variant(client, monkeypatch):
    # Un-publishing should always be allowed (only turning ON requires a variant).
    _set_user(monkeypatch, EditUser())
    monkeypatch.setattr(routes_mod._photos, 'get_by_id',
                        lambda pid: {'id': pid, 'enhanced_url': None})
    monkeypatch.setattr(routes_mod._photos, 'set_enhanced_published',
                        lambda pid, published: {'id': pid, 'enhanced_published': published})
    r = client.put('/carbackground/api/photos/1/publish', json={'published': False})
    assert r.status_code == 200


# ── DELETE /api/photos/<pid>/enhanced ──

def test_delete_enhanced_404_when_photo_missing(client, monkeypatch):
    _set_user(monkeypatch, EditUser())
    monkeypatch.setattr(routes_mod._photos, 'get_by_id', lambda pid: None)
    r = client.delete('/carbackground/api/photos/1/enhanced')
    assert r.status_code == 404


def test_delete_enhanced_clears_variant_and_deletes_spaces_objects(client, monkeypatch):
    _set_user(monkeypatch, EditUser())
    monkeypatch.setattr(routes_mod._photos, 'get_by_id', lambda pid: {
        'id': pid, 'enhanced_url': 'private/carpark/9/enhanced_abc.jpg',
        'enhanced_thumbnail_url': 'private/carpark/9/enhanced_abc_thumb.jpg',
    })
    cleared = {}
    monkeypatch.setattr(routes_mod._photos, 'clear_enhanced',
                        lambda pid: cleared.update(id=pid, enhanced_url=None) or
                        {'id': pid, 'enhanced_url': None})
    deleted_keys = []
    monkeypatch.setattr(routes_mod.spaces_service, 'delete', lambda key: deleted_keys.append(key))

    r = client.delete('/carbackground/api/photos/1/enhanced')
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is True
    assert body['photo']['enhanced_url'] is None
    assert deleted_keys == [
        'private/carpark/9/enhanced_abc.jpg',
        'private/carpark/9/enhanced_abc_thumb.jpg',
    ]


def test_delete_enhanced_spaces_failure_does_not_block_db_clear(client, monkeypatch):
    # A Spaces delete error must be swallowed (logged), not surfaced as a 500 -
    # the DB row still gets cleared.
    _set_user(monkeypatch, EditUser())
    monkeypatch.setattr(routes_mod._photos, 'get_by_id', lambda pid: {
        'id': pid, 'enhanced_url': 'private/x.jpg', 'enhanced_thumbnail_url': None,
    })
    monkeypatch.setattr(routes_mod._photos, 'clear_enhanced',
                        lambda pid: {'id': pid, 'enhanced_url': None})

    def _boom(key):
        raise RuntimeError('spaces down')

    monkeypatch.setattr(routes_mod.spaces_service, 'delete', _boom)
    r = client.delete('/carbackground/api/photos/1/enhanced')
    assert r.status_code == 200
    assert r.get_json()['photo']['enhanced_url'] is None


# ── test doubles ──

class _FakePhotos:
    """Minimal PhotoRepository stand-in keyed by photo id -> dict."""

    def __init__(self, by_id):
        self._by_id = by_id

    def get_by_id(self, pid):
        return self._by_id.get(pid)


class _FakeService:
    """Minimal CarBackgroundEnhanceService stand-in: `results` is consumed in
    order by successive `enhance_photo` calls — an Exception instance is
    raised instead of returned."""

    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    def enhance_photo(self, pid):
        self.calls.append(pid)
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result
