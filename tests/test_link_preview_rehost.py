"""Unit tests for link_preview.rehost_image.

Facebook/Instagram CDN thumbnail URLs returned by Microlink are signed
and expire, so rehost_image downloads the image once and stores it
locally under `upload_dir`, returning its `/static/uploads/digest/<uuid>.<ext>`
URL (mirroring the chat image-upload convention in
jarvis/chat/routes.py:upload_image).

The network is always mocked (`requests.get`, the same plain, un-guarded
seam fetch_via_microlink uses — see test_link_preview_resolve.py) and the
filesystem write goes to pytest's `tmp_path`, so these tests never touch
the network or the real uploads directory. `is_safe_url` is monkeypatched
to True for the happy-path / content-type / fetch-failure cases, isolating
each test from real DNS; the scheme-rejection test instead asserts the
scheme guard fires *before* is_safe_url or requests.get are ever called.
"""
import os
import sys

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from chat.services import link_preview
from chat.services.link_preview import rehost_image


class _FakeResponse:
    """Minimal stand-in for requests.Response: headers + iter_content + close."""

    def __init__(self, headers=None, body=b""):
        self.headers = dict(headers or {})
        self._body = body
        self.closed = False

    def iter_content(self, chunk_size=8192):
        body = self._body
        for i in range(0, len(body), chunk_size):
            yield body[i:i + chunk_size]

    def close(self):
        self.closed = True


def _allow_safe_url(monkeypatch, result=True):
    monkeypatch.setattr(link_preview, "is_safe_url", lambda url: result)


def test_rehost_saves_image_and_returns_static_url(monkeypatch, tmp_path):
    _allow_safe_url(monkeypatch)
    response = _FakeResponse(headers={"Content-Type": "image/jpeg"}, body=b"\xff\xd8\xff\xe0fakejpeg")
    mock_get = MagicMock(return_value=response)
    monkeypatch.setattr(link_preview.requests, "get", mock_get)

    url = rehost_image("https://cdn.fbcdn.net/i.jpg", str(tmp_path))

    assert url is not None
    assert url.startswith("/static/uploads/digest/")
    assert url.endswith(".jpg")

    # The file was actually written under upload_dir with the returned name.
    filename = url.rsplit("/", 1)[-1]
    saved_path = tmp_path / filename
    assert saved_path.exists()
    assert saved_path.read_bytes() == b"\xff\xd8\xff\xe0fakejpeg"

    mock_get.assert_called_once_with("https://cdn.fbcdn.net/i.jpg", timeout=4, stream=True)
    assert response.closed is True


def test_rehost_saves_png_with_matching_extension(monkeypatch, tmp_path):
    _allow_safe_url(monkeypatch)
    response = _FakeResponse(headers={"Content-Type": "image/png; charset=binary"}, body=b"pngbytes")
    monkeypatch.setattr(link_preview.requests, "get", MagicMock(return_value=response))

    url = rehost_image("https://cdn.fbcdn.net/i.png", str(tmp_path))

    assert url is not None
    assert url.endswith(".png")


def test_rehost_rejects_non_image_content_type(monkeypatch, tmp_path):
    _allow_safe_url(monkeypatch)
    response = _FakeResponse(headers={"Content-Type": "text/html"}, body=b"<html></html>")
    monkeypatch.setattr(link_preview.requests, "get", MagicMock(return_value=response))

    assert rehost_image("https://cdn.fbcdn.net/x", str(tmp_path)) is None
    assert list(tmp_path.iterdir()) == []


def test_rehost_rejects_image_subtype_outside_whitelist(monkeypatch, tmp_path):
    # image/svg+xml is image/* but not in the upload whitelist; must not
    # be written with an arbitrary/attacker-influenced extension.
    _allow_safe_url(monkeypatch)
    response = _FakeResponse(headers={"Content-Type": "image/svg+xml"}, body=b"<svg></svg>")
    monkeypatch.setattr(link_preview.requests, "get", MagicMock(return_value=response))

    assert rehost_image("https://cdn.fbcdn.net/x.svg", str(tmp_path)) is None
    assert list(tmp_path.iterdir()) == []


def test_rehost_handles_fetch_failure(monkeypatch, tmp_path):
    _allow_safe_url(monkeypatch)
    monkeypatch.setattr(
        link_preview.requests, "get",
        MagicMock(side_effect=link_preview.requests.exceptions.ConnectionError("boom")),
    )

    assert rehost_image("https://cdn.fbcdn.net/i.jpg", str(tmp_path)) is None


def test_rehost_rejects_when_is_safe_url_fails(monkeypatch, tmp_path):
    _allow_safe_url(monkeypatch, result=False)
    mock_get = MagicMock()
    monkeypatch.setattr(link_preview.requests, "get", mock_get)

    assert rehost_image("http://169.254.169.254/i.jpg", str(tmp_path)) is None
    mock_get.assert_not_called()


def test_rehost_rejects_non_http_scheme_before_any_check(monkeypatch, tmp_path):
    # Scheme guard runs first — neither is_safe_url nor requests.get should
    # ever be reached for a non-http(s) scheme.
    safe_url_mock = MagicMock(return_value=True)
    monkeypatch.setattr(link_preview, "is_safe_url", safe_url_mock)
    mock_get = MagicMock()
    monkeypatch.setattr(link_preview.requests, "get", mock_get)

    assert rehost_image("file:///etc/passwd", str(tmp_path)) is None
    safe_url_mock.assert_not_called()
    mock_get.assert_not_called()
