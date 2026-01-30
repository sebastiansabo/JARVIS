"""
Tests for Invoice Service

Unit tests for invoice extraction, parsing, and deduplication.
"""

import pytest
from decimal import Decimal
from datetime import date
from unittest.mock import Mock, patch

import sys
import os

# Add parent paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from accounting.efactura.services.invoice_service import InvoiceService
from accounting.efactura.config import InvoiceDirection, ArtifactType
from accounting.efactura.models import ANAFMessage
from accounting.efactura.client.exceptions import ParseError
from .fixtures.mock_anaf_responses import (
    SAMPLE_UBL_INVOICE_XML,
    create_mock_zip_content,
)


class TestInvoiceService:
    """Tests for InvoiceService."""

    @pytest.fixture
    def service(self):
        """Create invoice service instance."""
        return InvoiceService()

    def test_extract_zip_success(self, service):
        """Test successful ZIP extraction."""
        zip_content = create_mock_zip_content()

        contents = service.extract_zip(zip_content)

        assert 'invoice.xml' in contents
        assert 'semnatura.xml' in contents
        assert len(contents['invoice.xml']) > 0

    def test_extract_zip_without_signature(self, service):
        """Test ZIP extraction without signature."""
        zip_content = create_mock_zip_content(include_signature=False)

        contents = service.extract_zip(zip_content)

        assert 'invoice.xml' in contents
        assert 'semnatura.xml' not in contents

    def test_extract_zip_invalid(self, service):
        """Test extraction of invalid ZIP."""
        with pytest.raises(ParseError) as exc_info:
            service.extract_zip(b'not a zip file')

        assert 'Invalid ZIP' in str(exc_info.value)

    def test_parse_ubl_invoice_basic(self, service):
        """Test basic UBL invoice parsing."""
        parsed = service.parse_invoice_xml(SAMPLE_UBL_INVOICE_XML)

        assert parsed.invoice_number == 'INV-2025-001'
        assert parsed.issue_date == date(2025, 1, 26)
        assert parsed.due_date == date(2025, 2, 26)
        assert parsed.currency == 'RON'

    def test_parse_ubl_invoice_seller(self, service):
        """Test seller info extraction."""
        parsed = service.parse_invoice_xml(SAMPLE_UBL_INVOICE_XML)

        assert parsed.seller_name == 'ACME SRL'
        assert parsed.seller_cif == '87654321'  # RO prefix removed
        assert 'Bucuresti' in parsed.seller_address

    def test_parse_ubl_invoice_buyer(self, service):
        """Test buyer info extraction."""
        parsed = service.parse_invoice_xml(SAMPLE_UBL_INVOICE_XML)

        assert parsed.buyer_name == 'TEST COMPANY SRL'
        assert parsed.buyer_cif == '12345678'

    def test_parse_ubl_invoice_amounts(self, service):
        """Test amount extraction."""
        parsed = service.parse_invoice_xml(SAMPLE_UBL_INVOICE_XML)

        assert parsed.total_without_vat == Decimal('1000.00')
        assert parsed.total_vat == Decimal('190.00')
        assert parsed.total_amount == Decimal('1190.00')

    def test_parse_ubl_invoice_vat_breakdown(self, service):
        """Test VAT breakdown extraction."""
        parsed = service.parse_invoice_xml(SAMPLE_UBL_INVOICE_XML)

        assert len(parsed.vat_breakdown) == 1
        assert parsed.vat_breakdown[0]['rate'] == Decimal('19.00')
        assert parsed.vat_breakdown[0]['amount'] == Decimal('190.00')

    def test_parse_ubl_invoice_line_items(self, service):
        """Test line item extraction."""
        parsed = service.parse_invoice_xml(SAMPLE_UBL_INVOICE_XML)

        assert len(parsed.line_items) == 1
        item = parsed.line_items[0]
        assert item.description == 'Test Product'
        assert item.quantity == Decimal('10')
        assert item.unit_price == Decimal('100.00')
        assert item.line_amount == Decimal('1000.00')
        assert item.vat_rate == Decimal('19.00')

    def test_parse_ubl_invoice_notes(self, service):
        """Test notes extraction."""
        parsed = service.parse_invoice_xml(SAMPLE_UBL_INVOICE_XML)

        assert 'unit testing' in parsed.invoice_note

    def test_parse_ubl_invoice_hash(self, service):
        """Test XML hash generation."""
        parsed = service.parse_invoice_xml(SAMPLE_UBL_INVOICE_XML)

        assert parsed.xml_hash is not None
        assert len(parsed.xml_hash) == 64  # SHA256

    def test_parse_invalid_xml(self, service):
        """Test parsing invalid XML."""
        with pytest.raises(ParseError) as exc_info:
            service.parse_invoice_xml(b'<invalid>not closed')

        assert 'Invalid XML' in str(exc_info.value)

    def test_parse_unknown_format(self, service):
        """Test parsing unknown XML format."""
        unknown_xml = b'<?xml version="1.0"?><UnknownRoot></UnknownRoot>'

        with pytest.raises(ParseError) as exc_info:
            service.parse_invoice_xml(unknown_xml)

        assert 'Unknown invoice format' in str(exc_info.value)

    def test_process_message_received(self, service):
        """Test processing a received message."""
        message = ANAFMessage(
            id='3066421557',
            cif='12345678',
            message_type='FACTURA',
        )
        zip_content = create_mock_zip_content()

        invoice, artifacts = service.process_message(
            company_cif='12345678',
            message=message,
            zip_content=zip_content,
            direction=InvoiceDirection.RECEIVED,
        )

        # Invoice should have partner as seller (we received it)
        assert invoice.cif_owner == '12345678'
        assert invoice.direction == InvoiceDirection.RECEIVED
        assert invoice.partner_cif == '87654321'  # Seller CIF
        assert invoice.partner_name == 'ACME SRL'

    def test_process_message_sent(self, service):
        """Test processing a sent message."""
        message = ANAFMessage(
            id='4077532668',
            cif='87654321',
            message_type='FACTURA',
        )
        zip_content = create_mock_zip_content()

        invoice, artifacts = service.process_message(
            company_cif='87654321',
            message=message,
            zip_content=zip_content,
            direction=InvoiceDirection.SENT,
        )

        # Invoice should have partner as buyer (we sent it)
        assert invoice.cif_owner == '87654321'
        assert invoice.direction == InvoiceDirection.SENT
        assert invoice.partner_cif == '12345678'  # Buyer CIF
        assert invoice.partner_name == 'TEST COMPANY SRL'

    def test_process_message_creates_artifacts(self, service):
        """Test that artifacts are created correctly."""
        message = ANAFMessage(id='3066421557')
        zip_content = create_mock_zip_content()

        invoice, artifacts = service.process_message(
            company_cif='12345678',
            message=message,
            zip_content=zip_content,
            direction=InvoiceDirection.RECEIVED,
        )

        assert len(artifacts) == 3  # ZIP, XML, Signature

        artifact_types = {a.artifact_type for a in artifacts}
        assert ArtifactType.ZIP in artifact_types
        assert ArtifactType.XML in artifact_types
        assert ArtifactType.SIGNATURE in artifact_types

    def test_process_message_without_signature(self, service):
        """Test processing message without signature file."""
        message = ANAFMessage(id='3066421557')
        zip_content = create_mock_zip_content(include_signature=False)

        invoice, artifacts = service.process_message(
            company_cif='12345678',
            message=message,
            zip_content=zip_content,
            direction=InvoiceDirection.RECEIVED,
        )

        assert len(artifacts) == 2  # ZIP, XML only

    def test_process_message_no_xml_in_zip(self, service):
        """Test error when ZIP has no XML."""
        import io
        import zipfile

        # Create ZIP with only text file
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as zf:
            zf.writestr('readme.txt', 'No invoice here')
        buffer.seek(0)

        message = ANAFMessage(id='3066421557')

        with pytest.raises(ParseError) as exc_info:
            service.process_message(
                company_cif='12345678',
                message=message,
                zip_content=buffer.read(),
                direction=InvoiceDirection.RECEIVED,
            )

        assert 'No invoice XML' in str(exc_info.value)

    def test_dedup_key_generation(self, service):
        """Test deduplication key generation."""
        key = service.get_dedup_key(
            company_cif='12345678',
            direction=InvoiceDirection.RECEIVED,
            message_id='3066421557',
        )

        assert key == '12345678:received:3066421557'

    def test_check_duplicate_no_repo(self, service):
        """Test duplicate check without repository."""
        # Without repo, should return False (not a duplicate)
        result = service.check_duplicate(
            company_cif='12345678',
            direction=InvoiceDirection.RECEIVED,
            message_id='3066421557',
        )

        assert result is False

    def test_check_duplicate_with_repo(self):
        """Test duplicate check with repository."""
        mock_repo = Mock()
        mock_repo.exists_by_message_id.return_value = True

        service = InvoiceService(invoice_repo=mock_repo)

        result = service.check_duplicate(
            company_cif='12345678',
            direction=InvoiceDirection.RECEIVED,
            message_id='3066421557',
        )

        assert result is True
        mock_repo.exists_by_message_id.assert_called_once()


