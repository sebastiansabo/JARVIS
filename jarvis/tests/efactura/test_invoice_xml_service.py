"""Tests for the preview XML resolver (stored copy vs on-demand ANAF descarcare)."""
import io
import zipfile

from core.connectors.efactura.repositories import EFacturaInvoiceRepository
from core.connectors.efactura.services import invoice_xml_service as svc
from core.connectors.efactura.services import efactura_service as efsvc


def _zip_with(invoice_xml: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('semnatura_123.xml', '<sig/>')   # signature — must be skipped
        zf.writestr('4012345.xml', invoice_xml)       # the invoice — must be picked
        zf.writestr('4012345.p7s', 'x')               # detached signature — must be skipped
    return buf.getvalue()


def _fake_efactura_service(client):
    return lambda: type('S', (), {'get_anaf_client': lambda self, cif: client})()


# ── extract_invoice_xml_from_zip ────────────────────────────────────────────

def test_extract_skips_signature_files():
    assert svc.extract_invoice_xml_from_zip(_zip_with('<Invoice/>')) == '<Invoice/>'


def test_extract_returns_none_when_only_signatures():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('semnatura_1.xml', '<sig/>')
    assert svc.extract_invoice_xml_from_zip(buf.getvalue()) is None


# ── get_invoice_xml_by_jarvis_id ────────────────────────────────────────────

def test_stored_xml_returned(monkeypatch):
    monkeypatch.setattr(EFacturaInvoiceRepository, 'get_xml_source_info',
                        lambda self, jid: {'id': 5, 'cif_owner': 'RO1', 'xml_content': '<Invoice/>', 'download_id': 'D1'})
    assert svc.get_invoice_xml_by_jarvis_id(99) == '<Invoice/>'


def test_missing_xml_fetches_from_anaf_and_caches(monkeypatch):
    saved = {}
    monkeypatch.setattr(EFacturaInvoiceRepository, 'get_xml_source_info',
                        lambda self, jid: {'id': 5, 'cif_owner': 'RO1', 'xml_content': None, 'download_id': 'D1'})
    monkeypatch.setattr(EFacturaInvoiceRepository, 'save_xml_content',
                        lambda self, iid, xml: saved.update(id=iid, xml=xml))
    client = type('C', (), {'download_message': lambda self, did: _zip_with('<Invoice>fetched</Invoice>')})()
    monkeypatch.setattr(efsvc, 'EFacturaService', _fake_efactura_service(client))

    assert svc.get_invoice_xml_by_jarvis_id(99) == '<Invoice>fetched</Invoice>'
    assert saved == {'id': 5, 'xml': '<Invoice>fetched</Invoice>'}   # cached back


def test_no_download_id_returns_none(monkeypatch):
    monkeypatch.setattr(EFacturaInvoiceRepository, 'get_xml_source_info',
                        lambda self, jid: {'id': 5, 'cif_owner': 'RO1', 'xml_content': None, 'download_id': None})
    assert svc.get_invoice_xml_by_jarvis_id(99) is None


def test_anaf_failure_returns_none(monkeypatch):
    monkeypatch.setattr(EFacturaInvoiceRepository, 'get_xml_source_info',
                        lambda self, jid: {'id': 5, 'cif_owner': 'RO1', 'xml_content': None, 'download_id': 'D1'})

    class Boom:
        def get_anaf_client(self, cif):
            raise RuntimeError('ANAF 503')
    monkeypatch.setattr(efsvc, 'EFacturaService', lambda: Boom())
    assert svc.get_invoice_xml_by_jarvis_id(99) is None


def test_no_efactura_record_returns_none(monkeypatch):
    monkeypatch.setattr(EFacturaInvoiceRepository, 'get_xml_source_info', lambda self, jid: None)
    assert svc.get_invoice_xml_by_jarvis_id(99) is None
