"""Unit tests for link_preview.is_safe_url (SSRF guard) and
scrape_opengraph (in-house Open Graph scraper).

`requests.get` is always mocked — these tests never touch the network.
DNS resolution (`socket.getaddrinfo`) is mocked to a public IP for
"public" test URLs via `_patch_public_dns`; IP-literal hosts (used in
the reject cases, and the metadata-endpoint redirect target) resolve
through the real resolver, which is a local/offline parse for numeric
addresses and never hits the network either.

The private-URL case asserts the mocked `requests.get` was never
called — the SSRF guard must run and reject *before* any fetch.
"""
import ipaddress
import socket
import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from unittest.mock import MagicMock

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


class _FakeResponse:
    """Minimal stand-in for requests.Response, supporting only what
    scrape_opengraph touches: status_code, headers, iter_content, close.
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
    monkeypatch.setattr(link_preview.requests, "get", mock_get)

    r = scrape_opengraph("https://example.com")

    assert r["title"] == "T"
    assert r["image"] == "https://cdn/i.jpg"
    assert r["site_name"] == "S"
    assert r["source"] == "scrape"
    assert r["url"] == "https://example.com"
    mock_get.assert_called_once()


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
    monkeypatch.setattr(link_preview.requests, "get", MagicMock(return_value=response))

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
    monkeypatch.setattr(link_preview.requests, "get", MagicMock(return_value=response))

    r = scrape_opengraph("https://example.com")

    assert r["title"] == "Fallback Title"
    assert r["image"] is None


def test_scrape_non_html_returns_none(monkeypatch):
    _patch_public_dns(monkeypatch)
    response = _FakeResponse(
        status_code=200,
        headers={"Content-Type": "application/pdf"},
        body=b"%PDF-1.4 ...",
    )
    monkeypatch.setattr(link_preview.requests, "get", MagicMock(return_value=response))

    assert scrape_opengraph("https://example.com/f.pdf") is None


def test_scrape_private_url_does_not_fetch(monkeypatch):
    mock_get = MagicMock()
    monkeypatch.setattr(link_preview.requests, "get", mock_get)

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
    monkeypatch.setattr(link_preview.requests, "get", mock_get)

    r = scrape_opengraph("https://example.com/start")

    assert r["title"] == "Redirected"
    assert mock_get.call_count == 2


def test_scrape_redirect_to_private_url_blocked(monkeypatch):
    # Classic SSRF: a "safe" URL 302s to the cloud metadata endpoint.
    _patch_public_dns(monkeypatch)
    redirect_response = _FakeResponse(
        status_code=302, location="http://169.254.169.254/latest/meta-data",
    )
    mock_get = MagicMock(return_value=redirect_response)
    monkeypatch.setattr(link_preview.requests, "get", mock_get)

    assert scrape_opengraph("https://example.com/start") is None
    mock_get.assert_called_once()  # must stop at the unsafe hop, not follow it


def test_scrape_exceeding_redirect_budget_returns_none(monkeypatch):
    _patch_public_dns(monkeypatch)
    redirect_response = _FakeResponse(
        status_code=302, location="https://example.com/next",
    )
    mock_get = MagicMock(return_value=redirect_response)
    monkeypatch.setattr(link_preview.requests, "get", mock_get)

    assert scrape_opengraph("https://example.com/start") is None
    assert mock_get.call_count == 4  # initial fetch + 3 redirect hops, cap at 3


def test_scrape_network_error_returns_none(monkeypatch):
    _patch_public_dns(monkeypatch)
    mock_get = MagicMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(link_preview.requests, "get", mock_get)

    assert scrape_opengraph("https://example.com") is None
