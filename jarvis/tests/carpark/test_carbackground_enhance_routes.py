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


def test_enhance_non_integer_photo_ids_returns_400_not_500(client, monkeypatch):
    """A non-integer element in photo_ids must be a clean 400, not an
    unguarded int() -> ValueError -> Flask 500 (mirrors reorder_photos)."""
    _set_user(monkeypatch, EditUser())
    _own_vehicle(monkeypatch, 9)
    r = client.post('/carbackground/api/vehicles/9/enhance', json={'photo_ids': [1, 'abc']})
    assert r.status_code == 400
    assert 'integer' in r.get_json()['error'].lower()


def test_enhance_vehicle_not_found_propagates_404(client, monkeypatch):
    _set_user(monkeypatch, EditUser())
    monkeypatch.setattr(routes_mod, '_verify_vehicle_ownership',
                        lambda v: (None, (routes_mod.jsonify(
                            {'success': False, 'error': 'Vehicle not found'}), 404)))
    r = client.post('/carbackground/api/vehicles/9/enhance', json={'photo_ids': [1]})
    assert r.status_code == 404


# The route no longer processes photos inline — it validates, opens a
# 'running' sync-log, spawns a daemon worker, and returns 202. These tests
# cover the route contract; the per-photo processing lives in _run_enhance_job
# and is covered by the worker tests further below.

def test_enhance_returns_202_and_spawns_worker(client, monkeypatch):
    _set_user(monkeypatch, EditUser())
    _own_vehicle(monkeypatch, 9)
    monkeypatch.setattr(routes_mod, '_service', _FakeService(valid_backgrounds={'grey-concrete'}))
    monkeypatch.setattr(routes_mod._repo, 'get_by_type', lambda t: {'id': 7})
    monkeypatch.setattr(routes_mod._repo, 'add_sync_log', lambda *a, **kw: 555)
    threads = _capture_threads(monkeypatch)

    r = client.post('/carbackground/api/vehicles/9/enhance',
                    json={'photo_ids': [1, 2, 3], 'background_id': 'grey-concrete'})
    assert r.status_code == 202
    body = r.get_json()
    assert body['queued'] == 3 and body['job_id'] == 555
    # worker spawned as a daemon with (vid, ids, bg, connector_id, log_id)
    assert len(threads) == 1
    t = threads[0]
    assert t.target is routes_mod._run_enhance_job
    assert t.args == (9, [1, 2, 3], 'grey-concrete', 7, 555)
    assert t.daemon is True and t.started is True


def test_enhance_no_background_spawns_worker_with_none(client, monkeypatch):
    _set_user(monkeypatch, EditUser())
    _own_vehicle(monkeypatch, 9)
    monkeypatch.setattr(routes_mod, '_service', _FakeService())
    monkeypatch.setattr(routes_mod._repo, 'get_by_type', lambda t: {'id': 7})
    monkeypatch.setattr(routes_mod._repo, 'add_sync_log', lambda *a, **kw: 42)
    threads = _capture_threads(monkeypatch)

    r = client.post('/carbackground/api/vehicles/9/enhance', json={'photo_ids': [1]})
    assert r.status_code == 202
    assert threads[0].args == (9, [1], None, 7, 42)


def test_enhance_requires_connector(client, monkeypatch):
    """Without a configured connector there's nowhere to track progress and no
    API key to enhance with — fail fast with a 400, spawn nothing."""
    _set_user(monkeypatch, EditUser())
    _own_vehicle(monkeypatch, 9)
    monkeypatch.setattr(routes_mod, '_service', _FakeService())
    monkeypatch.setattr(routes_mod._repo, 'get_by_type', lambda t: None)
    threads = _capture_threads(monkeypatch)

    r = client.post('/carbackground/api/vehicles/9/enhance', json={'photo_ids': [1]})
    assert r.status_code == 400
    assert 'connector' in r.get_json()['error'].lower()
    assert threads == []


def test_enhance_opens_running_log_before_spawning(client, monkeypatch):
    _set_user(monkeypatch, EditUser())
    _own_vehicle(monkeypatch, 9)
    monkeypatch.setattr(routes_mod, '_service', _FakeService())
    monkeypatch.setattr(routes_mod._repo, 'get_by_type', lambda t: {'id': 7})
    opened = {}
    monkeypatch.setattr(routes_mod._repo, 'add_sync_log',
                        lambda cid, stype, status, **kw: opened.update(
                            cid=cid, stype=stype, status=status, **kw) or 99)
    _capture_threads(monkeypatch)

    client.post('/carbackground/api/vehicles/9/enhance', json={'photo_ids': [1, 2]})
    assert opened['status'] == 'running'
    assert opened['stype'] == 'carbackground_enhance'
    assert opened['invoices_found'] == 2
    assert opened['details']['vehicle_id'] == 9


# ── worker: _run_enhance_job (the per-photo processing, off-request) ──

