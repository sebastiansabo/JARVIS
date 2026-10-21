"""Tests for Task 5: the `'contract'` photo_type whitelist fix + the
store/replace helper `PhotoRepository.store_contract_pdf`.

Two DB-backed tests (`seeded_record` fixture, mirrors the `_record()` helper
in test_photo_repository.py: a real buyback_records row via
RecordRepository().create()) exercise store_contract_pdf against the real
localhost/defaultdb Postgres — same `require_real_db` skip-if-unreachable
guard as the rest of the buyback suite. `spaces_service.upload` is
monkeypatched (via `mock.patch`) on the photo_repository module so NO real
Spaces network call ever happens, mirroring the
`test_store_documents_uploads_private_pdf_and_creates_rows` pattern already
in test_photo_repository.py.

The third test (serialize_photos labels 'contract' as a document with the
'Contract' label) is a PURE function test — no DB, no fixture — and must stay
runnable even when Postgres is unreachable.
"""
import os

from unittest import mock

from buyback.repositories.record_repository import RecordRepository
from buyback.repositories.photo_repository import PhotoRepository


def _code():
    return f'BB-CONTRACT-{os.urandom(4).hex()}'


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


import pytest  # noqa: E402


@pytest.fixture
def seeded_record(require_real_db):
    """A real buyback_records row for store_contract_pdf to attach to."""
    return _record()


# ── store_contract_pdf (DB-backed) ──────────────────────────────────────────

def test_store_contract_creates_contract_typed_row(seeded_record):
    repo = PhotoRepository()
    with mock.patch('buyback.repositories.photo_repository.spaces_service.upload',
                     side_effect=lambda data, key, ct, acl='private': key) as up:
        row = repo.store_contract_pdf(seeded_record['id'], b'%PDF-1.4 x', 'Contract achizitie')

    assert row['photo_type'] == 'contract' and row['caption'] == 'Contract achizitie'
    up.assert_called_once()
    call = up.call_args
    assert call.args[1].startswith(f"private/buyback/{seeded_record['id']}/contract-")
    assert call.args[1].endswith('.pdf')
    assert call.args[2] == 'application/pdf'
    assert call.kwargs.get('acl') == 'private'
    assert row['file_size'] == len(b'%PDF-1.4 x')


def test_regenerate_replaces_prior_contract(seeded_record):
    repo = PhotoRepository()
    with mock.patch('buyback.repositories.photo_repository.spaces_service.upload',
                     side_effect=lambda data, key, ct, acl='private': key):
        repo.store_contract_pdf(seeded_record['id'], b'%PDF- a', 'C')
        repo.store_contract_pdf(seeded_record['id'], b'%PDF- b', 'C')
    docs = [p for p in repo.get_by_record(seeded_record['id']) if p['photo_type'] == 'contract']
    assert len(docs) == 1


# ── serialize_photos (pure — no DB) ─────────────────────────────────────────

def test_serialize_marks_contract_as_document():
    from buyback.routes import _shared
    out = _shared.serialize_photos([{'id': 1, 'record_id': 9, 'photo_type': 'contract', 'caption': None}])
    assert out[0]['is_document'] is True
    assert out[0]['download_url'].endswith('/records/9/photos/1/download')
    assert out[0]['label'] == 'Contract'
