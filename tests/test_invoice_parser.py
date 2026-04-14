"""Unit tests for Invoice Parser module.

Tests for:
- invoice_parser.py: VAT normalization, date parsing, value parsing, template matching
"""
import sys
import os

# Set dummy DATABASE_URL before importing modules that require it
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))


# ============== VAT NORMALIZATION TESTS ==============

class TestNormalizeVatNumber:
    """Tests for normalize_vat_number() function."""

    def test_romanian_with_space(self):
        from accounting.bugetare.invoice_parser import normalize_vat_number
        assert normalize_vat_number('RO 225615') == 'RO225615'

    def test_romanian_without_space(self):
        from accounting.bugetare.invoice_parser import normalize_vat_number
        assert normalize_vat_number('RO225615') == 'RO225615'

    def test_cui_prefix(self):
        from accounting.bugetare.invoice_parser import normalize_vat_number
        assert normalize_vat_number('CUI 225615') == '225615'

    def test_cif_with_country_code(self):
        from accounting.bugetare.invoice_parser import normalize_vat_number
        assert normalize_vat_number('CIF: RO 50022994') == 'RO50022994'

    def test_irish_vat_with_letter(self):
        from accounting.bugetare.invoice_parser import normalize_vat_number
        assert normalize_vat_number('IE9692928F') == 'IE9692928F'

    def test_vat_with_dashes(self):
        from accounting.bugetare.invoice_parser import normalize_vat_number
        assert normalize_vat_number('RO-225-615') == 'RO225615'

    def test_vat_with_dots(self):
        from accounting.bugetare.invoice_parser import normalize_vat_number
        assert normalize_vat_number('RO.225.615') == 'RO225615'

    def test_numbers_only(self):
        from accounting.bugetare.invoice_parser import normalize_vat_number
        assert normalize_vat_number('225615') == '225615'

    def test_empty_string(self):
        from accounting.bugetare.invoice_parser import normalize_vat_number
        assert normalize_vat_number('') is None

    def test_none(self):
        from accounting.bugetare.invoice_parser import normalize_vat_number
        assert normalize_vat_number(None) is None

    def test_lowercase_converted(self):
        from accounting.bugetare.invoice_parser import normalize_vat_number
        assert normalize_vat_number('ro225615') == 'RO225615'


# ============== DATE PARSING TESTS ==============

class TestParseRomanianDate:
    """Tests for parse_romanian_date() function."""

    def test_iso_format(self):
        from accounting.bugetare.invoice_parser import parse_romanian_date
        assert parse_romanian_date('2025-11-22') == '2025-11-22'

    def test_romanian_short_month(self):
        from accounting.bugetare.invoice_parser import parse_romanian_date
        assert parse_romanian_date('22 nov. 2025') == '2025-11-22'

    def test_romanian_full_month(self):
        from accounting.bugetare.invoice_parser import parse_romanian_date
        assert parse_romanian_date('22 noiembrie 2025') == '2025-11-22'

    def test_english_format(self):
        from accounting.bugetare.invoice_parser import parse_romanian_date
        assert parse_romanian_date('Nov 21, 2025') == '2025-11-21'

    def test_english_full_month(self):
        from accounting.bugetare.invoice_parser import parse_romanian_date
        assert parse_romanian_date('November 1, 2025') == '2025-11-01'

    def test_numeric_dot_separator(self):
        from accounting.bugetare.invoice_parser import parse_romanian_date
        assert parse_romanian_date('22.11.2025') == '2025-11-22'

    def test_numeric_slash_separator(self):
        from accounting.bugetare.invoice_parser import parse_romanian_date
        assert parse_romanian_date('22/11/2025') == '2025-11-22'

    def test_numeric_dash_separator(self):
        from accounting.bugetare.invoice_parser import parse_romanian_date
        assert parse_romanian_date('22-11-2025') == '2025-11-22'

    def test_single_digit_day(self):
        from accounting.bugetare.invoice_parser import parse_romanian_date
        assert parse_romanian_date('1.05.2025') == '2025-05-01'

    def test_unknown_format_returns_as_is(self):
        from accounting.bugetare.invoice_parser import parse_romanian_date
        assert parse_romanian_date('unknown format') == 'unknown format'


# ============== VALUE PARSING TESTS ==============

