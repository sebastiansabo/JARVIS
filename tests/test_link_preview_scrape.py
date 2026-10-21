"""Unit tests for link_preview.is_safe_url (SSRF guard) and
scrape_opengraph (in-house Open Graph scraper).

The HTTP call is always mocked — these tests never touch the network.
scrape_opengraph fetches through `link_preview._GUARDED_SESSION` (a
`requests.Session` whose mounted adapter re-checks the real peer IP at
connect time), so the fetch seam mocked here is that session's `get`.
DNS resolution (`socket.getaddrinfo`) is mocked to a public IP for
"public" test URLs via `_patch_public_dns`; IP-literal hosts (used in
the reject cases and the metadata-endpoint redirect target) resolve
through the real resolver, which is a local/offline parse for numeric
addresses and never hits the network either.

The private-URL case asserts the mocked HTTP call was never made — the
SSRF guard must run and reject *before* any fetch. The peer-IP recheck
(the TOCTOU/DNS-rebinding backstop) is covered directly against
`_assert_peer_is_safe` with a fake socket.
"""
import ipaddress
import socket
import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from chat.services import link_preview
from chat.services.link_preview import is_safe_url, scrape_opengraph


def _patch_public_dns(monkeypatch, ip="93.184.216.34"):
    """Make hostname lookups (e.g. "example.com") resolve to a single
    public IP, so tests don't depend on real DNS/network access.
    IP-literal hosts are passed through to the real resolver (a local
    parse, not a network call) so they still resolve to themselves —
    this matters for the redirect-to-metadata-IP test below.
    """
    real_getaddrinfo = socket.getaddrinfo

    def fake_getaddrinfo(host, *args, **kwargs):
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 0))]
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(link_preview.socket, "getaddrinfo", fake_getaddrinfo)


def _patch_get(monkeypatch, mock_get):
    """Replace the HTTP seam scrape_opengraph uses (the guarded session's
    get) so no real request is ever made."""
    monkeypatch.setattr(link_preview._GUARDED_SESSION, "get", mock_get)


class _FakeResponse:
    """Minimal stand-in for requests.Response, supporting only what
    scrape_opengraph touches: status_code, headers, iter_content, close.
    Tracks whether close() was called so tests can assert connections are
    released.
    """

    def __init__(self, status_code=200, headers=None, body=b"", location=None):
        self.status_code = status_code
        self.headers = dict(headers or {})
        if location is not None:
            self.headers.setdefault("Location", location)
        self._body = body
        self.closed = False

    def iter_content(self, chunk_size=8192):
        body = self._body
        for i in range(0, len(body), chunk_size):
            yield body[i:i + chunk_size]

    def close(self):
        self.closed = True


def test_is_safe_url_rejects_private_and_nonhttp():
    for u in ["http://localhost/x", "http://127.0.0.1", "http://10.0.0.5",
              "http://169.254.169.254/", "ftp://a.com", "file:///etc/passwd"]:
        assert is_safe_url(u) is False, u


def test_is_safe_url_rejects_cgnat(monkeypatch):
    # RFC 6598 CGNAT (100.64.0.0/10) — Tailscale / some clouds. Not flagged
    # by is_private/is_loopback/etc., only caught by the `not is_global` rule.
    monkeypatch.setattr(
        link_preview.socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ("100.64.0.1", 0))],
    )
    assert is_safe_url("https://sneaky.example/x") is False


def test_is_safe_url_accepts_public(monkeypatch):
    _patch_public_dns(monkeypatch)
    assert is_safe_url("https://example.com/a") is True


def test_scrape_parses_og_tags(monkeypatch):
    _patch_public_dns(monkeypatch)
    html = (b'<html><head>'
            b'<meta property="og:title" content="T">'
            b'<meta property="og:image" content="https://cdn/i.jpg">'
            b'<meta property="og:site_name" content="S">'
            b'</head></html>')
    response = _FakeResponse(
        status_code=200,
        headers={"Content-Type": "text/html; charset=utf-8"},
        body=html,
    )
    mock_get = MagicMock(return_value=response)
    _patch_get(monkeypatch, mock_get)

    r = scrape_opengraph("https://example.com")

    assert r["title"] == "T"
    assert r["image"] == "https://cdn/i.jpg"
    assert r["site_name"] == "S"
    assert r["source"] == "scrape"
    assert r["url"] == "https://example.com"
    mock_get.assert_called_once()
    assert response.closed is True  # connection released on the happy path