def test_worker_skips_photo_ids_whose_vehicle_id_differs(monkeypatch):
    monkeypatch.setattr(routes_mod, '_photos', _FakePhotos({
        1: {'id': 1, 'vehicle_id': 9},
        2: {'id': 2, 'vehicle_id': 777},  # different vehicle
    }))
    svc = _FakeService(results=[{'id': 1}])
    monkeypatch.setattr(routes_mod, '_service', svc)
    logs = _capture_logs(monkeypatch)

    routes_mod._run_enhance_job(9, [1, 2], None, 7, 555)
    assert svc.calls == [1]  # pid 2 never attempted
    final = logs[-1]
    assert final['status'] == 'partial'
    assert final['invoices_imported'] == 1
    assert any('not found for vehicle 9' in e for e in final['details']['errors'])


def test_worker_partial_on_out_of_credits(monkeypatch):
    """A 402 mid-batch is recorded per-photo; the job still finishes and the
    log lands as 'partial', never aborting the whole run."""
    monkeypatch.setattr(routes_mod, '_photos', _FakePhotos({
        1: {'id': 1, 'vehicle_id': 9}, 2: {'id': 2, 'vehicle_id': 9},
    }))
    monkeypatch.setattr(routes_mod, '_service',
                        _FakeService(results=[{'id': 1}, CarBackgroundError('out of credits', 402)]))
    logs = _capture_logs(monkeypatch)

    routes_mod._run_enhance_job(9, [1, 2], None, 7, 555)
    final = logs[-1]
    assert final['status'] == 'partial'
    assert final['invoices_imported'] == 1
    assert '402' in final['details']['errors'][0] and 'out of credits' in final['details']['errors'][0]


def test_worker_unexpected_exception_is_caught(monkeypatch):
    monkeypatch.setattr(routes_mod, '_photos', _FakePhotos({1: {'id': 1, 'vehicle_id': 9}}))
    monkeypatch.setattr(routes_mod, '_service', _FakeService(results=[RuntimeError('boom')]))
    logs = _capture_logs(monkeypatch)

    routes_mod._run_enhance_job(9, [1], None, 7, 555)
    final = logs[-1]
    assert final['status'] == 'error'  # nothing succeeded
    assert final['invoices_imported'] == 0
    assert 'boom' in final['details']['errors'][0]


def test_worker_db_error_mid_loop_is_recorded_not_mislabeled_success(monkeypatch):
    """A failure at get_by_id (e.g. a stale pooled connection) must be recorded
    as an error and land the job 'error'/'partial' — never a silent 'success'
    with the remaining photos dropped."""
    class _BoomPhotos:
        def get_by_id(self, pid):
            raise RuntimeError('db down')

    monkeypatch.setattr(routes_mod, '_photos', _BoomPhotos())
    monkeypatch.setattr(routes_mod, '_service', _FakeService())
    logs = _capture_logs(monkeypatch)

    routes_mod._run_enhance_job(9, [1], None, 7, 555)  # must not raise
    final = logs[-1]
    assert final['status'] == 'error'
    assert final['invoices_imported'] == 0
    assert 'db down' in final['details']['errors'][0]


def test_worker_forwards_background_and_reports_live_progress(monkeypatch):
    monkeypatch.setattr(routes_mod, '_photos', _FakePhotos({
        1: {'id': 1, 'vehicle_id': 9}, 2: {'id': 2, 'vehicle_id': 9},
    }))
    svc = _FakeService(results=[{'id': 1}, {'id': 2}],
                       valid_backgrounds={'grey-concrete'})
    monkeypatch.setattr(routes_mod, '_service', svc)
    logs = _capture_logs(monkeypatch)

    routes_mod._run_enhance_job(9, [1, 2], 'grey-concrete', 7, 555)
    assert svc.bg_calls == ['grey-concrete', 'grey-concrete']
    # progress climbs 1 -> 2 before the terminal update, all on log 555
    done_seq = [l['details']['done'] for l in logs]
    assert done_seq == [1, 2, 2]
    assert logs[-1]['status'] == 'success'


# ── GET /api/vehicles/<vid>/enhance/status ──

def test_status_forbidden_without_edit(client, monkeypatch):
    _set_user(monkeypatch, NoEditUser())
    r = client.get('/carbackground/api/vehicles/9/enhance/status')
    assert r.status_code == 403


def test_status_no_connector_reports_idle(client, monkeypatch):
    _set_user(monkeypatch, EditUser())
    _own_vehicle(monkeypatch, 9)
    monkeypatch.setattr(routes_mod._repo, 'get_by_type', lambda t: None)
    r = client.get('/carbackground/api/vehicles/9/enhance/status')
    assert r.status_code == 200
    body = r.get_json()
    assert body['running'] is False and body['total'] == 0 and body['done'] == 0


