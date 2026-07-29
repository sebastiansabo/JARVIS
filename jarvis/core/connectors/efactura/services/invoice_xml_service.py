"""
Resolve an invoice's UBL XML for the in-app preview.

Prefers the locally stored copy (`efactura_invoices.xml_content`). If that is missing,
fetches the ZIP from ANAF's `descarcare` endpoint on demand, extracts the invoice XML,
caches it back onto the invoice row, and returns it. Every failure degrades to None so the
caller can return a clean "not available" instead of an error — the preview itself never
depends on ANAF's flaky transformare/PDF service.
"""
import io
import zipfile
from typing import Optional

from core.utils.logging_config import get_logger
from ..repositories import EFacturaInvoiceRepository

logger = get_logger('jarvis.core.connectors.efactura.invoice_xml_service')


def extract_invoice_xml_from_zip(zip_bytes: bytes) -> Optional[str]:
    """Return the invoice XML from an ANAF ZIP, skipping the signature files."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            # semnatura_*.xml is the digital signature, *.p7s the detached one — skip both.
            if name.startswith('semnatura') or name.endswith('.p7s'):
                continue
            if name.endswith('.xml'):
                return zf.read(name).decode('utf-8')
    return None


def _resolve_xml(info: Optional[dict]) -> Optional[str]:
    """Given an {id, cif_owner, xml_content, download_id} row, return the UBL XML:
    the stored copy, or fetched once from ANAF descarcare (and cached back). None if
    unavailable (no record, no download id, or ANAF fetch failed)."""
    if not info:
        return None
    if info.get('xml_content'):
        return info['xml_content']

    download_id = info.get('download_id')
    cif = info.get('cif_owner')
    if not download_id or not cif:
        return None

    try:
        from .efactura_service import EFacturaService
        client = EFacturaService().get_anaf_client(cif)
        zip_bytes = client.download_message(download_id)
        xml = extract_invoice_xml_from_zip(zip_bytes)
    except Exception as e:
        logger.warning(
            "descarcare fetch failed for preview",
            extra={'invoice_id': info.get('id'), 'error': str(e)},
        )
        return None

    if xml:
        try:
            EFacturaInvoiceRepository().save_xml_content(info['id'], xml)
        except Exception as e:
            logger.warning(
                "failed to cache fetched xml",
                extra={'invoice_id': info.get('id'), 'error': str(e)},
            )
    return xml


def get_invoice_xml_by_jarvis_id(jarvis_invoice_id: int) -> Optional[str]:
    """UBL XML for a jarvis invoice's e-Factura record (profile preview)."""
    return _resolve_xml(EFacturaInvoiceRepository().get_xml_source_info(jarvis_invoice_id))


def get_invoice_xml_by_efactura_id(invoice_id: int) -> Optional[str]:
    """UBL XML for an e-Factura invoice by its PK (accounting/e-Factura preview)."""
    return _resolve_xml(EFacturaInvoiceRepository().get_xml_source_info_by_id(invoice_id))
