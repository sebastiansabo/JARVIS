"""Unit tests for the document-bytes fetch helper.

`fetch_document_bytes` is the single entry point the invoice-OCR flow uses to
turn a `carpark_vehicle_documents` row into raw bytes, regardless of where the
file actually lives: a DigitalOcean Spaces key (or legacy base64 data: URI)
via `spaces_service.resolve_image_bytes`, or a plain http(s) URL via
`requests.get`. Pure/monkeypatched — no real network or Spaces calls.
"""
import types

import pytest

from carpark.services import document_fetch


def test_spaces_key_uses_resolve_image_bytes(monkeypatch):
    monkeypatch.setattr(document_fetch.spaces_service, 'resolve_image_bytes', lambda v: b'PDFBYTES')
    data, name = document_fetch.fetch_document_bytes({'file_url': 'private/carpark/5/doc-1.pdf'})
    assert data == b'PDFBYTES' and name.endswith('.pdf')


def test_http_url_uses_requests(monkeypatch):
    monkeypatch.setattr(
        document_fetch.requests, 'get',
        lambda url, timeout=20: types.SimpleNamespace(content=b'IMG', raise_for_status=lambda: None))
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
    monkeypatch.setattr(
        document_fetch.requests, 'get',
        lambda url, timeout=20: types.SimpleNamespace(content=b'UP', raise_for_status=lambda: None))
    data, name = document_fetch.fetch_document_bytes({'file_url': 'HTTPS://X/INV.JPG'})
    assert data == b'UP'
    assert name.endswith('.JPG')


def test_http_raise_for_status_propagates(monkeypatch):
    class Boom(Exception):
        pass

    def _raise():
        raise Boom('bad status')

    monkeypatch.setattr(
        document_fetch.requests, 'get',
        lambda url, timeout=20: types.SimpleNamespace(content=b'', raise_for_status=_raise))

    with pytest.raises(Boom):
        document_fetch.fetch_document_bytes({'file_url': 'https://x/broken.pdf'})


def test_filename_defaults_when_no_extension_in_url(monkeypatch):
    monkeypatch.setattr(document_fetch.spaces_service, 'resolve_image_bytes', lambda v: b'X')
    _, name = document_fetch.fetch_document_bytes({'file_url': 'private/carpark/5/doc-no-ext'})
    assert name == 'invoice.pdf'


def test_filename_derived_from_basename_strips_query_string(monkeypatch):
    monkeypatch.setattr(
        document_fetch.requests, 'get',
        lambda url, timeout=20: types.SimpleNamespace(content=b'X', raise_for_status=lambda: None))
    _, name = document_fetch.fetch_document_bytes({'file_url': 'https://x/path/to/invoice-42.png?sig=abc'})
    assert name == 'invoice-42.png'