class TestParseInvoiceValue:
    """Tests for parse_invoice_value() function."""

    def test_european_format(self):
        from accounting.bugetare.invoice_parser import parse_invoice_value
        assert parse_invoice_value('1.234,56') == 1234.56

    def test_european_format_with_currency(self):
        from accounting.bugetare.invoice_parser import parse_invoice_value
        assert parse_invoice_value('874,90 RON') == 874.90

    def test_us_format(self):
        from accounting.bugetare.invoice_parser import parse_invoice_value
        assert parse_invoice_value('1,234.56') == 1234.56

    def test_space_thousand_separator(self):
        from accounting.bugetare.invoice_parser import parse_invoice_value
        assert parse_invoice_value('3 600.99') == 3600.99

    def test_lei_currency(self):
        from accounting.bugetare.invoice_parser import parse_invoice_value
        result = parse_invoice_value('1234.56 Lei')
        assert result == 1234.56

    def test_comma_decimal_only(self):
        from accounting.bugetare.invoice_parser import parse_invoice_value
        assert parse_invoice_value('123,45') == 123.45

    def test_simple_integer(self):
        from accounting.bugetare.invoice_parser import parse_invoice_value
        assert parse_invoice_value('1234') == 1234.0


# ============== TEMPLATE APPLICATION TESTS ==============

class TestApplyTemplate:
    """Tests for apply_template() function."""

    def test_fixed_template_values(self):
        from accounting.bugetare.invoice_parser import apply_template
        template = {
            'name': 'Test Template',
            'template_type': 'fixed',
            'supplier': 'Test Supplier',
            'supplier_vat': 'RO12345678',
            'currency': 'EUR'
        }
        result = apply_template(template)
        assert result['supplier'] == 'Test Supplier'
        assert result['supplier_vat'] == 'RO12345678'
        assert result['currency'] == 'EUR'
        assert result['template_used'] == 'Test Template'

    def test_customer_vat_regex_extraction(self):
        from accounting.bugetare.invoice_parser import apply_template
        template = {
            'name': 'Test',
            'template_type': 'fixed',
            'customer_vat_regex': r'VAT[:\s]*([A-Z]{2}\d+)'
        }
        text = 'Some invoice text VAT: RO50186814 more text'
        result = apply_template(template, text)
        assert result['customer_vat'] == 'RO50186814'

    def test_format_template_extracts_supplier(self):
        from accounting.bugetare.invoice_parser import apply_template
        template = {
            'name': 'Test',
            'template_type': 'format',
            'supplier_regex': r'Supplier:\s*(.+)',
            'supplier_vat_regex': r'CUI:\s*(\d+)'
        }
        text = 'Supplier: Test Company SRL\nCUI: 12345678'
        result = apply_template(template, text)
        assert result['supplier'] == 'Test Company SRL'
        assert result['supplier_vat'] == '12345678'


# ============== TEMPLATE MATCHING TESTS ==============

class TestFindMatchingTemplate:
    """Tests for find_matching_template() function."""

    def test_matches_by_supplier_vat(self):
        from accounting.bugetare.invoice_parser import find_matching_template
        templates = [
            {'id': 1, 'name': 'Meta', 'supplier_vat': 'IE9692928F', 'template_type': 'fixed'},
            {'id': 2, 'name': 'Google', 'supplier_vat': 'IE6388047V', 'template_type': 'fixed'}
        ]
        text = 'Invoice from Meta Platforms VAT: IE9692928F'
        result = find_matching_template(text, templates)
        assert result is not None
        assert result['name'] == 'Meta'

    def test_no_match_returns_none(self):
        from accounting.bugetare.invoice_parser import find_matching_template
        templates = [
            {'id': 1, 'name': 'Meta', 'supplier_vat': 'IE9692928F', 'template_type': 'fixed'}
        ]
        text = 'Invoice from Unknown Supplier VAT: XX12345678'
        result = find_matching_template(text, templates)
        assert result is None

    def test_format_template_marker_match(self):
        from accounting.bugetare.invoice_parser import find_matching_template
        templates = [
            {'id': 1, 'name': 'eFactura', 'supplier_vat': 'RO eFactura', 'template_type': 'format'}
        ]
        text = 'RO eFactura document content'
        result = find_matching_template(text, templates)
        assert result is not None
        assert result['name'] == 'eFactura'

    def test_empty_templates_returns_none(self):
        from accounting.bugetare.invoice_parser import find_matching_template
        assert find_matching_template('some text', []) is None

    def test_empty_text_returns_none(self):
        from accounting.bugetare.invoice_parser import find_matching_template
        templates = [{'id': 1, 'name': 'Test', 'supplier_vat': 'RO12345'}]
        assert find_matching_template('', templates) is None


# ============== VAT EXTRACTION TESTS ==============

