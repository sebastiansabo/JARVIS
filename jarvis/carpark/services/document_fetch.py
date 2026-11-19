"""Document-bytes fetch helper (Spaces / http) for invoice OCR.

A `carpark_vehicle_documents` row's `file_url` can point at one of three
places depending on how it was uploaded/migrated:

  - a DigitalOcean Spaces object key (current upload path), or a legacy
    base64 `data:` URI — both resolved via `spaces_service.resolve_image_bytes`;
  - a plain http(s) URL (older/external links) — fetched via `requests.get`.

A document with no `file_url` at all (e.g. DMS-only, or linkless) has nothing
fetchable here and raises `ValueError` so the invoice-OCR caller can surface a
clear error instead of crashing deeper in the parser.

The http(s) branch is SSRF-hardened: `file_url` is user-controlled (link-mode
document uploads accept arbitrary http(s) URLs) and this helper runs server-side
during invoice parsing, so a hostile URL could otherwise reach cloud metadata
(169.254.169.254) or internal hosts. Before fetching we resolve the host and
reject any URL that maps to a non-public IP, and we refuse to follow redirects
(a public URL that 30x-redirects to an internal one).

Pure glue — no DB access. `requests`, `socket` and `spaces_service` are imported
at module level (not locally) so tests can monkeypatch
`document_fetch.requests.get` / `document_fetch.socket.getaddrinfo` /
`document_fetch.spaces_service.resolve_image_bytes` directly.
"""
import ipaddress
import os
import socket
from urllib.parse import urlparse

import requests

from core.services import spaces_service

DEFAULT_FILENAME = 'invoice.pdf'


def _assert_public_http_url(url: str) -> None:
    """Raise ValueError unless `url` is an http(s) URL whose host resolves
    exclusively to public (routable, non-internal) IP addresses.

    Blocks SSRF: cloud-metadata (link-local 169.254.0.0/16), loopback,
    RFC1918 private ranges, reserved/multicast/unspecified addresses. ALL
    resolved addresses must be public — a host that resolves to even one
    internal IP is rejected (defends against DNS rebinding returning a mix).
    """
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise ValueError('refusing to fetch non-public URL')

    host = parsed.hostname.rstrip('.').lower()

    try:
        infos = socket.getaddrinfo(host, None)
    except Exception as exc:  # unresolvable host, etc.
        raise ValueError('refusing to fetch non-public URL') from exc

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise ValueError('refusing to fetch non-public URL')


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
        _assert_public_http_url(file_url_str)
        # Redirects are NOT followed: a public URL could 30x to an internal host,
        # bypassing the pre-fetch IP guard above. Document links are direct
        # Spaces/presigned/file URLs, so a redirect is never expected here.
        response = requests.get(file_url_str, timeout=20, allow_redirects=False)
        if 300 <= getattr(response, 'status_code', 0) < 400:
            raise ValueError('refusing to follow redirect')
        response.raise_for_status()
        return response.content, filename

    return spaces_service.resolve_image_bytes(file_url), filename