def test_scrape_missing_image_returns_none_image(monkeypatch):
    _patch_public_dns(monkeypatch)
    # og:title present (wins over the <title> fallback), no og:image at all.
    html = (b'<html><head>'
            b'<title>Fallback Title</title>'
            b'<meta property="og:title" content="T">'
            b'</head></html>')
    response = _FakeResponse(
        status_code=200,
        headers={"Content-Type": "text/html"},
        body=html,
    )
    _patch_get(monkeypatch, MagicMock(return_value=response))

    r = scrape_opengraph("https://example.com")

    assert r["image"] is None
    assert r["title"] == "T"


def test_scrape_title_falls_back_to_title_tag(monkeypatch):
    _patch_public_dns(monkeypatch)
    html = b'<html><head><title>Fallback Title</title></head></html>'
    response = _FakeResponse(
        status_code=200,
        headers={"Content-Type": "text/html"},
        body=html,
    )
    _patch_get(monkeypatch, MagicMock(return_value=response))

    r = scrape_opengraph("https://example.com")

    assert r["title"] == "Fallback Title"
    assert r["image"] is None


def test_scrape_description_falls_back_to_meta_description(monkeypatch):
    _patch_public_dns(monkeypatch)
    # No og:description; the <meta name="description"> supplies it.
    html = (b'<html><head>'
            b'<meta property="og:title" content="T">'
            b'<meta name="description" content="Plain meta description">'
            b'</head></html>')
    response = _FakeResponse(
        status_code=200,
        headers={"Content-Type": "text/html"},
        body=html,
    )
    _patch_get(monkeypatch, MagicMock(return_value=response))

    r = scrape_opengraph("https://example.com")

    assert r["description"] == "Plain meta description"


def test_scrape_site_name_falls_back_to_host(monkeypatch):
    _patch_public_dns(monkeypatch)
    # No og:site_name -> site_name falls back to the URL's hostname.
    html = b'<html><head><meta property="og:title" content="T"></head></html>'
    response = _FakeResponse(
        status_code=200,
        headers={"Content-Type": "text/html"},
        body=html,
    )
    _patch_get(monkeypatch, MagicMock(return_value=response))

    r = scrape_opengraph("https://example.com/some/path")

    assert r["site_name"] == "example.com"


def test_scrape_body_truncated_at_cap(monkeypatch):
    _patch_public_dns(monkeypatch)
    # og:title sits at the very front; og:image is placed *after* the 2 MiB
    # cap behind >2 MiB of filler, so a correctly truncated read keeps the
    # title but never sees the image.
    head = b'<html><head><meta property="og:title" content="Early">'
    filler = b'<!-- ' + b'x' * link_preview._MAX_BODY_BYTES + b' -->'
    tail = b'<meta property="og:image" content="https://cdn/late.jpg"></head></html>'
    response = _FakeResponse(
        status_code=200,
        headers={"Content-Type": "text/html"},
        body=head + filler + tail,
    )
    _patch_get(monkeypatch, MagicMock(return_value=response))

    r = scrape_opengraph("https://example.com")

    assert r["title"] == "Early"
    assert r["image"] is None  # image tag was beyond the 2 MiB cap, truncated


def test_scrape_non_html_returns_none(monkeypatch):
    _patch_public_dns(monkeypatch)
    response = _FakeResponse(
        status_code=200,
        headers={"Content-Type": "application/pdf"},
        body=b"%PDF-1.4 ...",
    )
    _patch_get(monkeypatch, MagicMock(return_value=response))

    assert scrape_opengraph("https://example.com/f.pdf") is None
    assert response.closed is True  # connection released on the bail path


def test_scrape_private_url_does_not_fetch(monkeypatch):
    mock_get = MagicMock()
    _patch_get(monkeypatch, mock_get)

    assert scrape_opengraph("http://10.0.0.1") is None
    mock_get.assert_not_called()


def test_scrape_follows_safe_redirect(monkeypatch):
    _patch_public_dns(monkeypatch)
    html = b'<html><head><meta property="og:title" content="Redirected"></head></html>'
    redirect_response = _FakeResponse(
        status_code=302, location="https://example.com/final",
    )
    final_response = _FakeResponse(
        status_code=200, headers={"Content-Type": "text/html"}, body=html,
    )
    mock_get = MagicMock(side_effect=[redirect_response, final_response])
    _patch_get(monkeypatch, mock_get)

    r = scrape_opengraph("https://example.com/start")

    assert r["title"] == "Redirected"
    assert mock_get.call_count == 2
    assert redirect_response.closed is True  # intermediate hop released
    assert final_response.closed is True


def test_scrape_redirect_to_private_url_blocked(monkeypatch):
    # Classic SSRF: a "safe" URL 302s to the cloud metadata endpoint.
    _patch_public_dns(monkeypatch)
    redirect_response = _FakeResponse(
        status_code=302, location="http://169.254.169.254/latest/meta-data",
    )
    mock_get = MagicMock(return_value=redirect_response)
    _patch_get(monkeypatch, mock_get)

    assert scrape_opengraph("https://example.com/start") is None
    mock_get.assert_called_once()  # must stop at the unsafe hop, not follow it
    assert redirect_response.closed is True


