"""Tests for the CarPark photo UPLOAD endpoint:
POST /api/carpark/vehicles/<id>/photos/upload.

Uses the real Flask app (`app.py`) so the actual Flask-Login + carpark
permission-decorator wiring is exercised end-to-end (mirrors
jarvis/tests/core/test_media_routes.py, the sibling test from the same
feature slice). Under pytest, the top-level conftest.py mocks psycopg2
before `app` is imported, so the real `UserRepository.get_by_id` call made
by Flask-Login's user_loader returns `{}` (falsy) instead of a real user —
we patch `app._user_repo.get_by_id` per-test to return a real user dict so
session-based login actually authenticates AND carries the right
`can_access_carpark` / `can_edit_carpark` permission flags (see
`core/auth/models.py::User`).

GOTCHA: `app.py`'s Flask-Login `user_loader` caches loaded `User` objects
per-process for 60s, keyed by int(user_id) (see `_user_cache` in
`app.py::_setup_login_manager`). Reusing the same uid across tests with
different permission dicts would silently read the stale cached user
instead of the freshly-monkeypatched one. We dodge this by giving every
test its own unique uid, so each gets its own fresh cache entry.
"""
import io
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from unittest import mock
import pytest

import app as app_module
from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    return flask_app.test_client()


def _login(client, monkeypatch, uid, **perm_overrides):
    """Log a session in as `uid`, whose loaded User carries carpark
    permission flags from `perm_overrides` (defaults: full carpark access)."""
    user_dict = {
        'id': uid,
        'email': f'test{uid}@example.com',
        'name': 'Test User',
        'can_access_carpark': True,
        'can_edit_carpark': True,
    }
    user_dict.update(perm_overrides)
    monkeypatch.setattr(app_module._user_repo, 'get_by_id', lambda _uid: user_dict)
    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)


