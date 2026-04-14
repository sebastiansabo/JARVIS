"""
PDF Service - invoice PDF generation and export from XML.
"""
from core.utils.logging_config import get_logger
from ..repositories import EFacturaInvoiceRepository
from .base import ServiceResult

logger = get_logger('jarvis.core.connectors.efactura.pdf_service')


class PDFService:
    def __init__(self):
        self.invoice_repo = EFacturaInvoiceRepository()

    def get_invoice_pdf(self, invoice_id: int) -> ServiceResult:
        """
        Get PDF for a stored e-Factura invoice.

        Retrieves the XML from storage and converts to PDF via ANAF API.
        """
        invoice = self.invoice_repo.get_by_id(invoice_id)

        if not invoice:
            return ServiceResult(success=False, error="Invoice not found")

        # Get the XML content
        xml_content = self.invoice_repo.get_xml_content(invoice_id)

        if not xml_content:
            return ServiceResult(success=False, error="XML content not found")

        try:
            # Convert to PDF
            from .efactura_service import EFacturaService
            client = EFacturaService().get_anaf_client(invoice.cif_owner)
            pdf_data = client.xml_to_pdf(xml_content, standard='FACT1', validate=True)

            return ServiceResult(success=True, data={
                'pdf_data': pdf_data,
                'filename': f'invoice_{invoice.full_invoice_number}.pdf',
            })

        except Exception as e:
            logger.error(f"Error converting to PDF: {e}")
            return ServiceResult(success=False, error=str(e))

    def export_anaf_pdf(
        self,
        cif: str,
        message_id: str,
        standard: str = 'FACT1',
        validate: bool = True
    ) -> ServiceResult:
        """
        Export invoice as PDF from ANAF message.

        Downloads the ZIP from ANAF, extracts the XML, and converts it to PDF.
        """
        import io
        import zipfile
        from .base import MOCK_MODE

        try:
            # Get client (mock or real)
            from .efactura_service import EFacturaService
            client = EFacturaService().get_anaf_client(cif)

            # Step 1: Download the ZIP file
            logger.info(f"Downloading message {message_id} for PDF export")
            zip_data = client.download_message(message_id)

            # Step 2: Extract XML from ZIP
            # Note: ZIPs may contain multiple XMLs:
            # - semnatura_*.xml = digital signature (skip)
            # - *.xml = actual invoice (we want this)
            xml_content = None
            with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zf:
                for filename in zf.namelist():
                    # Skip signature files and .p7s files
                    if filename.startswith('semnatura') or filename.endswith('.p7s'):
                        continue
                    if filename.endswith('.xml'):
                        xml_content = zf.read(filename).decode('utf-8')
                        break

            if not xml_content:
                return ServiceResult(success=False, error="No XML file found in downloaded ZIP")

            # Step 3: Convert XML to PDF using ANAF API
            logger.info(f"Converting XML to PDF using standard {standard}")
            pdf_data = client.xml_to_pdf(xml_content, standard=standard, validate=validate)

            return ServiceResult(success=True, data={
                'pdf_data': pdf_data,
                'filename': f'invoice_{message_id}.pdf',
                'mock_mode': MOCK_MODE,
            })

        except ValueError as e:
            return ServiceResult(success=False, error=f"Configuration error: {e}")
        except Exception as e:
            logger.error(f"Error exporting PDF: {e}")
            return ServiceResult(success=False, error=str(e))
