"""
e-Factura XML Parser

Parses UBL 2.1 XML invoices from ANAF e-Factura system.
Extracts invoice data into structured ParsedInvoice objects.
"""

import re
from decimal import Decimal, InvalidOperation
from datetime import date
from typing import Optional
from xml.etree import ElementTree as ET

from core.utils.logging_config import get_logger
from .models import ParsedInvoice, InvoiceLineItem

logger = get_logger('jarvis.core.connectors.efactura.xml_parser')

# UBL 2.1 namespaces used in e-Factura
NAMESPACES = {
    'invoice': 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',
    'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
    'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
    'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
}


def parse_invoice_xml(xml_content: str) -> ParsedInvoice:
    """
    Parse e-Factura UBL 2.1 XML content into a ParsedInvoice object.

    Args:
        xml_content: The XML content as a string

    Returns:
        ParsedInvoice object with extracted data
    """
    try:
        # Parse XML
        root = ET.fromstring(xml_content)

        # Register namespaces for searching
        for prefix, uri in NAMESPACES.items():
            ET.register_namespace(prefix, uri)

        invoice = ParsedInvoice()

        # Basic invoice info
        invoice.invoice_number = _get_text(root, './/cbc:ID')
        invoice.issue_date = _parse_date(_get_text(root, './/cbc:IssueDate'))
        invoice.due_date = _parse_date(_get_text(root, './/cbc:DueDate'))

        # Currency
        invoice.currency = _get_text(root, './/cbc:DocumentCurrencyCode') or 'RON'

        # Seller (supplier) info
        seller = root.find('.//cac:AccountingSupplierParty/cac:Party', NAMESPACES)
        if seller is not None:
            invoice.seller_name = _get_party_name(seller)
            invoice.seller_cif = _get_party_cif(seller)
            invoice.seller_address = _get_party_address(seller)
            invoice.seller_reg_number = _get_text(seller, './/cbc:CompanyID')

        # Buyer (customer) info
        buyer = root.find('.//cac:AccountingCustomerParty/cac:Party', NAMESPACES)
        if buyer is not None:
            invoice.buyer_name = _get_party_name(buyer)
            invoice.buyer_cif = _get_party_cif(buyer)
            invoice.buyer_address = _get_party_address(buyer)

        # Amounts from LegalMonetaryTotal
        monetary_total = root.find('.//cac:LegalMonetaryTotal', NAMESPACES)
        if monetary_total is not None:
            invoice.total_without_vat = _parse_decimal(
                _get_text(monetary_total, 'cbc:TaxExclusiveAmount')
            )
            invoice.total_amount = _parse_decimal(
                _get_text(monetary_total, 'cbc:TaxInclusiveAmount') or
                _get_text(monetary_total, 'cbc:PayableAmount')
            )

        # VAT from TaxTotal
        tax_total = root.find('.//cac:TaxTotal', NAMESPACES)
        if tax_total is not None:
            invoice.total_vat = _parse_decimal(
                _get_text(tax_total, 'cbc:TaxAmount')
            )

            # VAT breakdown
            for subtotal in tax_total.findall('cac:TaxSubtotal', NAMESPACES):
                category = subtotal.find('cac:TaxCategory', NAMESPACES)
                if category is not None:
                    rate = _parse_decimal(_get_text(category, 'cbc:Percent'))
                    amount = _parse_decimal(_get_text(subtotal, 'cbc:TaxAmount'))
                    taxable = _parse_decimal(_get_text(subtotal, 'cbc:TaxableAmount'))

                    invoice.vat_breakdown.append({
                        'rate': rate,
                        'amount': amount,
                        'taxable': taxable,
                    })

        # If totals not found in LegalMonetaryTotal, calculate from VAT
        if invoice.total_amount == Decimal('0') and invoice.total_without_vat > 0:
            invoice.total_amount = invoice.total_without_vat + invoice.total_vat

        # Payment info
        payment_means = root.find('.//cac:PaymentMeans', NAMESPACES)
        if payment_means is not None:
            invoice.payment_means = _get_text(payment_means, 'cbc:PaymentMeansCode')
            account = payment_means.find('cac:PayeeFinancialAccount', NAMESPACES)
            if account is not None:
                invoice.bank_account = _get_text(account, 'cbc:ID')

        payment_terms = root.find('.//cac:PaymentTerms', NAMESPACES)
        if payment_terms is not None:
            invoice.payment_terms = _get_text(payment_terms, 'cbc:Note')

        # Notes
        invoice.invoice_note = _get_text(root, './/cbc:Note')

        # Line items (optional - can be omitted for performance)
        for line_elem in root.findall('.//cac:InvoiceLine', NAMESPACES):
            line = _parse_line_item(line_elem)
            if line:
                invoice.line_items.append(line)

        logger.info(
            "Parsed e-Factura XML",
            extra={
                'invoice_number': invoice.invoice_number,
                'seller': invoice.seller_name,
                'buyer': invoice.buyer_name,
                'total': str(invoice.total_amount),
            }
        )

        return invoice

    except ET.ParseError as e:
        logger.error(f"XML parse error: {e}")
        raise ValueError(f"Invalid XML: {e}")
    except Exception as e:
        logger.error(f"Error parsing invoice XML: {e}")
        raise


