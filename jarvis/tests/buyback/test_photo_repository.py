"""Tests for the buyback PhotoRepository (Task 6): create/get_by_record/
reorder/soft_delete against buyback_photos, plus store_base64_images (the
base64->Spaces upload helper).

DB-backed (uses `require_real_db` from tests/buyback/conftest.py) — obtains
its connection via the repository's own `database` layer, NOT raw
psycopg2.connect, since jarvis/conftest.py mocks psycopg2 at collection time
for the rest of the suite (see tests/buyback/test_offer_repository.py for
the same pattern). Each test creates its own parent buyback_records row via
RecordRepository().create() with a unique record_code + VIN.

Spaces is DISABLED in the test environment (no DO_SPACES_* creds), so every
store_base64_images test monkeypatches
`buyback.repositories.photo_repository.spaces_service.upload` to avoid a
real network call — mirrors tests/carpark/test_photo_upload.py's
`mock.patch('carpark.routes.photos.spaces_service.upload', ...)` pattern.
`resolve_image_bytes` is NOT patched: it's a pure base64 decode for
`data:` URLs (core/services/spaces_service.py), so real data URLs built
from os.urandom bytes exercise the real decode path end-to-end.
"""
import base64
import os

from unittest import mock

import pytest

from buyback.repositories.record_repository import RecordRepository
from buyback.repositories.photo_repository import PhotoRepository


def _code(prefix='BB-PHOTO'):
    return f'{prefix}-{os.urandom(4).hex()}'


def _vin():
    # Not checksum-valid (the schema doesn't enforce VIN format), just a
    # unique 17-char alnum string so concurrent/rerun tests never collide.
    return ('WBA' + os.urandom(7).hex().upper())[:17]


def _record(**overrides):
    data = {
        'record_code': _code(),
        'company_id': 1,
        'vin': _vin(),
        'brand': 'BMW',
        'model': '320d',
        'created_by': 1,
    }
    data.update(overrides)
    return RecordRepository().create(data)


def _data_url(n_bytes):
    raw = os.urandom(n_bytes)
    b64 = base64.b64encode(raw).decode()
    return f'data:image/jpeg;base64,{b64}'


# ── create / get_by_record ──────────────────────────────────────────────

def test_create_auto_sort_and_primary(require_real_db):
    rid = _record()['id']
    repo = PhotoRepository()
    a = repo.create(rid, 'private/buyback/1/a.jpg', is_primary=True)
    b = repo.create(rid, 'private/buyback/1/b.jpg')
    assert a['is_primary'] is True
    assert b['sort_order'] > a['sort_order']
    assert len(repo.get_by_record(rid)) == 2


def test_create_second_primary_unsets_first(require_real_db):
    rid = _record()['id']
    repo = PhotoRepository()
    a = repo.create(rid, 'private/buyback/1/a.jpg', is_primary=True)
    b = repo.create(rid, 'private/buyback/1/b.jpg', is_primary=True)
    photos = {p['id']: p for p in repo.get_by_record(rid)}
    assert photos[a['id']]['is_primary'] is False
    assert photos[b['id']]['is_primary'] is True


def test_get_by_record_filters_photo_type(require_real_db):
    rid = _record()['id']
    repo = PhotoRepository()
    repo.create(rid, 'private/buyback/1/a.jpg', photo_type='gallery')
    repo.create(rid, 'private/buyback/1/b.jpg', photo_type='inspection')
    gallery = repo.get_by_record(rid, photo_type='gallery')
    assert len(gallery) == 1
    assert gallery[0]['photo_type'] == 'gallery'


def test_get_by_record_excludes_soft_deleted(require_real_db):
    rid = _record()['id']
    repo = PhotoRepository()
    a = repo.create(rid, 'private/buyback/1/a.jpg')
    b = repo.create(rid, 'private/buyback/1/b.jpg')
    repo.soft_delete([a['id']])
    remaining = repo.get_by_record(rid)
    assert len(remaining) == 1
    assert remaining[0]['id'] == b['id']


def test_get_by_record_orders_by_sort_order_then_id(require_real_db):
    rid = _record()['id']
    repo = PhotoRepository()
    a = repo.create(rid, 'private/buyback/1/a.jpg')
    b = repo.create(rid, 'private/buyback/1/b.jpg')
    c = repo.create(rid, 'private/buyback/1/c.jpg')
    assert [p['id'] for p in repo.get_by_record(rid)] == [a['id'], b['id'], c['id']]


# ── reorder / soft_delete ────────────────────────────────────────────────

def test_reorder(require_real_db):
    rid = _record()['id']
    repo = PhotoRepository()
    a = repo.create(rid, 'private/buyback/1/a.jpg')
    b = repo.create(rid, 'private/buyback/1/b.jpg')
    repo.reorder(rid, [b['id'], a['id']])
    ordered = repo.get_by_record(rid)
    assert [p['id'] for p in ordered] == [b['id'], a['id']]


def test_soft_delete_scoped_to_record(require_real_db):
    rid1 = _record()['id']
    rid2 = _record()['id']
    repo = PhotoRepository()
    a = repo.create(rid1, 'private/buyback/1/a.jpg')
    n = repo.soft_delete([a['id']], record_id=rid2)
    assert n == 0
    assert len(repo.get_by_record(rid1)) == 1


def test_soft_delete_empty_list_is_noop(require_real_db):
    repo = PhotoRepository()
    assert repo.soft_delete([]) == 0


# ── store_base64_images ─────────────────────────────────────────────────

def test_store_base64_images_uploads_and_creates_rows(require_real_db):
    rid = _record()['id']
    repo = PhotoRepository()
    images = [_data_url(100), _data_url(100)]
    with mock.patch('buyback.repositories.photo_repository.spaces_service.upload',
                     side_effect=lambda data, key, ct: key) as up:
        rows = repo.store_base64_images(rid, images, max_bytes=10_000)

    assert up.call_count == 2
    for call in up.call_args_list:
        assert call.args[1].startswith(f'private/buyback/{rid}/')
        assert call.args[1].endswith('.jpg')
        assert call.args[2] == 'image/jpeg'

    assert len(rows) == 2
    assert rows[0]['is_primary'] is True
    assert rows[1]['is_primary'] is False
    assert rows[0]['file_size'] == 100
    assert len(repo.get_by_record(rid)) == 2


def test_store_base64_images_not_primary_when_gallery_nonempty(require_real_db):
    rid = _record()['id']
    repo = PhotoRepository()
    repo.create(rid, 'private/buyback/1/existing.jpg', is_primary=True)
    with mock.patch('buyback.repositories.photo_repository.spaces_service.upload',
                     side_effect=lambda data, key, ct: key):
        rows = repo.store_base64_images(rid, [_data_url(100)], max_bytes=10_000)
    assert rows[0]['is_primary'] is False


def test_store_base64_images_rejects_oversized_batch_before_upload(require_real_db):
    rid = _record()['id']
    repo = PhotoRepository()
    images = [_data_url(200), _data_url(200)]
    with mock.patch('buyback.repositories.photo_repository.spaces_service.upload') as up:
        with pytest.raises(ValueError, match='payload too large'):
            repo.store_base64_images(rid, images, max_bytes=300)
    up.assert_not_called()
    assert len(repo.get_by_record(rid)) == 0
