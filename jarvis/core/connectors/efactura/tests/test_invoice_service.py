"""
Tests for Invoice Service

Unit tests for invoice extraction, parsing, and deduplication.
"""

import pytest
from decimal import Decimal
from datetime import date
from unittest.mock import Mock

import sys
import os

# Add parent paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))

from core.connectors.efactura.services.invoice_service import InvoiceService
from core.connectors.efactura.config import InvoiceDirection, ArtifactType
from core.connectors.efactura.models import ANAFMessage
from core.connectors.efactura.client.exceptions import ParseError
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

    def test_parse_ubl_invoice_amounts(self, service):
        """Test amount extraction."""
        parsed = service.parse_invoice_xml(SAMPLE_UBL_INVOICE_XML)

        assert parsed.total_without_vat == Decimal('1000.00')
        assert parsed.total_vat == Decimal('190.00')
        assert parsed.total_amount == Decimal('1190.00')

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

    def test_dedup_key_generation(self, service):
        """Test deduplication key generation."""
        key = service.get_dedup_key(
            company_cif='12345678',
            direction=InvoiceDirection.RECEIVED,
            message_id='3066421557',
        )

        assert key == '12345678:received:3066421557'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