class TestExtractVatNumbersFromText:
    """Tests for extract_vat_numbers_from_text() function."""

    def test_extracts_romanian_vat(self):
        from accounting.bugetare.invoice_parser import extract_vat_numbers_from_text
        text = 'Company with CUI: RO50186814'
        result = extract_vat_numbers_from_text(text)
        assert 'RO50186814' in result

    def test_extracts_irish_vat(self):
        from accounting.bugetare.invoice_parser import extract_vat_numbers_from_text
        text = 'VAT Reg. No. IE9692928F'
        result = extract_vat_numbers_from_text(text)
        assert 'IE9692928F' in result

    def test_extracts_multiple_vats(self):
        from accounting.bugetare.invoice_parser import extract_vat_numbers_from_text
        text = 'Seller: IE9692928F Buyer: RO50186814'
        result = extract_vat_numbers_from_text(text)
        assert len(result) >= 2


class TestExtractCustomerVatFromText:
    """Tests for extract_customer_vat_from_text() function."""

    def test_extracts_customer_vat(self):
        from accounting.bugetare.invoice_parser import extract_customer_vat_from_text
        text = 'Bill to: Company SRL CUI: RO50186814'
        result = extract_customer_vat_from_text(text)
        assert result == 'RO50186814'

    def test_excludes_supplier_vat(self):
        from accounting.bugetare.invoice_parser import extract_customer_vat_from_text
        text = 'Seller VAT: IE9692928F Buyer VAT: RO50186814'
        result = extract_customer_vat_from_text(text, supplier_vat='IE9692928F')
        assert result == 'RO50186814'

    def test_prefers_ro_vat(self):
        from accounting.bugetare.invoice_parser import extract_customer_vat_from_text
        text = 'Contains: 12345678 and RO50186814'
        result = extract_customer_vat_from_text(text)
        assert result.startswith('RO')


# ============== AI PARSING TESTS (MOCKED) ==============

class TestParseInvoiceAI:
    """Tests for parse_invoice() function with mocked AI."""

    @patch('accounting.bugetare.invoice_parser._llm_call')
    @patch('accounting.bugetare.invoice_parser.pdf_to_images')
    def test_returns_parsed_data(self, mock_pdf, mock_llm_call):
        from accounting.bugetare.invoice_parser import parse_invoice

        mock_pdf.return_value = [('base64data', 'image/png')]
        mock_llm_call.return_value = '{"supplier": "Test Co", "invoice_number": "INV001", "invoice_value": 100.50, "currency": "RON"}'

        result = parse_invoice('/tmp/test.pdf', api_key='test-key')

        assert result['supplier'] == 'Test Co'
        assert result['invoice_number'] == 'INV001'
        assert result['invoice_value'] == 100.50

    def test_raises_without_api_key(self):
        from accounting.bugetare.invoice_parser import parse_invoice

        with patch.dict(os.environ, {}, clear=True):
            # Remove ANTHROPIC_API_KEY if it exists
            os.environ.pop('ANTHROPIC_API_KEY', None)
            with pytest.raises(ValueError, match='ANTHROPIC_API_KEY'):
                parse_invoice('/tmp/test.pdf')


# ============== TEMPLATE PARSING TESTS ==============

class TestParseWithTemplate:
    """Tests for parse_with_template() function."""

    @patch('accounting.bugetare.invoice_parser.get_patterns_from_templates')
    @patch('PyPDF2.PdfReader')
    def test_extracts_invoice_number(self, mock_reader, mock_patterns):
        from accounting.bugetare.invoice_parser import parse_with_template

        mock_patterns.return_value = ([], [], [])

        mock_page = MagicMock()
        mock_page.extract_text.return_value = 'Factura nr. FBADS-123-456789'
        mock_reader.return_value.pages = [mock_page]

        template = {
            'name': 'Test',
            'template_type': 'fixed',
            'invoice_number_regex': r'Factura\s+nr\.?\s*(FBADS-\d+-\d+)'
        }

        with patch('builtins.open', MagicMock()):
            result = parse_with_template('/tmp/test.pdf', template)

        assert result['invoice_number'] == 'FBADS-123-456789'


# ============== IMAGE ENCODING TESTS ==============

class TestEncodeImageToBase64:
    """Tests for encode_image_to_base64() function."""

    def test_returns_correct_media_type_jpeg(self):
        from accounting.bugetare.invoice_parser import encode_image_to_base64

        with patch('builtins.open', MagicMock(return_value=MagicMock(__enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value=b'test')))))):
            data, media_type = encode_image_to_base64('/tmp/test.jpg')

        assert media_type == 'image/jpeg'

    def test_returns_correct_media_type_png(self):
        from accounting.bugetare.invoice_parser import encode_image_to_base64

        with patch('builtins.open', MagicMock(return_value=MagicMock(__enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value=b'test')))))):
            data, media_type = encode_image_to_base64('/tmp/test.png')

        assert media_type == 'image/png'


# Run with: pytest tests/test_invoice_parser.py -v
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
