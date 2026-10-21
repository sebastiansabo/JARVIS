"""Unit tests for link_preview.rehost_image.

Facebook/Instagram CDN thumbnail URLs returned by Microlink are signed
and expire, so rehost_image downloads the image once and stores it
locally under `upload_dir`, returning its `/static/uploads/digest/<uuid>.<ext>`
URL (mirroring the chat image-upload convention in
jarvis/chat/routes.py:upload_image).

rehost_image fetches through `link_preview._GUARDED_SESSION` (the same
SSRF-guarded session scrape_opengraph uses) with `allow_redirects=False`
and a manual hop loop that re-validates each redirect `Location` with
`is_safe_url`, so the fetch seam mocked here is that session's `get` —
never the network. For the simple content-type / failure cases `is_safe_url`
is monkeypatched to True to isolate them from real DNS; the redirect and
guard-rejection cases instead drive the real `is_safe_url` (patching
`socket.getaddrinfo` to a public IP, like the scrape tests) so the SSRF
logic is genuinely exercised. All filesystem writes go to pytest's
`tmp_path`.
"""
import ipaddress
import os
import socket
import sys

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from chat.services import link_preview
from chat.services.link_preview import rehost_image


class _FakeResponse:
    """Minimal stand-in for requests.Response: status_code + headers +
    iter_content + close. Tracks close() so tests can assert the connection
    is released on every path."""

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


def _patch_get(monkeypatch, mock_get):
    """Replace the HTTP seam rehost_image uses (the guarded session's get)."""
    monkeypatch.setattr(link_preview._GUARDED_SESSION, "get", mock_get)


def _allow_safe_url(monkeypatch, result=True):
    monkeypatch.setattr(link_preview, "is_safe_url", lambda url: result)


def _patch_public_dns(monkeypatch, ip="93.184.216.34"):
    """Make hostname lookups resolve to one public IP (so is_safe_url runs
    offline), while IP-literal hosts pass through to the real resolver (a
    local parse) and resolve to themselves — matters for the redirect-to-
    metadata-IP case. Mirrors tests/test_link_preview_scrape.py."""
    real_getaddrinfo = socket.getaddrinfo

    def fake_getaddrinfo(host, *args, **kwargs):
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 0))]
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(link_preview.socket, "getaddrinfo", fake_getaddrinfo)


def test_rehost_saves_image_and_returns_static_url(monkeypatch, tmp_path):
    _allow_safe_url(monkeypatch)
    response = _FakeResponse(
        status_code=200,
        headers={"Content-Type": "image/jpeg"},
        body=b"\xff\xd8\xff\xe0fakejpeg",
    )
    mock_get = MagicMock(return_value=response)
    _patch_get(monkeypatch, mock_get)

    url = rehost_image("https://cdn.fbcdn.net/i.jpg", str(tmp_path))

    assert url is not None
    assert url.startswith("/static/uploads/digest/")
    assert url.endswith(".jpg")

    # The file was actually written under upload_dir with the returned name.
    filename = url.rsplit("/", 1)[-1]
    saved_path = tmp_path / filename
    assert saved_path.exists()
    assert saved_path.read_bytes() == b"\xff\xd8\xff\xe0fakejpeg"

    # Fetched through the guarded session, no redirects, with the shared UA.
    mock_get.assert_called_once_with(
        "https://cdn.fbcdn.net/i.jpg",
        timeout=4,
        allow_redirects=False,
        stream=True,
        headers=link_preview._REQUEST_HEADERS,
    )
    assert response.closed is True


def test_rehost_saves_png_with_matching_extension(monkeypatch, tmp_path):
    _allow_safe_url(monkeypatch)
    response = _FakeResponse(headers={"Content-Type": "image/png; charset=binary"}, body=b"pngbytes")
    _patch_get(monkeypatch, MagicMock(return_value=response))

    url = rehost_image("https://cdn.fbcdn.net/i.png", str(tmp_path))

    assert url is not None
    assert url.endswith(".png")