class TestDateParsing:
    """Tests for date parsing utilities."""

    @pytest.fixture
    def service(self):
        return InvoiceService()

    def test_parse_iso_date(self, service):
        """Test ISO date parsing."""
        result = service._parse_date('2025-01-26')
        assert result == date(2025, 1, 26)

    def test_parse_compact_date(self, service):
        """Test compact date parsing."""
        result = service._parse_date('20250126')
        assert result == date(2025, 1, 26)

    def test_parse_romanian_date(self, service):
        """Test Romanian date format."""
        result = service._parse_date('26.01.2025')
        assert result == date(2025, 1, 26)

    def test_parse_slash_date(self, service):
        """Test slash-separated date."""
        result = service._parse_date('26/01/2025')
        assert result == date(2025, 1, 26)

    def test_parse_none_date(self, service):
        """Test None date handling."""
        result = service._parse_date(None)
        assert result is None

    def test_parse_invalid_date(self, service):
        """Test invalid date handling."""
        result = service._parse_date('not a date')
        assert result is None


class TestDecimalParsing:
    """Tests for decimal parsing utilities."""

    @pytest.fixture
    def service(self):
        return InvoiceService()

    def test_parse_decimal_dot(self, service):
        """Test decimal with dot separator."""
        result = service._parse_decimal('1234.56')
        assert result == Decimal('1234.56')

    def test_parse_decimal_comma(self, service):
        """Test decimal with comma separator."""
        result = service._parse_decimal('1234,56')
        assert result == Decimal('1234.56')

    def test_parse_decimal_none(self, service):
        """Test None decimal handling."""
        result = service._parse_decimal(None)
        assert result == Decimal('0.00')

    def test_parse_decimal_empty(self, service):
        """Test empty string handling."""
        result = service._parse_decimal('')
        assert result == Decimal('0.00')

    def test_parse_decimal_with_spaces(self, service):
        """Test decimal with spaces."""
        result = service._parse_decimal('1 234.56')
        assert result == Decimal('1234.56')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