def _get_text(element: Optional[ET.Element], path: str) -> Optional[str]:
    """Get text content from element at path."""
    if element is None:
        return None

    found = element.find(path, NAMESPACES)
    if found is not None and found.text:
        return found.text.strip()
    return None


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    """Parse ISO date string to date object."""
    if not date_str:
        return None
    try:
        # Handle YYYY-MM-DD format
        return date.fromisoformat(date_str[:10])
    except ValueError:
        return None


def _parse_decimal(value: Optional[str]) -> Decimal:
    """Parse decimal value, returning 0 on error."""
    if not value:
        return Decimal('0')
    try:
        # Remove any currency symbols or spaces
        cleaned = re.sub(r'[^\d.,\-]', '', value)
        # Handle comma as decimal separator
        if ',' in cleaned and '.' not in cleaned:
            cleaned = cleaned.replace(',', '.')
        elif ',' in cleaned and '.' in cleaned:
            # Both present - comma is likely thousands separator
            cleaned = cleaned.replace(',', '')
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return Decimal('0')


def _get_party_name(party: ET.Element) -> str:
    """Extract party name from Party element."""
    # Try multiple paths
    name = _get_text(party, 'cac:PartyName/cbc:Name')
    if name:
        return name

    # Try PartyLegalEntity
    name = _get_text(party, 'cac:PartyLegalEntity/cbc:RegistrationName')
    if name:
        return name

    return ''


def _get_party_cif(party: ET.Element) -> str:
    """Extract party CIF/VAT number from Party element."""
    # Try PartyTaxScheme first (usually has the VAT ID)
    cif = _get_text(party, 'cac:PartyTaxScheme/cbc:CompanyID')
    if cif:
        return _normalize_cif(cif)

    # Try PartyIdentification
    for ident in party.findall('cac:PartyIdentification', NAMESPACES):
        cif_id = _get_text(ident, 'cbc:ID')
        if cif_id:
            # Check if it looks like a CIF (has schemeID or looks like VAT)
            id_elem = ident.find('cbc:ID', NAMESPACES)
            if id_elem is not None:
                scheme = id_elem.get('schemeID', '')
                if scheme in ('CIF', 'CUI', 'VAT', 'VATID', ''):
                    return _normalize_cif(cif_id)

    # Try PartyLegalEntity
    cif = _get_text(party, 'cac:PartyLegalEntity/cbc:CompanyID')
    if cif:
        return _normalize_cif(cif)

    return ''


def _normalize_cif(cif: str) -> str:
    """Normalize CIF/VAT number by removing spaces but keeping country code."""
    if not cif:
        return ''
    # Remove spaces and dashes
    cleaned = cif.replace(' ', '').replace('-', '').upper()
    return cleaned


def _get_party_address(party: ET.Element) -> Optional[str]:
    """Extract party address from Party element."""
    address = party.find('cac:PostalAddress', NAMESPACES)
    if address is None:
        return None

    parts = []

    street = _get_text(address, 'cbc:StreetName')
    if street:
        parts.append(street)

    building = _get_text(address, 'cbc:BuildingNumber')
    if building:
        parts.append(f'Nr. {building}')

    city = _get_text(address, 'cbc:CityName')
    if city:
        parts.append(city)

    region = _get_text(address, 'cbc:CountrySubentity')
    if region:
        parts.append(region)

    postal = _get_text(address, 'cbc:PostalZone')
    if postal:
        parts.append(postal)

    country = _get_text(address, 'cac:Country/cbc:IdentificationCode')
    if country:
        parts.append(country)

    return ', '.join(parts) if parts else None


def _parse_line_item(line: ET.Element) -> Optional[InvoiceLineItem]:
    """Parse a single invoice line item."""
    try:
        item = InvoiceLineItem()

        item.line_number = int(_get_text(line, 'cbc:ID') or '0')

        # Get item info
        item_elem = line.find('cac:Item', NAMESPACES)
        if item_elem is not None:
            item.description = _get_text(item_elem, 'cbc:Description') or \
                              _get_text(item_elem, 'cbc:Name') or ''

            # Item identification codes
            item.seller_item_id = _get_text(
                item_elem, 'cac:SellersItemIdentification/cbc:ID'
            )
            item.buyer_item_id = _get_text(
                item_elem, 'cac:BuyersItemIdentification/cbc:ID'
            )

            # Commodity code
            commodity = item_elem.find(
                'cac:CommodityClassification/cbc:ItemClassificationCode',
                NAMESPACES
            )
            if commodity is not None:
                item.commodity_code = commodity.text

            # VAT rate
            tax_cat = item_elem.find('cac:ClassifiedTaxCategory', NAMESPACES)
            if tax_cat is not None:
                item.vat_rate = _parse_decimal(_get_text(tax_cat, 'cbc:Percent'))

        # Quantity and unit
        qty = _get_text(line, 'cbc:InvoicedQuantity')
        item.quantity = _parse_decimal(qty)

        qty_elem = line.find('cbc:InvoicedQuantity', NAMESPACES)
        if qty_elem is not None:
            item.unit = qty_elem.get('unitCode', 'BUC')

        # Pricing
        price = line.find('cac:Price', NAMESPACES)
        if price is not None:
            item.unit_price = _parse_decimal(_get_text(price, 'cbc:PriceAmount'))

        # Line total
        item.line_amount = _parse_decimal(_get_text(line, 'cbc:LineExtensionAmount'))

        # Calculate VAT amount if we have rate and amount
        if item.vat_rate > 0 and item.line_amount > 0:
            item.vat_amount = item.line_amount * (item.vat_rate / 100)

        return item

    except Exception as e:
        logger.warning(f"Error parsing line item: {e}")
        return None
