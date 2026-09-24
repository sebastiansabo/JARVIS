"""Route tests for the buyback photo HTTP endpoints (Task 12):
upload/list/reorder/soft-delete under /api/buyback/records/<id>/photos[...],
gated by @v2_permission_required('buyback', 'record', 'edit') plus the same
cross-company IDOR guard as records.py.

Uses the real app (`client` fixture) + the `as_role(role_name, company_id)`
login helper from tests/buyback/conftest.py — NOT a `client_as` helper (see
test_routes_records.py's module docstring for why).

Per Ruling R4: happy-path tests authenticate as as_role('Admin', 1) (admin
bypass -> g.permission_scope == 'all'). Sales has 'own' scope with
record.edit (per migrations/domains/schema_roles.py::_seed_buyback_permissions_v2),
so cross-company IDOR is exercised with Sales for both the owner and the
intruder company, mirroring test_routes_records.py's
test_mutation_cross_company_idor_forbidden.

Spaces is disabled in the test environment (no DO_SPACES_* creds) —
spaces_service.upload/delete are monkeypatched at
`buyback.routes.photos.spaces_service` to no-ops rather than faking
is_enabled() (the buyback upload route, like inspection.py's report upload,
does not gate on is_enabled() at all — see photos.py's module docstring).
"""
import io

import pytest
from PIL import Image

import buyback.routes.photos as photos_mod

pytestmark = pytest.mark.usefixtures('require_real_db')


def _vin():
    # Not checksum-valid (VIN_RE only checks shape), unique per call so
    # parallel/rerun tests never collide.
    import secrets
    alphabet = 'ABCDEFGHJKLMNPRSTUVWXYZ0123456789'
    return 'WBA' + ''.join(secrets.choice(alphabet) for _ in range(14))


def _payload(**overrides):
    data = {
        'vin': _vin(),
        'brand': 'BMW',
        'model': '320d',
        'acquisition_type': 'buyback',
        'client_asking_price_eur': 1000,
        'seller_email': 's@e.z',
    }
    data.update(overrides)
    return data


def _make_record(client, as_role, company_id=1):
    as_role('Admin', company_id)
    return client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']


def _png_bytes(color='red'):
    b = io.BytesIO()
    Image.new('RGB', (10, 10), color).save(b, 'PNG')
    b.seek(0)
    return b


@pytest.fixture(autouse=True)
def _noop_spaces(monkeypatch):
    """Every test in this file uploads through the multipart route, so
    default all of them to a no-op Spaces upload/delete; individual tests
    override this when they need to observe/fail specific calls."""
    monkeypatch.setattr(photos_mod.spaces_service, 'upload', lambda data, key, ct: key)
    monkeypatch.setattr(photos_mod.spaces_service, 'delete', lambda key: None)


# ── UPLOAD + LIST ────────────────────────────────────────────────────────

def test_upload_and_list_photos(client, as_role):
    rid = _make_record(client, as_role)
    r = client.post(f'/api/buyback/records/{rid}/photos/upload',
                     data={'files': (_png_bytes(), 'a.png')},
                     content_type='multipart/form-data')
    assert r.status_code in (200, 201), r.get_json()
    body = r.get_json()
    assert body['success'] is True
    assert len(body['photos']) == 1
    assert body['photos'][0]['is_primary'] is True
    assert body['photos'][0]['url'].startswith(f'private/buyback/{rid}/')
    assert body['photos'][0]['url'].endswith('.jpg')

    lst = client.get(f'/api/buyback/records/{rid}/photos').get_json()
    assert len(lst['photos']) == 1
    assert lst['photos'][0]['id'] == body['photos'][0]['id']


def test_get_photos_empty_initially(client, as_role):
    rid = _make_record(client, as_role)
    lst = client.get(f'/api/buyback/records/{rid}/photos').get_json()
    assert lst['photos'] == []