def test_scrape_exceeding_redirect_budget_returns_none(monkeypatch):
    _patch_public_dns(monkeypatch)
    redirect_response = _FakeResponse(
        status_code=302, location="https://example.com/next",
    )
    mock_get = MagicMock(return_value=redirect_response)
    _patch_get(monkeypatch, mock_get)

    assert scrape_opengraph("https://example.com/start") is None
    assert mock_get.call_count == 4  # initial fetch + 3 redirect hops, cap at 3


def test_scrape_network_error_returns_none(monkeypatch):
    _patch_public_dns(monkeypatch)
    mock_get = MagicMock(side_effect=RuntimeError("boom"))
    _patch_get(monkeypatch, mock_get)

    assert scrape_opengraph("https://example.com") is None


def test_scrape_image_with_javascript_scheme_dropped(monkeypatch):
    # Spec requirement: the image is only loaded via <img src> after
    # validating an http(s) scheme. A javascript: og:image must come
    # back as None, not pass through to the client untouched.
    _patch_public_dns(monkeypatch)
    html = (b'<html><head>'
            b'<meta property="og:title" content="T">'
            b'<meta property="og:image" content="javascript:alert(1)">'
            b'</head></html>')
    response = _FakeResponse(
        status_code=200,
        headers={"Content-Type": "text/html"},
        body=html,
    )
    _patch_get(monkeypatch, MagicMock(return_value=response))

    r = scrape_opengraph("https://example.com")

    assert r["image"] is None


def test_scrape_image_with_data_scheme_dropped(monkeypatch):
    _patch_public_dns(monkeypatch)
    html = (b'<html><head>'
            b'<meta property="og:title" content="T">'
            b'<meta property="og:image" content="data:image/png;base64,abcd">'
            b'</head></html>')
    response = _FakeResponse(
        status_code=200,
        headers={"Content-Type": "text/html"},
        body=html,
    )
    _patch_get(monkeypatch, MagicMock(return_value=response))

    r = scrape_opengraph("https://example.com")

    assert r["image"] is None


def test_scrape_image_with_relative_path_dropped(monkeypatch):
    _patch_public_dns(monkeypatch)
    html = (b'<html><head>'
            b'<meta property="og:title" content="T">'
            b'<meta property="og:image" content="/relative/i.jpg">'
            b'</head></html>')
    response = _FakeResponse(
        status_code=200,
        headers={"Content-Type": "text/html"},
        body=html,
    )
    _patch_get(monkeypatch, MagicMock(return_value=response))

    r = scrape_opengraph("https://example.com")

    assert r["image"] is None


def test_scrape_image_with_https_scheme_kept(monkeypatch):
    _patch_public_dns(monkeypatch)
    html = (b'<html><head>'
            b'<meta property="og:title" content="T">'
            b'<meta property="og:image" content="https://cdn.example.com/i.jpg">'
            b'</head></html>')
    response = _FakeResponse(
        status_code=200,
        headers={"Content-Type": "text/html"},
        body=html,
    )
    _patch_get(monkeypatch, MagicMock(return_value=response))

    r = scrape_opengraph("https://example.com")

    assert r["image"] == "https://cdn.example.com/i.jpg"


def test_is_safe_url_rejects_malformed_idna_unicode_error(monkeypatch):
    # socket.getaddrinfo raises UnicodeError (not gaierror) for a malformed
    # IDNA host. is_safe_url must fail closed (return False) rather than
    # let the exception propagate out of the SSRF guard.
    monkeypatch.setattr(
        link_preview.socket, "getaddrinfo",
        MagicMock(side_effect=UnicodeError("label empty or too long")),
    )
    assert is_safe_url("https://xn--bad.example/x") is False


def test_connect_guard_refuses_non_public_peer():
    """TOCTOU backstop: even if DNS said "public", the transport refuses
    once the real connected peer IP is private/CGNAT/etc."""

    class _FakeSock:
        def __init__(self, ip):
            self._ip = ip

        def getpeername(self):
            return (self._ip, 443)

    for bad in ["10.0.0.5", "127.0.0.1", "169.254.169.254", "100.64.0.1"]:
        with pytest.raises(link_preview._UnsafePeerError):
            link_preview._assert_peer_is_safe(_FakeSock(bad))

    # A genuine public peer passes through without raising.
    link_preview._assert_peer_is_safe(_FakeSock("93.184.216.34"))
