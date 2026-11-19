"""Document-bytes fetch helper (Spaces / http) for invoice OCR.

A `carpark_vehicle_documents` row's `file_url` can point at one of three
places depending on how it was uploaded/migrated:

  - a DigitalOcean Spaces object key (current upload path), or a legacy
    base64 `data:` URI — both resolved via `spaces_service.resolve_image_bytes`;
  - a plain http(s) URL (older/external links) — fetched via `requests.get`.

A document with no `file_url` at all (e.g. DMS-only, or linkless) has nothing
fetchable here and raises `ValueError` so the invoice-OCR caller can surface a
clear error instead of crashing deeper in the parser.

Pure glue — no DB access. `requests` and `spaces_service` are imported at
module level (not locally) so tests can monkeypatch
`document_fetch.requests.get` / `document_fetch.spaces_service.resolve_image_bytes`
directly.
"""
import os

import requests

from core.services import spaces_service

DEFAULT_FILENAME = 'invoice.pdf'


def _derive_filename(file_url: str) -> str:
    """Basename of `file_url`, for the extension the invoice parser keys on.

    Falls back to DEFAULT_FILENAME when there's no usable basename/extension
    (a `data:` URI, a bare key with no suffix, or a trailing-dot/edge case).
    """
    lowered = file_url.lower()
    if lowered.startswith('data:'):
        return DEFAULT_FILENAME

    path_only = file_url.split('?', 1)[0].split('#', 1)[0]
    basename = path_only.rsplit('/', 1)[-1]
    stem, ext = os.path.splitext(basename)
    if not stem or not ext or ext == '.':
        return DEFAULT_FILENAME
    return basename


def fetch_document_bytes(document: dict) -> tuple[bytes, str]:
    """Fetch a document's raw bytes so it can be OCR'd.

    Returns (file_bytes, filename). Raises ValueError when the document has
    no fetchable file_url (DMS-only or linkless documents).
    """
    file_url = (document or {}).get('file_url')
    if not file_url:
        raise ValueError('no fetchable file for document')

    file_url_str = str(file_url)
    filename = _derive_filename(file_url_str)

    if file_url_str.lower().startswith(('http://', 'https://')):
        response = requests.get(file_url_str, timeout=20)
        response.raise_for_status()
        return response.content, filename

    return spaces_service.resolve_image_bytes(file_url), filename