def test_upload_multiple_files_only_first_is_primary(client, as_role):
    rid = _make_record(client, as_role)
    r = client.post(f'/api/buyback/records/{rid}/photos/upload',
                     data={'files': [(_png_bytes('red'), 'a.png'), (_png_bytes('blue'), 'b.png')]},
                     content_type='multipart/form-data')
    assert r.status_code in (200, 201), r.get_json()
    photos = r.get_json()['photos']
    assert len(photos) == 2
    assert sum(1 for p in photos if p['is_primary']) == 1
    assert photos[0]['is_primary'] is True
    assert photos[1]['is_primary'] is False


def test_second_upload_does_not_override_existing_primary(client, as_role):
    rid = _make_record(client, as_role)
    client.post(f'/api/buyback/records/{rid}/photos/upload',
                data={'files': (_png_bytes(), 'a.png')},
                content_type='multipart/form-data')
    r = client.post(f'/api/buyback/records/{rid}/photos/upload',
                     data={'files': (_png_bytes(), 'b.png')},
                     content_type='multipart/form-data')
    assert r.get_json()['photos'][0]['is_primary'] is False

    lst = client.get(f'/api/buyback/records/{rid}/photos').get_json()['photos']
    assert sum(1 for p in lst if p['is_primary']) == 1


def test_upload_no_files_is_400(client, as_role):
    rid = _make_record(client, as_role)
    r = client.post(f'/api/buyback/records/{rid}/photos/upload',
                     data={}, content_type='multipart/form-data')
    assert r.status_code == 400


def test_upload_non_image_is_400_not_500(client, as_role):
    rid = _make_record(client, as_role)
    r = client.post(f'/api/buyback/records/{rid}/photos/upload',
                     data={'files': (io.BytesIO(b'not an image'), 'a.png')},
                     content_type='multipart/form-data')
    assert r.status_code == 400, r.get_json()
    assert r.status_code != 500


def test_upload_oversized_file_is_413(client, as_role, monkeypatch):
    monkeypatch.setattr(photos_mod, 'MAX_PHOTO_SIZE', 10)
    rid = _make_record(client, as_role)
    r = client.post(f'/api/buyback/records/{rid}/photos/upload',
                     data={'files': (_png_bytes(), 'a.png')},
                     content_type='multipart/form-data')
    assert r.status_code == 413


def test_upload_missing_record_is_404(client, as_role):
    as_role('Admin', 1)
    r = client.post('/api/buyback/records/999999999/photos/upload',
                     data={'files': (_png_bytes(), 'a.png')},
                     content_type='multipart/form-data')
    assert r.status_code == 404


def test_get_missing_record_is_404(client, as_role):
    as_role('Admin', 1)
    r = client.get('/api/buyback/records/999999999/photos')
    assert r.status_code == 404


# ── ROLLBACK ─────────────────────────────────────────────────────────────

def test_upload_mid_batch_failure_rolls_back(client, as_role, monkeypatch):
    """The 2nd file's Spaces upload raises -> the 1st file's already-created
    Spaces object + DB row must be rolled back, leaving the gallery empty."""
    rid = _make_record(client, as_role)

    calls = {'n': 0}
    deleted_keys = []

    def _flaky_upload(data, key, ct):
        calls['n'] += 1
        if calls['n'] == 2:
            raise RuntimeError('simulated Spaces outage')
        return key

    monkeypatch.setattr(photos_mod.spaces_service, 'upload', _flaky_upload)
    monkeypatch.setattr(photos_mod.spaces_service, 'delete', lambda key: deleted_keys.append(key))

    r = client.post(f'/api/buyback/records/{rid}/photos/upload',
                     data={'files': [(_png_bytes('red'), 'a.png'), (_png_bytes('blue'), 'b.png')]},
                     content_type='multipart/form-data')
    assert r.status_code == 500, r.get_json()

    # No ghost row: the gallery must be empty after rollback.
    lst = client.get(f'/api/buyback/records/{rid}/photos').get_json()
    assert lst['photos'] == []
    # The 1st file's Spaces object was rolled back (best-effort delete called).
    assert len(deleted_keys) == 1


