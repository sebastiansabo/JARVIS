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


def get_invoice_xml_by_jarvis_id(jarvis_invoice_id: int) -> Optional[str]:
    """UBL XML for a jarvis invoice's e-Factura record.

    Returns the stored copy if present; otherwise fetches it once from ANAF's descarcare
    endpoint, caches it back, and returns it. None when unavailable (no e-Factura record,
    no download id, or ANAF fetch failed).
    """
    repo = EFacturaInvoiceRepository()
    info = repo.get_xml_source_info(jarvis_invoice_id)
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
            extra={'jarvis_invoice_id': jarvis_invoice_id, 'error': str(e)},
        )
        return None

    if xml:
        try:
            repo.save_xml_content(info['id'], xml)
        except Exception as e:
            logger.warning(
                "failed to cache fetched xml",
                extra={'invoice_id': info['id'], 'error': str(e)},
            )
    return xml