def test_rehost_rejects_non_image_content_type(monkeypatch, tmp_path):
    _allow_safe_url(monkeypatch)
    response = _FakeResponse(headers={"Content-Type": "text/html"}, body=b"<html></html>")
    _patch_get(monkeypatch, MagicMock(return_value=response))

    assert rehost_image("https://cdn.fbcdn.net/x", str(tmp_path)) is None
    assert list(tmp_path.iterdir()) == []
    assert response.closed is True


def test_rehost_rejects_image_subtype_outside_whitelist(monkeypatch, tmp_path):
    # image/svg+xml is image/* but not in the upload whitelist; must not
    # be written with an arbitrary/attacker-influenced extension.
    _allow_safe_url(monkeypatch)
    response = _FakeResponse(headers={"Content-Type": "image/svg+xml"}, body=b"<svg></svg>")
    _patch_get(monkeypatch, MagicMock(return_value=response))

    assert rehost_image("https://cdn.fbcdn.net/x.svg", str(tmp_path)) is None
    assert list(tmp_path.iterdir()) == []


def test_rehost_handles_fetch_failure(monkeypatch, tmp_path):
    _allow_safe_url(monkeypatch)
    _patch_get(
        monkeypatch,
        MagicMock(side_effect=link_preview.requests.exceptions.ConnectionError("boom")),
    )

    assert rehost_image("https://cdn.fbcdn.net/i.jpg", str(tmp_path)) is None
    assert list(tmp_path.iterdir()) == []


def test_rehost_follows_safe_redirect(monkeypatch, tmp_path):
    # A safe 302 is followed; the image at the final hop is re-hosted and
    # the intermediate response is released.
    _patch_public_dns(monkeypatch)
    redirect_response = _FakeResponse(status_code=302, location="https://cdn.example.com/final.jpg")
    final_response = _FakeResponse(
        status_code=200, headers={"Content-Type": "image/jpeg"}, body=b"jpegbytes",
    )
    mock_get = MagicMock(side_effect=[redirect_response, final_response])
    _patch_get(monkeypatch, mock_get)

    url = rehost_image("https://cdn.example.com/start.jpg", str(tmp_path))

    assert url is not None and url.endswith(".jpg")
    assert mock_get.call_count == 2
    assert redirect_response.closed is True  # intermediate hop released
    assert final_response.closed is True


def test_rehost_redirect_to_private_host_blocked(monkeypatch, tmp_path):
    # Redirect-following SSRF: a "safe" CDN URL 302s to the cloud metadata
    # endpoint. The guard must re-validate the Location and refuse to follow,
    # returning None and persisting nothing.
    _patch_public_dns(monkeypatch)
    redirect_response = _FakeResponse(
        status_code=302, location="http://169.254.169.254/latest/meta-data",
    )
    mock_get = MagicMock(return_value=redirect_response)
    _patch_get(monkeypatch, mock_get)

    assert rehost_image("https://cdn.example.com/start.jpg", str(tmp_path)) is None
    mock_get.assert_called_once()  # must stop at the unsafe hop, not follow it
    assert redirect_response.closed is True
    assert list(tmp_path.iterdir()) == []


def test_rehost_rejects_when_is_safe_url_fails(monkeypatch, tmp_path):
    _allow_safe_url(monkeypatch, result=False)
    mock_get = MagicMock()
    _patch_get(monkeypatch, mock_get)

    assert rehost_image("http://169.254.169.254/i.jpg", str(tmp_path)) is None
    mock_get.assert_not_called()


def test_rehost_rejects_non_http_scheme_before_any_check(monkeypatch, tmp_path):
    # Scheme guard runs first — neither is_safe_url nor the fetch should
    # ever be reached for a non-http(s) scheme.
    safe_url_mock = MagicMock(return_value=True)
    monkeypatch.setattr(link_preview, "is_safe_url", safe_url_mock)
    mock_get = MagicMock()
    _patch_get(monkeypatch, mock_get)

    assert rehost_image("file:///etc/passwd", str(tmp_path)) is None
    safe_url_mock.assert_not_called()
    mock_get.assert_not_called()