def _jpeg_bytes(size=(2000, 1500)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', size, (10, 20, 30)).save(buf, 'JPEG')
    return buf.getvalue()


def test_upload_stores_key_and_creates_row(client, monkeypatch):
    _login(client, monkeypatch, uid=90001)
    with mock.patch('carpark.routes.photos.spaces_service.is_enabled', return_value=True), \
         mock.patch('carpark.routes.photos.spaces_service.upload', side_effect=lambda data, key, ct: key) as up, \
         mock.patch('carpark.routes.photos._photo_repo.create',
                    return_value={'id': 1, 'url': 'private/carpark/18/01.jpg', 'is_primary': True}) as create, \
         mock.patch('carpark.routes.photos._photo_repo.get_by_vehicle', return_value=[]), \
         mock.patch('carpark.routes.photos._verify_vehicle_ownership', return_value=({'id': 18}, None)):
        data = {'file': (io.BytesIO(_jpeg_bytes()), 'photo.jpg')}
        r = client.post('/api/carpark/vehicles/18/photos/upload',
                        data=data, content_type='multipart/form-data')
    assert r.status_code in (200, 201)
    # key was stored, not raw bytes / public URL
    assert up.call_args.args[1].startswith('private/carpark/18/')
    assert up.call_args.args[1].endswith('.jpg')
    assert up.call_args.args[2] == 'image/jpeg'
    stored_url = create.call_args.kwargs.get('url') or create.call_args.args[1]
    assert stored_url.startswith('private/carpark/18/')
    # first photo on a vehicle with none yet -> primary
    assert create.call_args.kwargs.get('is_primary') is True
    # what got uploaded is the compressed JPEG, never the raw bytes
    uploaded_bytes = up.call_args.args[0]
    assert isinstance(uploaded_bytes, bytes)
    assert uploaded_bytes != _jpeg_bytes()
    assert create.call_args.kwargs.get('file_size') == len(uploaded_bytes)


def test_upload_compresses_to_max_1600px(client, monkeypatch):
    from PIL import Image
    _login(client, monkeypatch, uid=90002)
    with mock.patch('carpark.routes.photos.spaces_service.is_enabled', return_value=True), \
         mock.patch('carpark.routes.photos.spaces_service.upload', side_effect=lambda data, key, ct: key) as up, \
         mock.patch('carpark.routes.photos._photo_repo.create', return_value={'id': 1}), \
         mock.patch('carpark.routes.photos._photo_repo.get_by_vehicle', return_value=[]), \
         mock.patch('carpark.routes.photos._verify_vehicle_ownership', return_value=({'id': 18}, None)):
        data = {'file': (io.BytesIO(_jpeg_bytes(size=(3000, 2000))), 'big.jpg')}
        client.post('/api/carpark/vehicles/18/photos/upload',
                    data=data, content_type='multipart/form-data')
    out = Image.open(io.BytesIO(up.call_args.args[0]))
    assert max(out.size) <= 1600
    assert out.format == 'JPEG'


def test_upload_multiple_files_only_first_is_primary(client, monkeypatch):
    _login(client, monkeypatch, uid=90003)
    with mock.patch('carpark.routes.photos.spaces_service.is_enabled', return_value=True), \
         mock.patch('carpark.routes.photos.spaces_service.upload', side_effect=lambda data, key, ct: key), \
         mock.patch('carpark.routes.photos._photo_repo.create',
                    side_effect=lambda **kw: dict(kw, id=len(created_calls) + 1)) as create, \
         mock.patch('carpark.routes.photos._photo_repo.get_by_vehicle', return_value=[]), \
         mock.patch('carpark.routes.photos._verify_vehicle_ownership', return_value=({'id': 18}, None)):
        created_calls = []
        data = {'files': [
            (io.BytesIO(_jpeg_bytes()), 'a.jpg'),
            (io.BytesIO(_jpeg_bytes()), 'b.jpg'),
        ]}
        r = client.post('/api/carpark/vehicles/18/photos/upload',
                        data=data, content_type='multipart/form-data')
    assert r.status_code == 201
    assert create.call_count == 2
    first_kwargs = create.call_args_list[0].kwargs
    second_kwargs = create.call_args_list[1].kwargs
    assert first_kwargs['is_primary'] is True
    assert second_kwargs['is_primary'] is False
    assert len(r.get_json()['photos']) == 2


def test_upload_not_primary_when_vehicle_already_has_photos(client, monkeypatch):
    _login(client, monkeypatch, uid=90004)
    with mock.patch('carpark.routes.photos.spaces_service.is_enabled', return_value=True), \
         mock.patch('carpark.routes.photos.spaces_service.upload', side_effect=lambda data, key, ct: key), \
         mock.patch('carpark.routes.photos._photo_repo.create', return_value={'id': 2}) as create, \
         mock.patch('carpark.routes.photos._photo_repo.get_by_vehicle',
                    return_value=[{'id': 1, 'is_primary': True}]), \
         mock.patch('carpark.routes.photos._verify_vehicle_ownership', return_value=({'id': 18}, None)):
        data = {'file': (io.BytesIO(_jpeg_bytes()), 'photo.jpg')}
        client.post('/api/carpark/vehicles/18/photos/upload',
                    data=data, content_type='multipart/form-data')
    assert create.call_args.kwargs.get('is_primary') is False


def test_upload_requires_file(client, monkeypatch):
    _login(client, monkeypatch, uid=90005)
    with mock.patch('carpark.routes.photos.spaces_service.is_enabled', return_value=True), \
         mock.patch('carpark.routes.photos._verify_vehicle_ownership', return_value=({'id': 18}, None)):
        r = client.post('/api/carpark/vehicles/18/photos/upload',
                        data={}, content_type='multipart/form-data')
    assert r.status_code == 400


def test_upload_503_when_storage_not_configured(client, monkeypatch):
    _login(client, monkeypatch, uid=90006)
    with mock.patch('carpark.routes.photos.spaces_service.is_enabled', return_value=False), \
         mock.patch('carpark.routes.photos._verify_vehicle_ownership', return_value=({'id': 18}, None)):
        data = {'file': (io.BytesIO(_jpeg_bytes()), 'photo.jpg')}
        r = client.post('/api/carpark/vehicles/18/photos/upload',
                        data=data, content_type='multipart/form-data')
    assert r.status_code == 503


def test_upload_404_when_vehicle_not_owned(client, monkeypatch):
    _login(client, monkeypatch, uid=90007)
    # _verify_vehicle_ownership returns (vehicle, err) — err is whatever the
    # sibling routes return-as-is on failure (a (body, status) tuple that
    # Flask auto-jsonifies; a dict body is enough here, no app context
    # needed to build it, unlike calling jsonify() outside a request).
    not_found_err = ({'success': False, 'error': 'Vehicle not found'}, 404)
    with mock.patch('carpark.routes.photos._verify_vehicle_ownership',
                    return_value=(None, not_found_err)):
        data = {'file': (io.BytesIO(_jpeg_bytes()), 'photo.jpg')}
        r = client.post('/api/carpark/vehicles/999/photos/upload',
                        data=data, content_type='multipart/form-data')
    assert r.status_code == 404


def test_upload_403_without_edit_permission(client, monkeypatch):
    _login(client, monkeypatch, uid=90008, can_edit_carpark=False)
    with mock.patch('carpark.routes.photos._verify_vehicle_ownership', return_value=({'id': 18}, None)):
        data = {'file': (io.BytesIO(_jpeg_bytes()), 'photo.jpg')}
        r = client.post('/api/carpark/vehicles/18/photos/upload',
                        data=data, content_type='multipart/form-data')
    assert r.status_code == 403


# ── Robustness fixes (round 1): size/pixel/count caps, 4xx on bad image,
#    atomic multi-file upload with rollback ──

def test_upload_rejects_non_image_with_400(client, monkeypatch):
    _login(client, monkeypatch, uid=90009)
    with mock.patch('carpark.routes.photos.spaces_service.is_enabled', return_value=True), \
         mock.patch('carpark.routes.photos.spaces_service.upload') as up, \
         mock.patch('carpark.routes.photos._photo_repo.create') as create, \
         mock.patch('carpark.routes.photos._photo_repo.get_by_vehicle', return_value=[]), \
         mock.patch('carpark.routes.photos._verify_vehicle_ownership', return_value=({'id': 18}, None)):
        data = {'file': (io.BytesIO(b'not an image'), 'evil.jpg')}
        r = client.post('/api/carpark/vehicles/18/photos/upload',
                        data=data, content_type='multipart/form-data')
    assert r.status_code == 400
    # Nothing must be written to Spaces or the DB for a bad-image request.
    up.assert_not_called()
    create.assert_not_called()


def test_upload_rejects_oversize_file_with_413(client, monkeypatch):
    _login(client, monkeypatch, uid=90010)
    # Patch the cap tiny so we can trip it with a small (but > cap) payload
    # without allocating 15 MB — this exercises OUR per-file size check
    # directly, independent of any Flask global MAX_CONTENT_LENGTH.
    with mock.patch('carpark.routes.photos.MAX_PHOTO_SIZE', 100), \
         mock.patch('carpark.routes.photos.spaces_service.is_enabled', return_value=True), \
         mock.patch('carpark.routes.photos.spaces_service.upload') as up, \
         mock.patch('carpark.routes.photos._photo_repo.create') as create, \
         mock.patch('carpark.routes.photos._photo_repo.get_by_vehicle', return_value=[]), \
         mock.patch('carpark.routes.photos._verify_vehicle_ownership', return_value=({'id': 18}, None)):
        data = {'file': (io.BytesIO(b'x' * 500), 'big.jpg')}
        r = client.post('/api/carpark/vehicles/18/photos/upload',
                        data=data, content_type='multipart/form-data')
    assert r.status_code in (400, 413)
    up.assert_not_called()
    create.assert_not_called()


def test_upload_rejects_too_many_files_with_400(client, monkeypatch):
    _login(client, monkeypatch, uid=90011)
    with mock.patch('carpark.routes.photos.spaces_service.is_enabled', return_value=True), \
         mock.patch('carpark.routes.photos.spaces_service.upload') as up, \
         mock.patch('carpark.routes.photos._photo_repo.create') as create, \
         mock.patch('carpark.routes.photos._photo_repo.get_by_vehicle', return_value=[]), \
         mock.patch('carpark.routes.photos._verify_vehicle_ownership', return_value=({'id': 18}, None)):
        # 51 > MAX_BATCH_PHOTOS (50). Count is checked before any read, so the
        # payloads can be trivial.
        data = {'files': [(io.BytesIO(b'x'), f'{i}.jpg') for i in range(51)]}
        r = client.post('/api/carpark/vehicles/18/photos/upload',
                        data=data, content_type='multipart/form-data')
    assert r.status_code == 400
    up.assert_not_called()
    create.assert_not_called()


def test_upload_rolls_back_this_requests_writes_on_midbatch_failure(client, monkeypatch):
    _login(client, monkeypatch, uid=90012)
    upload_calls = {'n': 0}

    def _upload(data, key, ct):
        upload_calls['n'] += 1
        if upload_calls['n'] == 2:
            raise RuntimeError('spaces down')
        return key

    with mock.patch('carpark.routes.photos.spaces_service.is_enabled', return_value=True), \
         mock.patch('carpark.routes.photos.spaces_service.upload', side_effect=_upload) as up, \
         mock.patch('carpark.routes.photos.spaces_service.delete') as sp_delete, \
         mock.patch('carpark.routes.photos._photo_repo.create',
                    return_value={'id': 101, 'url': 'private/carpark/18/a.jpg'}), \
         mock.patch('carpark.routes.photos._photo_repo.delete') as repo_delete, \
         mock.patch('carpark.routes.photos._photo_repo.get_by_vehicle', return_value=[]), \
         mock.patch('carpark.routes.photos._verify_vehicle_ownership', return_value=({'id': 18}, None)):
        data = {'files': [
            (io.BytesIO(_jpeg_bytes()), 'a.jpg'),
            (io.BytesIO(_jpeg_bytes()), 'b.jpg'),
        ]}
        r = client.post('/api/carpark/vehicles/18/photos/upload',
                        data=data, content_type='multipart/form-data')
    assert r.status_code == 500
    # File 1's object was uploaded and its row created before file 2 failed —
    # both must be rolled back for this request to be all-or-nothing.
    first_key = up.call_args_list[0].args[1]
    repo_delete.assert_called_once_with(101)
    sp_delete.assert_called_once_with(first_key)