# ── REORDER ──────────────────────────────────────────────────────────────

def test_reorder_changes_order(client, as_role):
    rid = _make_record(client, as_role)
    r = client.post(f'/api/buyback/records/{rid}/photos/upload',
                     data={'files': [(_png_bytes('red'), 'a.png'), (_png_bytes('blue'), 'b.png')]},
                     content_type='multipart/form-data')
    ids = [p['id'] for p in r.get_json()['photos']]
    assert len(ids) == 2

    reversed_ids = list(reversed(ids))
    r2 = client.post(f'/api/buyback/records/{rid}/photos/reorder', json={'ids': reversed_ids})
    assert r2.status_code == 200, r2.get_json()

    lst = client.get(f'/api/buyback/records/{rid}/photos').get_json()['photos']
    assert [p['id'] for p in lst] == reversed_ids


def test_reorder_requires_ids_array(client, as_role):
    rid = _make_record(client, as_role)
    r = client.post(f'/api/buyback/records/{rid}/photos/reorder', json={})
    assert r.status_code == 400


def test_reorder_missing_record_is_404(client, as_role):
    as_role('Admin', 1)
    r = client.post('/api/buyback/records/999999999/photos/reorder', json={'ids': []})
    assert r.status_code == 404


# ── DELETE ───────────────────────────────────────────────────────────────

def test_soft_delete_removes_from_list(client, as_role):
    rid = _make_record(client, as_role)
    r = client.post(f'/api/buyback/records/{rid}/photos/upload',
                     data={'files': [(_png_bytes('red'), 'a.png'), (_png_bytes('blue'), 'b.png')]},
                     content_type='multipart/form-data')
    photos = r.get_json()['photos']
    pid_to_delete = photos[0]['id']
    pid_to_keep = photos[1]['id']

    dele = client.delete(f'/api/buyback/records/{rid}/photos/{pid_to_delete}')
    assert dele.status_code == 200, dele.get_json()
    assert dele.get_json()['success'] is True

    lst = client.get(f'/api/buyback/records/{rid}/photos').get_json()['photos']
    assert [p['id'] for p in lst] == [pid_to_keep]


def test_delete_missing_photo_is_404(client, as_role):
    rid = _make_record(client, as_role)
    r = client.delete(f'/api/buyback/records/{rid}/photos/999999999')
    assert r.status_code == 404


def test_delete_missing_record_is_404(client, as_role):
    as_role('Admin', 1)
    r = client.delete('/api/buyback/records/999999999/photos/1')
    assert r.status_code == 404


# ── CROSS-COMPANY IDOR ───────────────────────────────────────────────────

def test_upload_cross_company_forbidden(client, as_role):
    as_role('Sales', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']

    as_role('Sales', 2)
    r = client.post(f'/api/buyback/records/{rid}/photos/upload',
                     data={'files': (_png_bytes(), 'a.png')},
                     content_type='multipart/form-data')
    assert r.status_code == 403


def test_get_cross_company_forbidden(client, as_role):
    as_role('Sales', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']

    as_role('Sales', 2)
    r = client.get(f'/api/buyback/records/{rid}/photos')
    assert r.status_code == 403


def test_delete_cross_company_forbidden(client, as_role):
    as_role('Sales', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']
    up = client.post(f'/api/buyback/records/{rid}/photos/upload',
                      data={'files': (_png_bytes(), 'a.png')},
                      content_type='multipart/form-data')
    pid = up.get_json()['photos'][0]['id']

    as_role('Sales', 2)
    r = client.delete(f'/api/buyback/records/{rid}/photos/{pid}')
    assert r.status_code == 403


def test_reorder_cross_company_forbidden(client, as_role):
    as_role('Sales', 1)
    rid = client.post('/api/buyback/records', json=_payload()).get_json()['record']['id']

    as_role('Sales', 2)
    r = client.post(f'/api/buyback/records/{rid}/photos/reorder', json={'ids': []})
    assert r.status_code == 403
