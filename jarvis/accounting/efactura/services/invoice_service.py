"""
Invoice Service

Business logic for invoice extraction, parsing, and deduplication.
"""

import hashlib
import io
import zipfile
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Dict, Any, List, Tuple
from xml.etree import ElementTree as ET

from core.utils.logging_config import get_logger
from ..config import InvoiceDirection, ArtifactType
from ..models import (
    Invoice,
    InvoiceExternalRef,
    InvoiceArtifact,
    ParsedInvoice,
    InvoiceLineItem,
    ANAFMessage,
)
from ..client.exceptions import ParseError

logger = get_logger('jarvis.accounting.efactura.invoice_service')

# UBL/CII XML namespaces
NAMESPACES = {
    'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
    'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
    'ubl': 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',
    'cii': 'urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100',
    'ram': 'urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100',
}


class InvoiceService:
    """
    Service for processing e-Factura invoices.

    Handles extraction from ZIP archives, XML parsing,
    deduplication, and data transformation.
    """

    def __init__(self, invoice_repo=None, artifact_repo=None):
        """
        Initialize invoice service.

        Args:
            invoice_repo: Repository for invoice persistence
            artifact_repo: Repository for artifact storage
        """
        self.invoice_repo = invoice_repo
        self.artifact_repo = artifact_repo

    def extract_zip(
        self,
        zip_content: bytes,
    ) -> Dict[str, bytes]:
        """
        Extract contents from ANAF ZIP archive.

        Args:
            zip_content: ZIP file as bytes

        Returns:
            Dict mapping filename to content bytes
        """
        logger.debug(
            "Extracting ZIP archive",
            extra={'size_bytes': len(zip_content)}
        )

        try:
            with zipfile.ZipFile(io.BytesIO(zip_content), 'r') as zf:
                contents = {}
                for name in zf.namelist():
                    contents[name] = zf.read(name)

                logger.debug(
                    "ZIP extracted",
                    extra={
                        'file_count': len(contents),
                        'files': list(contents.keys()),
                    }
                )
                return contents

        except zipfile.BadZipFile as e:
            raise ParseError(f"Invalid ZIP file: {e}")
        except Exception as e:
            raise ParseError(f"Failed to extract ZIP: {e}")

    def parse_invoice_xml(
        self,
        xml_content: bytes,
    ) -> ParsedInvoice:
        """
        Parse invoice XML (UBL or CII format).

        Args:
            xml_content: Invoice XML as bytes

        Returns:
            ParsedInvoice with extracted data
        """
        logger.debug(
            "Parsing invoice XML",
            extra={'size_bytes': len(xml_content)}
        )

        try:
            # Parse XML
            root = ET.fromstring(xml_content)
            root_tag = root.tag.lower()

            # Detect format and parse accordingly
            if 'invoice' in root_tag:
                return self._parse_ubl_invoice(root)
            elif 'crossindustryinvoice' in root_tag:
                return self._parse_cii_invoice(root)
            else:
                raise ParseError(f"Unknown invoice format: {root.tag}")

        except ET.ParseError as e:
            raise ParseError(f"Invalid XML: {e}")
        except Exception as e:
            logger.error(
                "Invoice parsing failed",
                extra={'error': str(e)}
            )
            raise ParseError(f"Failed to parse invoice XML: {e}")

    def _parse_ubl_invoice(self, root: ET.Element) -> ParsedInvoice:
        """Parse UBL 2.1 format invoice."""
        invoice = ParsedInvoice()

        def find_text(path: str, namespaces: dict = NAMESPACES) -> Optional[str]:
            elem = root.find(path, namespaces)
            return elem.text if elem is not None else None

        # Basic invoice info
        invoice.invoice_number = find_text('.//cbc:ID') or ''
        invoice.issue_date = self._parse_date(find_text('.//cbc:IssueDate'))
        invoice.due_date = self._parse_date(find_text('.//cbc:DueDate'))
        invoice.currency = find_text('.//cbc:DocumentCurrencyCode') or 'RON'

        # Seller info
        seller = root.find('.//cac:AccountingSupplierParty/cac:Party', NAMESPACES)
        if seller is not None:
            invoice.seller_name = self._find_party_name(seller)
            invoice.seller_cif = self._find_party_tax_id(seller)
            invoice.seller_address = self._find_party_address(seller)
            invoice.seller_reg_number = self._find_company_id(seller)

        # Buyer info
        buyer = root.find('.//cac:AccountingCustomerParty/cac:Party', NAMESPACES)
        if buyer is not None:
            invoice.buyer_name = self._find_party_name(buyer)
            invoice.buyer_cif = self._find_party_tax_id(buyer)
            invoice.buyer_address = self._find_party_address(buyer)

        # Totals
        monetary = root.find('.//cac:LegalMonetaryTotal', NAMESPACES)
        if monetary is not None:
            invoice.total_without_vat = self._parse_decimal(
                monetary.findtext('cbc:TaxExclusiveAmount', namespaces=NAMESPACES)
            )
            invoice.total_vat = self._parse_decimal(
                monetary.findtext('cbc:TaxAmount', namespaces=NAMESPACES)
            )
            invoice.total_amount = self._parse_decimal(
                monetary.findtext('cbc:PayableAmount', namespaces=NAMESPACES)
            )

        # VAT breakdown
        for tax_subtotal in root.findall('.//cac:TaxTotal/cac:TaxSubtotal', NAMESPACES):
            rate = self._parse_decimal(
                tax_subtotal.findtext('.//cbc:Percent', namespaces=NAMESPACES)
            )
            amount = self._parse_decimal(
                tax_subtotal.findtext('cbc:TaxAmount', namespaces=NAMESPACES)
            )
            base = self._parse_decimal(
                tax_subtotal.findtext('cbc:TaxableAmount', namespaces=NAMESPACES)
            )
            invoice.vat_breakdown.append({
                'rate': rate,
                'amount': amount,
                'base': base,
            })

        # Line items
        for idx, line in enumerate(root.findall('.//cac:InvoiceLine', NAMESPACES), 1):
            item = InvoiceLineItem(line_number=idx)
            item.description = (
                line.findtext('.//cbc:Name', namespaces=NAMESPACES) or
                line.findtext('.//cbc:Description', namespaces=NAMESPACES) or
                ''
            )
            item.quantity = self._parse_decimal(
                line.findtext('cbc:InvoicedQuantity', namespaces=NAMESPACES)
            )
            item.unit_price = self._parse_decimal(
                line.findtext('.//cbc:PriceAmount', namespaces=NAMESPACES)
            )
            item.line_amount = self._parse_decimal(
                line.findtext('cbc:LineExtensionAmount', namespaces=NAMESPACES)
            )
            item.vat_rate = self._parse_decimal(
                line.findtext('.//cac:ClassifiedTaxCategory/cbc:Percent', namespaces=NAMESPACES)
            )
            invoice.line_items.append(item)

        # Notes
        invoice.invoice_note = find_text('.//cbc:Note')

        # Payment info
        payment = root.find('.//cac:PaymentMeans', NAMESPACES)
        if payment is not None:
            invoice.payment_means = payment.findtext('cbc:PaymentMeansCode', namespaces=NAMESPACES)
            invoice.bank_account = payment.findtext(
                './/cac:PayeeFinancialAccount/cbc:ID', namespaces=NAMESPACES
            )

        # Calculate hash
        invoice.xml_hash = hashlib.sha256(ET.tostring(root)).hexdigest()

        logger.info(
            "UBL invoice parsed",
            extra={
                'invoice_number': invoice.invoice_number,
                'seller_cif': invoice.seller_cif,
                'total': str(invoice.total_amount),
            }
        )

        return invoice

    def _parse_cii_invoice(self, root: ET.Element) -> ParsedInvoice:
        """Parse CII (Cross Industry Invoice) format."""
        invoice = ParsedInvoice()

        def find_text(path: str) -> Optional[str]:
            elem = root.find(path, NAMESPACES)
            return elem.text if elem is not None else None

        # Document header
        header = root.find('.//ram:ExchangedDocument', NAMESPACES)
        if header is not None:
            invoice.invoice_number = (
                header.findtext('.//ram:ID', namespaces=NAMESPACES) or ''
            )
            invoice.issue_date = self._parse_date(
                header.findtext('.//ram:IssueDateTime/ram:DateTimeString', namespaces=NAMESPACES)
            )

        # Trade parties
        trade = root.find('.//ram:SupplyChainTradeTransaction', NAMESPACES)
        if trade is not None:
            # Seller
            seller = trade.find('.//ram:SellerTradeParty', NAMESPACES)
            if seller is not None:
                invoice.seller_name = (
                    seller.findtext('ram:Name', namespaces=NAMESPACES) or ''
                )
                tax_reg = seller.find('.//ram:SpecifiedTaxRegistration/ram:ID', NAMESPACES)
                if tax_reg is not None:
                    invoice.seller_cif = tax_reg.text or ''

            # Buyer
            buyer = trade.find('.//ram:BuyerTradeParty', NAMESPACES)
            if buyer is not None:
                invoice.buyer_name = (
                    buyer.findtext('ram:Name', namespaces=NAMESPACES) or ''
                )
                tax_reg = buyer.find('.//ram:SpecifiedTaxRegistration/ram:ID', NAMESPACES)
                if tax_reg is not None:
                    invoice.buyer_cif = tax_reg.text or ''

            # Monetary totals
            settlement = trade.find('.//ram:ApplicableHeaderTradeSettlement', NAMESPACES)
            if settlement is not None:
                invoice.currency = (
                    settlement.findtext('ram:InvoiceCurrencyCode', namespaces=NAMESPACES) or 'RON'
                )
                summary = settlement.find('ram:SpecifiedTradeSettlementHeaderMonetarySummation', NAMESPACES)
                if summary is not None:
                    invoice.total_without_vat = self._parse_decimal(
                        summary.findtext('ram:TaxBasisTotalAmount', namespaces=NAMESPACES)
                    )
                    invoice.total_vat = self._parse_decimal(
                        summary.findtext('ram:TaxTotalAmount', namespaces=NAMESPACES)
                    )
                    invoice.total_amount = self._parse_decimal(
                        summary.findtext('ram:GrandTotalAmount', namespaces=NAMESPACES)
                    )

        invoice.xml_hash = hashlib.sha256(ET.tostring(root)).hexdigest()

        logger.info(
            "CII invoice parsed",
            extra={
                'invoice_number': invoice.invoice_number,
                'seller_cif': invoice.seller_cif,
                'total': str(invoice.total_amount),
            }
        )

        return invoice

    def _find_party_name(self, party: ET.Element) -> str:
        """Extract party name from UBL party element."""
        name = party.findtext('.//cbc:RegistrationName', namespaces=NAMESPACES)
        if not name:
            name = party.findtext('.//cbc:Name', namespaces=NAMESPACES)
        return name or ''

    def _find_party_tax_id(self, party: ET.Element) -> str:
        """Extract tax ID (CIF/VAT) from UBL party element."""
        tax_id = party.findtext('.//cbc:CompanyID', namespaces=NAMESPACES)
        if not tax_id:
            tax_id = party.findtext(
                './/cac:PartyTaxScheme/cbc:CompanyID', namespaces=NAMESPACES
            )
        return (tax_id or '').replace('RO', '').strip()

    def _find_party_address(self, party: ET.Element) -> Optional[str]:
        """Extract address from UBL party element."""
        addr = party.find('.//cac:PostalAddress', NAMESPACES)
        if addr is None:
            return None

        parts = []
        street = addr.findtext('cbc:StreetName', namespaces=NAMESPACES)
        if street:
            parts.append(street)
        city = addr.findtext('cbc:CityName', namespaces=NAMESPACES)
        if city:
            parts.append(city)
        country = addr.findtext('.//cbc:IdentificationCode', namespaces=NAMESPACES)
        if country:
            parts.append(country)

        return ', '.join(parts) if parts else None

    def _find_company_id(self, party: ET.Element) -> Optional[str]:
        """Extract company registration ID (J number) from UBL party."""
        legal = party.find('.//cac:PartyLegalEntity', NAMESPACES)
        if legal is not None:
            return legal.findtext('cbc:CompanyID', namespaces=NAMESPACES)
        return None

    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """Parse date from various formats."""
        if not date_str:
            return None

        # Try common formats
        formats = [
            '%Y-%m-%d',
            '%Y%m%d',
            '%d.%m.%Y',
            '%d/%m/%Y',
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str[:10], fmt).date()
            except ValueError:
                continue

        logger.warning(f"Could not parse date: {date_str}")
        return None

    def _parse_decimal(self, value: Optional[str]) -> Decimal:
        """Parse decimal value, defaulting to 0."""
        if not value:
            return Decimal('0.00')
        try:
            # Handle both . and , as decimal separators
            cleaned = value.replace(',', '.').replace(' ', '')
            return Decimal(cleaned).quantize(Decimal('0.01'))
        except Exception:
            return Decimal('0.00')

    def process_message(
        self,
        company_cif: str,
        message: ANAFMessage,
        zip_content: bytes,
        direction: InvoiceDirection,
    ) -> Tuple[Invoice, List[InvoiceArtifact]]:
        """
        Process a downloaded ANAF message.

        Args:
            company_cif: Company that owns this invoice
            message: ANAF message metadata
            zip_content: Downloaded ZIP file content
            direction: Whether invoice was received or sent

        Returns:
            Tuple of (Invoice, list of artifacts)
        """
        logger.info(
            "Processing ANAF message",
            extra={
                'message_id': message.id,
                'company_cif': company_cif,
                'direction': direction.value,
            }
        )

        # Extract ZIP contents
        contents = self.extract_zip(zip_content)

        # Find and parse the invoice XML
        xml_content = None
        xml_filename = None
        for filename, content in contents.items():
            if filename.endswith('.xml') and not filename.startswith('semnatura'):
                xml_content = content
                xml_filename = filename
                break

        if not xml_content:
            raise ParseError("No invoice XML found in ZIP archive")

        # Parse invoice
        parsed = self.parse_invoice_xml(xml_content)

        # Create invoice model
        invoice = Invoice(
            cif_owner=company_cif,
            direction=direction,
            partner_cif=parsed.seller_cif if direction == InvoiceDirection.RECEIVED else parsed.buyer_cif,
            partner_name=parsed.seller_name if direction == InvoiceDirection.RECEIVED else parsed.buyer_name,
            invoice_number=parsed.invoice_number,
            invoice_series=parsed.invoice_series,
            issue_date=parsed.issue_date,
            due_date=parsed.due_date,
            total_amount=parsed.total_amount,
            total_vat=parsed.total_vat,
            total_without_vat=parsed.total_without_vat,
            currency=parsed.currency,
        )

        # Create artifacts
        artifacts = []

        # ZIP artifact
        artifacts.append(InvoiceArtifact(
            artifact_type=ArtifactType.ZIP,
            original_filename=f"{message.id}.zip",
            checksum=hashlib.sha256(zip_content).hexdigest(),
            size_bytes=len(zip_content),
        ))

        # XML artifact
        artifacts.append(InvoiceArtifact(
            artifact_type=ArtifactType.XML,
            original_filename=xml_filename,
            checksum=hashlib.sha256(xml_content).hexdigest(),
            size_bytes=len(xml_content),
        ))

        # Signature artifact (if present)
        for filename, content in contents.items():
            if 'semnatura' in filename.lower() or filename.endswith('.p7s'):
                artifacts.append(InvoiceArtifact(
                    artifact_type=ArtifactType.SIGNATURE,
                    original_filename=filename,
                    checksum=hashlib.sha256(content).hexdigest(),
                    size_bytes=len(content),
                ))
                break

        logger.info(
            "Message processed",
            extra={
                'message_id': message.id,
                'invoice_number': invoice.invoice_number,
                'partner_cif': invoice.partner_cif,
                'total': str(invoice.total_amount),
                'artifact_count': len(artifacts),
            }
        )

        return invoice, artifacts

    def check_duplicate(
        self,
        company_cif: str,
        direction: InvoiceDirection,
        message_id: str,
    ) -> bool:
        """
        Check if an invoice already exists (deduplication).

        Args:
            company_cif: Company CIF
            direction: Invoice direction
            message_id: ANAF message ID

        Returns:
            True if invoice already exists
        """
        if self.invoice_repo is None:
            return False

        return self.invoice_repo.exists_by_message_id(
            company_cif,
            direction,
            message_id,
        )

    def get_dedup_key(
        self,
        company_cif: str,
        direction: InvoiceDirection,
        message_id: str,
    ) -> str:
        """
        Generate deduplication key for an invoice.

        Args:
            company_cif: Company CIF
            direction: Invoice direction
            message_id: ANAF message ID

        Returns:
            Unique deduplication key
        """
        return f"{company_cif}:{direction.value}:{message_id}"