def test_status_returns_latest_running_job_for_vehicle(client, monkeypatch):
    _set_user(monkeypatch, EditUser())
    _own_vehicle(monkeypatch, 9)
    monkeypatch.setattr(routes_mod._repo, 'get_by_type', lambda t: {'id': 7})
    monkeypatch.setattr(routes_mod._repo, 'get_latest_sync_log', lambda cid, stype, vid: {
        'status': 'running', 'invoices_found': 7, 'invoices_imported': 3,
        'details': {'vehicle_id': 9, 'done': 3, 'requested': 7, 'errors': [],
                    'background_id': 'grey-concrete'}})
    r = client.get('/carbackground/api/vehicles/9/enhance/status')
    body = r.get_json()
    assert body['running'] is True
    assert body['total'] == 7 and body['done'] == 3
    assert body['background_id'] == 'grey-concrete' and body['errors'] == []


def test_status_scopes_lookup_to_this_vehicle(client, monkeypatch):
    """The status is resolved by a vehicle-scoped query (not a fixed window of
    recent connector-wide logs) so a busy fleet can't hide a running job."""
    _set_user(monkeypatch, EditUser())
    _own_vehicle(monkeypatch, 9)
    monkeypatch.setattr(routes_mod._repo, 'get_by_type', lambda t: {'id': 7})
    seen = {}
    monkeypatch.setattr(routes_mod._repo, 'get_latest_sync_log',
                        lambda cid, stype, vid: seen.update(cid=cid, stype=stype, vid=vid) or {
                            'status': 'success', 'invoices_found': 4, 'invoices_imported': 4,
                            'details': {'vehicle_id': 9, 'done': 4, 'errors': []}})
    r = client.get('/carbackground/api/vehicles/9/enhance/status')
    body = r.get_json()
    assert seen == {'cid': 7, 'stype': 'carbackground_enhance', 'vid': 9}
    assert body['running'] is False and body['total'] == 4 and body['done'] == 4


def test_status_no_job_for_vehicle_reports_idle(client, monkeypatch):
    _set_user(monkeypatch, EditUser())
    _own_vehicle(monkeypatch, 9)
    monkeypatch.setattr(routes_mod._repo, 'get_by_type', lambda t: {'id': 7})
    monkeypatch.setattr(routes_mod._repo, 'get_latest_sync_log', lambda cid, stype, vid: None)
    r = client.get('/carbackground/api/vehicles/9/enhance/status')
    body = r.get_json()
    assert body['running'] is False and body['total'] == 0 and body['done'] == 0


def test_enhance_rejects_off_list_background_400(client, monkeypatch):
    """A background_id that isn't preferred fails the whole batch with a 400
    before any photo is enhanced."""
    _set_user(monkeypatch, EditUser())
    _own_vehicle(monkeypatch, 9)
    monkeypatch.setattr(routes_mod, '_photos', _FakePhotos({1: {'id': 1, 'vehicle_id': 9}}))
    svc = _FakeService(results=[{'id': 1}], valid_backgrounds={'grey-concrete'})
    monkeypatch.setattr(routes_mod, '_service', svc)

    r = client.post('/carbackground/api/vehicles/9/enhance',
                    json={'photo_ids': [1], 'background_id': 'alpine-lot'})
    assert r.status_code == 400
    assert svc.calls == []  # nothing enhanced


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

class _FakeThread:
    """Captures threading.Thread(...) args and records .start() without ever
    running the target — so route tests assert what the worker WOULD be called
    with, and the worker is tested directly (not through a real thread)."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self.target = target
        self.args = tuple(args)
        self.kwargs = kwargs or {}
        self.daemon = daemon
        self.started = False

    def start(self):
        self.started = True


def _capture_threads(monkeypatch):
    """Swap routes_mod.threading.Thread for _FakeThread; return the list the
    route appends its spawned thread(s) to."""
    created = []

    def _factory(*a, **kw):
        t = _FakeThread(*a, **kw)
        created.append(t)
        return t

    monkeypatch.setattr(routes_mod.threading, 'Thread', _factory)
    return created


def _capture_logs(monkeypatch):
    """Record every update_sync_log(log_id, **kw) the worker makes, in order."""
    calls = []
    monkeypatch.setattr(routes_mod._repo, 'update_sync_log',
                        lambda log_id, **kw: calls.append({'log_id': log_id, **kw}) or 1)
    return calls


class _FakePhotos:
    """Minimal PhotoRepository stand-in keyed by photo id -> dict."""

    def __init__(self, by_id):
        self._by_id = by_id

    def get_by_id(self, pid):
        return self._by_id.get(pid)


class _FakeService:
    """Minimal CarBackgroundEnhanceService stand-in: `results` is consumed in
    order by successive `enhance_photo` calls — an Exception instance is
    raised instead of returned. `bg_calls` records the background_id passed to
    each call; `valid_backgrounds` (when set) makes `resolve_background_id`
    reject anything off-list, mirroring the real service's 400."""

    def __init__(self, results=None, valid_backgrounds=None):
        self._results = list(results or [])
        self.calls = []
        self.bg_calls = []
        self._valid = valid_backgrounds

    def resolve_background_id(self, background_id=None):
        if background_id and self._valid is not None and background_id not in self._valid:
            raise CarBackgroundError(
                f'background_id "{background_id}" is not a preferred background', 400)
        return background_id

    def enhance_photo(self, pid, background_id=None):
        self.calls.append(pid)
        self.bg_calls.append(background_id)
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result
