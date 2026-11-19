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


# CGNAT / shared address space (RFC 6598). None of the six `ipaddress`
# is_* flags cover it, so we check membership explicitly.
_CGNAT_NET = ipaddress.ip_network('100.64.0.0/10')


def _assert_public_http_url(url: str) -> None:
    """Raise ValueError unless `url` is an http(s) URL whose host resolves
    exclusively to public (routable, non-internal) IP addresses.

    Blocks SSRF: cloud-metadata (link-local 169.254.0.0/16), loopback,
    RFC1918 private ranges, CGNAT (100.64.0.0/10), reserved/multicast/
    unspecified addresses. ALL resolved addresses must be public — a host that
    resolves to even one internal IP is rejected.

    Defense-in-depth against *parser divergence*: `urllib.parse` and the
    `requests`/`urllib3` URL parser disagree on where the authority ends when
    the raw string contains a backslash, whitespace/control char, or userinfo
    (`user@host`). e.g. `http://169.254.169.254\\@good.example.com/` — urlparse
    reads the host as `good.example.com` (which we'd validate as public) while
    `requests` actually connects to `169.254.169.254`. Rather than rely on the
    two parsers agreeing, we reject these ambiguous inputs outright up front —
    they never appear in legitimate document URLs.
    """
    # 1. Reject chars that make urlparse and urllib3 disagree, BEFORE parsing:
    #    a backslash, or any whitespace/control char (incl. tab/newline/DEL).
    for ch in url:
        if ch == '\\' or ord(ch) < 0x21 or ord(ch) == 0x7f:
            raise ValueError('malformed URL')

    parsed = urlparse(url)

    # 2. Reject userinfo in the authority — `user@host` is the core confusion
    #    vector and never present in a real document/invoice URL.
    if parsed.username is not None or '@' in parsed.netloc:
        raise ValueError('malformed URL')

    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise ValueError('refusing to fetch non-public URL')

    host = parsed.hostname.rstrip('.').lower()

    # 3. Resolve and reject any non-public address.
    #    KNOWN, TRACKED residual (do NOT mark resolved): this validates the
    #    name once here, then `requests` re-resolves it at connect time — a
    #    DNS-rebinding window remains. Fully closing it needs pinning the
    #    connection to the validated IP, which conflicts with https presigned
    #    signatures, so it's out of scope for this helper and carried in the
    #    ledger into Task 5.
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception as exc:  # unresolvable host, etc.
        raise ValueError('refusing to fetch non-public URL') from exc

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        # Unwrap IPv4-mapped IPv6 (::ffff:a.b.c.d) to its embedded IPv4 so the
        # checks are representation-agnostic. The is_* flags already delegate
        # for mapped addresses, but the hand-rolled CGNAT membership below is
        # version-specific (`v6 in v4_net` is silently False), so an attacker
        # could otherwise smuggle 100.64.0.0/10 past us as ::ffff:100.64.0.1.
        mapped = getattr(ip, 'ipv4_mapped', None)
        if mapped is not None:
            ip = mapped
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified
                or ip in _CGNAT_NET):
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
