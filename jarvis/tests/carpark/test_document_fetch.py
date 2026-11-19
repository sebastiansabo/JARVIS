"""Unit tests for the document-bytes fetch helper.

`fetch_document_bytes` is the single entry point the invoice-OCR flow uses to
turn a `carpark_vehicle_documents` row into raw bytes, regardless of where the
file actually lives: a DigitalOcean Spaces key (or legacy base64 data: URI)
via `spaces_service.resolve_image_bytes`, or a plain http(s) URL via
`requests.get`. Pure/monkeypatched — no real network or Spaces calls.

The http(s) branch is SSRF-hardened: before fetching, the host is resolved and
rejected if any address is non-public, and redirects are refused. Tests
monkeypatch `document_fetch.socket.getaddrinfo` (alongside `requests.get`) to
drive the guard deterministically without touching DNS.
"""
import types

import pytest

from carpark.services import document_fetch

# A routable, public IPv4 (example.com's address) — passes the SSRF guard.
PUBLIC_IP = '93.184.216.34'


def _allow_public_dns(monkeypatch, ip=PUBLIC_IP):
    """Make the SSRF guard see `ip` as the only resolved address for any host."""
    monkeypatch.setattr(
        document_fetch.socket, 'getaddrinfo',
        lambda host, port, *a, **k: [(2, 1, 6, '', (ip, 0))])


def _resp(content=b'', status_code=200, **extra):
    ns = types.SimpleNamespace(
        status_code=status_code, content=content,
        raise_for_status=lambda: None, headers={})
    for k, v in extra.items():
        setattr(ns, k, v)
    return ns


def test_spaces_key_uses_resolve_image_bytes(monkeypatch):
    monkeypatch.setattr(document_fetch.spaces_service, 'resolve_image_bytes', lambda v: b'PDFBYTES')
    data, name = document_fetch.fetch_document_bytes({'file_url': 'private/carpark/5/doc-1.pdf'})
    assert data == b'PDFBYTES' and name.endswith('.pdf')


def test_http_url_uses_requests(monkeypatch):
    _allow_public_dns(monkeypatch)
    monkeypatch.setattr(
        document_fetch.requests, 'get',
        lambda url, timeout=20, allow_redirects=False: _resp(content=b'IMG'))
    data, _ = document_fetch.fetch_document_bytes({'file_url': 'https://x/inv.pdf'})
    assert data == b'IMG'


def test_no_file_raises():
    with pytest.raises(ValueError):
        document_fetch.fetch_document_bytes({'dms_document_id': 7, 'file_url': None})


def test_missing_file_url_key_raises():
    with pytest.raises(ValueError):
        document_fetch.fetch_document_bytes({})


def test_data_uri_routes_to_resolve_image_bytes_not_requests(monkeypatch):
    # A legacy base64 data: URI is not http(s) — must go through spaces_service,
    # never requests, even though it technically "starts with" a scheme-like prefix.
    monkeypatch.setattr(document_fetch.spaces_service, 'resolve_image_bytes', lambda v: b'DATAURI')

    def _boom(*a, **k):
        raise AssertionError('requests.get should not be called for a data: URI')
    monkeypatch.setattr(document_fetch.requests, 'get', _boom)

    data, name = document_fetch.fetch_document_bytes({'file_url': 'data:application/pdf;base64,AAAA'})
    assert data == b'DATAURI'
    assert name == 'invoice.pdf'


def test_https_is_case_insensitive_and_uppercase_scheme_routes_to_requests(monkeypatch):
    _allow_public_dns(monkeypatch)
    monkeypatch.setattr(
        document_fetch.requests, 'get',
        lambda url, timeout=20, allow_redirects=False: _resp(content=b'UP'))
    data, name = document_fetch.fetch_document_bytes({'file_url': 'HTTPS://X/INV.JPG'})
    assert data == b'UP'
    assert name.endswith('.JPG')


def test_http_raise_for_status_propagates(monkeypatch):
    _allow_public_dns(monkeypatch)

    class Boom(Exception):
        pass

    def _raise():
        raise Boom('bad status')

    monkeypatch.setattr(
        document_fetch.requests, 'get',
        lambda url, timeout=20, allow_redirects=False: _resp(status_code=200, raise_for_status=_raise))

    with pytest.raises(Boom):
        document_fetch.fetch_document_bytes({'file_url': 'https://x/broken.pdf'})


def test_filename_defaults_when_no_extension_in_url(monkeypatch):
    monkeypatch.setattr(document_fetch.spaces_service, 'resolve_image_bytes', lambda v: b'X')
    _, name = document_fetch.fetch_document_bytes({'file_url': 'private/carpark/5/doc-no-ext'})
    assert name == 'invoice.pdf'


def test_filename_derived_from_basename_strips_query_string(monkeypatch):
    _allow_public_dns(monkeypatch)
    monkeypatch.setattr(
        document_fetch.requests, 'get',
        lambda url, timeout=20, allow_redirects=False: _resp(content=b'X'))
    _, name = document_fetch.fetch_document_bytes({'file_url': 'https://x/path/to/invoice-42.png?sig=abc'})
    assert name == 'invoice-42.png'


# ---------------------------------------------------------------------------
# SSRF hardening
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('bad_ip', ['127.0.0.1', '10.0.0.1', '169.254.169.254'])
def test_private_ip_host_is_blocked(monkeypatch, bad_ip):
    # Host resolves to a non-public address -> rejected BEFORE any network I/O.
    monkeypatch.setattr(
        document_fetch.socket, 'getaddrinfo',
        lambda host, port, *a, **k: [(2, 1, 6, '', (bad_ip, 0))])

    def _must_not_fetch(*a, **k):
        raise AssertionError('requests.get must NOT be called for a blocked host')
    monkeypatch.setattr(document_fetch.requests, 'get', _must_not_fetch)

    with pytest.raises(ValueError):
        document_fetch.fetch_document_bytes({'file_url': 'http://evil.test/x.pdf'})


def test_mixed_public_and_private_dns_is_blocked(monkeypatch):
    # DNS-rebinding defense: if ANY resolved address is internal, reject.
    monkeypatch.setattr(
        document_fetch.socket, 'getaddrinfo',
        lambda host, port, *a, **k: [
            (2, 1, 6, '', (PUBLIC_IP, 0)),
            (2, 1, 6, '', ('10.0.0.1', 0)),
        ])
    monkeypatch.setattr(
        document_fetch.requests, 'get',
        lambda *a, **k: (_ for _ in ()).throw(AssertionError('must not fetch')))

    with pytest.raises(ValueError):
        document_fetch.fetch_document_bytes({'file_url': 'http://rebind.test/x.pdf'})


def test_unresolvable_host_raises_valueerror(monkeypatch):
    import socket as _socket

    def _boom(host, port, *a, **k):
        raise _socket.gaierror('name or service not known')
    monkeypatch.setattr(document_fetch.socket, 'getaddrinfo', _boom)

    with pytest.raises(ValueError):
        document_fetch.fetch_document_bytes({'file_url': 'http://nope.invalid/x.pdf'})


def test_redirect_is_refused(monkeypatch):
    _allow_public_dns(monkeypatch)
    monkeypatch.setattr(
        document_fetch.requests, 'get',
        lambda url, timeout=20, allow_redirects=False: _resp(
            status_code=302, headers={'Location': 'http://10.0.0.1/'}))

    with pytest.raises(ValueError):
        document_fetch.fetch_document_bytes({'file_url': 'https://x/redirects.pdf'})
