"""Unit tests for Bank Statement module.

Tests for:
- parser.py: parse_value(), parse_date(), parse_unicredit_statement()
- vendors.py: match_vendor(), extract_vendor_name()
- database.py: check_duplicate_transaction(), save_transactions()
"""
import sys
import os
import pytest
from unittest.mock import patch, MagicMock
from datetime import date

# Add project root to path (for 'from database import' to work)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
# Add jarvis folder to path (for 'from accounting.statements import' to work)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))


# ============== PARSER TESTS ==============

class TestParseValue:
    """Tests for parse_value() function - European number format parsing."""

    def test_simple_integer(self):
        from accounting.statements.parser import parse_value
        assert parse_value('123') == 123.0

    def test_european_format_with_comma(self):
        from accounting.statements.parser import parse_value
        assert parse_value('123,45') == 123.45

    def test_european_format_with_thousands(self):
        from accounting.statements.parser import parse_value
        assert parse_value('1.234,56') == 1234.56

    def test_european_format_large_number(self):
        from accounting.statements.parser import parse_value
        assert parse_value('1.234.567,89') == 1234567.89

    def test_with_spaces(self):
        from accounting.statements.parser import parse_value
        assert parse_value('1 234,56') == 1234.56

    def test_empty_string(self):
        from accounting.statements.parser import parse_value
        assert parse_value('') == 0.0

    def test_none(self):
        from accounting.statements.parser import parse_value
        assert parse_value(None) == 0.0

    def test_invalid_value(self):
        from accounting.statements.parser import parse_value
        assert parse_value('abc') == 0.0

    def test_negative(self):
        from accounting.statements.parser import parse_value
        assert parse_value('-1.247,80') == -1247.80

    def test_ocr_comma_as_thousands(self):
        # OCR sometimes renders the thousands '.' as ',' -> "2,003,36"
        from accounting.statements.parser import parse_value
        assert parse_value('2,003,36') == 2003.36
        assert parse_value('-2,000,00') == -2000.00
        assert parse_value('3,000,00') == 3000.00

    def test_multi_separator_integer(self):
        # Multiple grouping separators, no decimal comma -> integer value.
        # (A lone "1.234" stays a decimal, matching long-standing behavior;
        # real statement amounts always carry a 2-digit decimal.)
        from accounting.statements.parser import parse_value
        assert parse_value('1.234.567') == 1234567.0


class TestParseDate:
    """Tests for parse_date() function - DD.MM.YYYY to YYYY-MM-DD conversion."""

    def test_valid_date(self):
        from accounting.statements.parser import parse_date
        assert parse_date('15.11.2024') == '2024-11-15'

    def test_date_with_leading_zeros(self):
        from accounting.statements.parser import parse_date
        assert parse_date('01.01.2024') == '2024-01-01'

    def test_date_with_whitespace(self):
        from accounting.statements.parser import parse_date
        assert parse_date('  15.11.2024  ') == '2024-11-15'

    def test_empty_string(self):
        from accounting.statements.parser import parse_date
        assert parse_date('') is None

    def test_none(self):
        from accounting.statements.parser import parse_date
        assert parse_date(None) is None

    def test_invalid_date_format(self):
        from accounting.statements.parser import parse_date
        assert parse_date('2024-11-15') is None  # Wrong format

    def test_invalid_date_value(self):
        from accounting.statements.parser import parse_date
        assert parse_date('32.13.2024') is None  # Invalid day/month


class TestClassifyTransaction:
    """Tests for classify_transaction() function."""

    def test_pos_purchase(self):
        from accounting.statements.parser import classify_transaction
        assert classify_transaction('POS purchase at store') == 'card_purchase'

    def test_internal_transfer(self):
        from accounting.statements.parser import classify_transaction
        assert classify_transaction('Alim Card from account') == 'internal'

    def test_refund(self):
        from accounting.statements.parser import classify_transaction
        assert classify_transaction('Return from merchant') == 'refund'

    def test_fee(self):
        from accounting.statements.parser import classify_transaction
        assert classify_transaction('Comision administrare') == 'fee'

    def test_cms_transaction(self):
        from accounting.statements.parser import classify_transaction
        assert classify_transaction('Payment +CMS fee') == 'card_purchase'

    def test_other(self):
        from accounting.statements.parser import classify_transaction
        assert classify_transaction('Random transaction') == 'other'


class TestExtractTextFromPdf:
    """Tests for extract_text_from_pdf() function."""

    def test_extracts_text(self):
        from accounting.statements.parser import extract_text_from_pdf
        # Create a minimal PDF-like bytes (mock approach)
        with patch('accounting.statements.parser.PyPDF2.PdfReader') as mock_reader:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = 'Test PDF content'
            mock_reader.return_value.pages = [mock_page]

            result = extract_text_from_pdf(b'fake pdf bytes')
            assert 'Test PDF content' in result


# ============== VENDOR TESTS ==============

class TestExtractVendorName:
    """Tests for extract_vendor_name() function."""

    def test_facebook_pattern(self):
        from accounting.statements.vendors import extract_vendor_name
        assert extract_vendor_name('FACEBK *9DGR2CRV62') == 'FACEBK'

    def test_google_ads_pattern(self):
        from accounting.statements.vendors import extract_vendor_name
        assert extract_vendor_name('GOOGLE *ADS3555304242') == 'GOOGLE ADS'

    def test_claude_ai_pattern(self):
        from accounting.statements.vendors import extract_vendor_name
        assert extract_vendor_name('CLAUDE.AI SUBSCRIPTION') == 'CLAUDE.AI'

    def test_openai_pattern(self):
        from accounting.statements.vendors import extract_vendor_name
        assert extract_vendor_name('OPENAI *CHATGPT SUBSCR') == 'OPENAI CHATGPT'

    def test_digitalocean_pattern(self):
        from accounting.statements.vendors import extract_vendor_name
        assert extract_vendor_name('DIGITALOCEAN.COM') == 'DIGITALOCEAN'

    def test_dreamstime_pattern(self):
        from accounting.statements.vendors import extract_vendor_name
        assert extract_vendor_name('DREAMSTIME.COM purchase') == 'DREAMSTIME'

    def test_shopify_pattern(self):
        from accounting.statements.vendors import extract_vendor_name
        assert extract_vendor_name('SHOPIFY *12345') == 'SHOPIFY'

    def test_empty_string(self):
        from accounting.statements.vendors import extract_vendor_name
        assert extract_vendor_name('') is None

    def test_none(self):
        from accounting.statements.vendors import extract_vendor_name
        assert extract_vendor_name(None) is None

    def test_unmatched_description(self):
        from accounting.statements.vendors import extract_vendor_name
        # Should return None or fallback extraction
        result = extract_vendor_name('Unknown vendor transaction')
        # Could be None or extracted word depending on fallback logic
        assert result is None or isinstance(result, str)


class TestMatchVendor:
    """Tests for match_vendor() function."""

    @patch('accounting.statements.vendors.get_all_vendor_mappings')
    def test_match_with_known_pattern(self, mock_get_mappings):
        from accounting.statements.vendors import match_vendor, reload_patterns

        mock_get_mappings.return_value = [
            {'id': 1, 'pattern': r'FACEBK\s*\*', 'supplier_name': 'Meta', 'supplier_vat': None, 'template_id': None}
        ]
        reload_patterns()

        result = match_vendor('FACEBK *9DGR2CRV62')
        assert result['matched'] is True
        assert result['supplier_name'] == 'Meta'

    @patch('accounting.statements.vendors.get_all_vendor_mappings')
    def test_no_match(self, mock_get_mappings):
        from accounting.statements.vendors import match_vendor, reload_patterns

        mock_get_mappings.return_value = [
            {'id': 1, 'pattern': r'FACEBK\s*\*', 'supplier_name': 'Meta', 'supplier_vat': None, 'template_id': None}
        ]
        reload_patterns()

        result = match_vendor('Unknown Vendor Transaction')
        assert result['matched'] is False
        assert result['supplier_name'] is None

    @patch('accounting.statements.vendors.get_all_vendor_mappings')
    def test_empty_description(self, mock_get_mappings):
        from accounting.statements.vendors import match_vendor, reload_patterns

        mock_get_mappings.return_value = []
        reload_patterns()

        result = match_vendor('')
        assert result['matched'] is False
        assert result['vendor_name'] is None


class TestMatchTransactions:
    """Tests for match_transactions() function."""

    @patch('accounting.statements.vendors.get_all_vendor_mappings')
    def test_matches_multiple_transactions(self, mock_get_mappings):
        from accounting.statements.vendors import match_transactions, reload_patterns

        mock_get_mappings.return_value = [
            {'id': 1, 'pattern': r'FACEBK\s*\*', 'supplier_name': 'Meta', 'supplier_vat': None, 'template_id': None},
            {'id': 2, 'pattern': r'GOOGLE\s*\*\s*ADS', 'supplier_name': 'Google Ads', 'supplier_vat': None, 'template_id': None}
        ]
        reload_patterns()

        transactions = [
            {'description': 'FACEBK *123', 'transaction_type': 'card_purchase'},
            {'description': 'GOOGLE *ADS456', 'transaction_type': 'card_purchase'},
            {'description': 'Unknown', 'transaction_type': 'card_purchase'}
        ]

        result = match_transactions(transactions)

        # Note: 'matched' status is reserved for invoice matching, not vendor matching
        # All non-internal transactions start as 'pending' but have matched_supplier populated
        assert result[0]['status'] == 'pending'
        assert result[0]['matched_supplier'] == 'Meta'
        assert result[1]['status'] == 'pending'
        assert result[1]['matched_supplier'] == 'Google Ads'
        assert result[2]['status'] == 'pending'
        assert result[2]['matched_supplier'] is None

    @patch('accounting.statements.vendors.get_all_vendor_mappings')
    def test_auto_ignores_internal_transfers(self, mock_get_mappings):
        from accounting.statements.vendors import match_transactions, reload_patterns

        mock_get_mappings.return_value = []
        reload_patterns()

        transactions = [
            {'description': 'Alim Card transfer', 'transaction_type': 'internal'}
        ]

        result = match_transactions(transactions)
        assert result[0]['status'] == 'ignored'


class TestGetUnmatchedVendors:
    """Tests for get_unmatched_vendors() function."""

    def test_returns_unique_vendors(self):
        from accounting.statements.vendors import get_unmatched_vendors

        transactions = [
            {'status': 'pending', 'vendor_name': 'VENDOR A'},
            {'status': 'pending', 'vendor_name': 'VENDOR B'},
            {'status': 'pending', 'vendor_name': 'VENDOR A'},  # Duplicate
            {'status': 'matched', 'vendor_name': 'VENDOR C'},  # Should be excluded
        ]

        result = get_unmatched_vendors(transactions)
        assert 'VENDOR A' in result
        assert 'VENDOR B' in result
        assert 'VENDOR C' not in result
        assert len(result) == 2


# ============== DATABASE TESTS ==============

class TestCheckDuplicateTransaction:
    """Tests for check_duplicate_transaction() function."""

    @patch('accounting.statements.database.release_db')
    @patch('accounting.statements.database.get_db')
    @patch('accounting.statements.database.get_cursor')
    def test_finds_duplicate(self, mock_cursor, mock_db, _mock_release):
        from accounting.statements.database import check_duplicate_transaction

        mock_conn = MagicMock()
        mock_db.return_value = mock_conn
        mock_cur = MagicMock()
        mock_cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = {'id': 1}  # Found duplicate

        result = check_duplicate_transaction('12345', '2024-11-15', 100.0, 'Test transaction')
        assert result is True

    @patch('accounting.statements.database.release_db')
    @patch('accounting.statements.database.get_db')
    @patch('accounting.statements.database.get_cursor')
    def test_no_duplicate(self, mock_cursor, mock_db, _mock_release):
        from accounting.statements.database import check_duplicate_transaction

        mock_conn = MagicMock()
        mock_db.return_value = mock_conn
        mock_cur = MagicMock()
        mock_cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = None  # No duplicate

        result = check_duplicate_transaction('12345', '2024-11-15', 100.0, 'Test transaction')
        assert result is False


class TestSaveTransactions:
    """Tests for save_transactions_with_dedup() function."""

    @patch('accounting.statements.database.release_db')
    @patch('accounting.statements.database.get_db')
    @patch('accounting.statements.database.get_cursor')
    def test_saves_transactions(self, mock_cursor, mock_db, _mock_release):
        from accounting.statements.database import save_transactions_with_dedup

        mock_conn = MagicMock()
        mock_db.return_value = mock_conn
        mock_cur = MagicMock()
        mock_cursor.return_value = mock_cur
        # First fetchone returns None (no duplicate), second returns the new ID
        mock_cur.fetchone.side_effect = [None, {'id': 1}, None, {'id': 2}]

        transactions = [
            {'statement_file': 'test.pdf', 'amount': 100, 'description': 'Test 1'},
            {'statement_file': 'test.pdf', 'amount': 200, 'description': 'Test 2'}
        ]

        result = save_transactions_with_dedup(transactions)

        assert result['new_count'] == 2
        assert len(result['new_ids']) == 2
        assert 1 in result['new_ids']
        assert 2 in result['new_ids']
        mock_conn.commit.assert_called_once()

    @patch('accounting.statements.database.release_db')
    @patch('accounting.statements.database.get_db')
    @patch('accounting.statements.database.get_cursor')
    def test_handles_duplicates_in_batch(self, mock_cursor, mock_db, _mock_release):
        from accounting.statements.database import save_transactions_with_dedup

        mock_conn = MagicMock()
        mock_db.return_value = mock_conn
        mock_cur = MagicMock()
        mock_cursor.return_value = mock_cur
        # First transaction: duplicate check returns existing, second: no duplicate
        mock_cur.fetchone.side_effect = [{'id': 99}, None, {'id': 1}]

        transactions = [
            {'statement_file': 'test.pdf', 'amount': 100, 'description': 'Duplicate'},
            {'statement_file': 'test.pdf', 'amount': 200, 'description': 'New'}
        ]

        result = save_transactions_with_dedup(transactions)
        assert result['new_count'] == 1
        assert result['duplicate_count'] == 1


# ============== RATE LIMITER TESTS ==============

class TestRateLimiter:
    """Tests for RateLimiter class."""

    def test_allows_first_request(self):
        from accounting.statements.routes import RateLimiter
        limiter = RateLimiter()

        is_allowed, retry_after = limiter.is_allowed(user_id=1, max_requests=10, window_seconds=60)
        assert is_allowed is True
        assert retry_after == 0

    def test_allows_up_to_limit(self):
        from accounting.statements.routes import RateLimiter
        limiter = RateLimiter()

        # Make 10 requests (the limit)
        for i in range(10):
            is_allowed, _ = limiter.is_allowed(user_id=1, max_requests=10, window_seconds=60)
            assert is_allowed is True

        # 11th request should be blocked
        is_allowed, retry_after = limiter.is_allowed(user_id=1, max_requests=10, window_seconds=60)
        assert is_allowed is False
        assert retry_after > 0

    def test_different_users_have_separate_limits(self):
        from accounting.statements.routes import RateLimiter
        limiter = RateLimiter()

        # Exhaust user 1's limit
        for i in range(10):
            limiter.is_allowed(user_id=1, max_requests=10, window_seconds=60)

        # User 2 should still be allowed
        is_allowed, _ = limiter.is_allowed(user_id=2, max_requests=10, window_seconds=60)
        assert is_allowed is True

    def test_get_remaining(self):
        from accounting.statements.routes import RateLimiter
        limiter = RateLimiter()

        assert limiter.get_remaining(user_id=1, max_requests=10, window_seconds=60) == 10

        # Make 3 requests
        for _ in range(3):
            limiter.is_allowed(user_id=1, max_requests=10, window_seconds=60)

        assert limiter.get_remaining(user_id=1, max_requests=10, window_seconds=60) == 7

    def test_window_expiry(self):
        import time
        from accounting.statements.routes import RateLimiter
        limiter = RateLimiter()

        # Use a very short window for testing
        window = 0.1  # 100ms

        # Exhaust limit
        for i in range(3):
            limiter.is_allowed(user_id=1, max_requests=3, window_seconds=window)

        # Should be blocked
        is_allowed, _ = limiter.is_allowed(user_id=1, max_requests=3, window_seconds=window)
        assert is_allowed is False

        # Wait for window to expire
        time.sleep(0.15)

        # Should be allowed again
        is_allowed, _ = limiter.is_allowed(user_id=1, max_requests=3, window_seconds=window)
        assert is_allowed is True


class TestBulkItemLimits:
    """Tests for bulk operation item count limits."""

    def test_max_bulk_items_constant(self):
        from accounting.statements.routes import MAX_BULK_ITEMS
        assert MAX_BULK_ITEMS == 100

    def test_rate_limit_constants(self):
        from accounting.statements.routes import RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW
        assert RATE_LIMIT_REQUESTS == 10
        assert RATE_LIMIT_WINDOW == 60


# ============== OCR INLINE-LAYOUT TESTS ==============
# Some UniCredit statements are vector-path PDFs (PyPDF2 returns no text) and,
# under the current tesseract, OCR to an *inline* layout: each transaction's
# date, description and signed amount all land on one line, and header fields
# are label-prefixed ("Cont ales RO..", "CUI/CNP 123"). This differs from the
# column-separated OCR layout the parser originally targeted.
# Regression fixture captured from "Extras cont mk AW One 08.2026.pdf".

# Load parser.py standalone (bypass the package __init__, which pulls in Flask
# and DB modules) so these pure-function tests run in any environment.
import importlib.util as _ilu
_parser_path = os.path.join(os.path.dirname(__file__), '..', 'jarvis',
                            'accounting', 'statements', 'parser.py')
_spec = _ilu.spec_from_file_location('statements_parser_standalone', _parser_path)
ocr_parser = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(ocr_parser)

OCR_INLINE_TEXT = """printat de CLAUDIA BRUSLEA

UniCredit Bank

Lista Tranzactii 01.09.2026 08:25:42

Cont ales RO42 BACX 0000 0004 3006 3029 | CARD SABO | RON

Titular de cont AUTOWORLD ONE S.R.L.

CUI/CNP 15128629

Adresa STR.Floresti NR.145 BL.- SC.- ET.- AP.- CLUJ

Istoric oO 1 Ultimele zile

Data inregistrarii @ 01.08.2026 31.08.2026

Tip Toate

Data Data valutei Detaliile tranzactiei Valoare Tranz. Valuta

inregistrarii

31.08.2026 31.08.2026 Int.Appl. to 31/08/26 0,01 RON

31.08.2026 31.08.2026 +CMS CLT-3541834139 Card 5586-84XX-XXXX-3100 -1.247,80 RON
2026.08.31 FACEBK *HNARF5J9J4 POS purchase Auth
code 071963 1.247,80 RON

28.08.2026 28.08.2026 +CMS CLT-3540439447 Card 5586-84XX-XXXX-3100 -2,003,36 RON
2026.08.28 FACEBK *ZWVEJ429J4 POS purchase Auth
code 157087 2.003,36 RON

27.08.2026 27.08.2026 AUTOWORLD ONE S.R.L., CUI/CNP:15128629, 4.000,00 RON
CONT:RO21BACX0000000430063310, LA: UNICREDIT
BANK S.A., Nr op.:1199, transfer disponibil,
Ref.:566515600

03.08.2026 03.08.2026 +CMS CLT-3525844194 Card 5586-84XX-XXXX-3100 -1.040,00 RON
2026.08.01 GOOGLE *ADS1861622105 POS purchase
Auth code 588442 1.040,00 RON

Sold deschidere 03.08.2026 1.729,72 RON
Credit total pentru tranzactiile selectate (4) 11.000,01 RON
Debit total pentru tranzactiile selectate (7) -12.299,55 RON
Totalul tranzactiilor selectate (11) -1.299,54 RON

UniCredit Bank S.A.

Pagina 1

Sold inchidere 31.08.2026 430,18 RON
"""


class TestOcrInlineHeader:
    """Header extraction from inline (label-prefixed) OCR output."""

    def test_account_number(self):
        info = ocr_parser._extract_header_ocr(OCR_INLINE_TEXT)
        assert info['account_number'] == 'RO42BACX0000000430063029'

    def test_company_name(self):
        info = ocr_parser._extract_header_ocr(OCR_INLINE_TEXT)
        assert info['company_name'] == 'AUTOWORLD ONE S.R.L.'

    def test_company_cui(self):
        info = ocr_parser._extract_header_ocr(OCR_INLINE_TEXT)
        assert info['company_cui'] == '15128629'

    def test_period(self):
        info = ocr_parser._extract_header_ocr(OCR_INLINE_TEXT)
        assert info['period_from'] == '2026-08-01'
        assert info['period_to'] == '2026-08-31'


class TestOcrInlineTransactions:
    """Transaction amounts must be read from the inline (trailing) value column."""

    def _txns(self):
        header = {'company_name': 'AUTOWORLD ONE S.R.L.', 'company_cui': '15128629',
                  'account_number': 'RO42BACX0000000430063029'}
        return ocr_parser._extract_transactions_ocr(OCR_INLINE_TEXT, header)

    def test_all_amounts_populated(self):
        txns = self._txns()
        assert len(txns) == 5
        assert all(t['amount'] is not None for t in txns), [t['amount'] for t in txns]

    def test_debit_is_negative(self):
        txns = self._txns()
        debit = next(t for t in txns if t['transaction_date'] == '2026-08-31'
                     and 'FACEBK' in (t['description'] or ''))
        assert debit['amount'] == -1247.80

    def test_ocr_comma_thousands_amount(self):
        # OCR mangled "-2.003,36" into "-2,003,36"; must still parse to -2003.36
        txns = self._txns()
        debit = next(t for t in txns if t['transaction_date'] == '2026-08-28')
        assert debit['amount'] == -2003.36

    def test_credit_is_positive(self):
        txns = self._txns()
        credit = next(t for t in txns if t['transaction_date'] == '2026-08-27')
        assert credit['amount'] == 4000.00

    def test_interest_row(self):
        txns = self._txns()
        interest = next(t for t in txns if t['transaction_date'] == '2026-08-31'
                        and 'Int.Appl' in (t['description'] or ''))
        assert interest['amount'] == 0.01

    def test_header_propagated(self):
        txns = self._txns()
        assert txns[0]['company_cui'] == '15128629'
        assert txns[0]['account_number'] == 'RO42BACX0000000430063029'


class TestOcrInlineSummary:
    """Summary balances/totals read from label-prefixed inline lines."""

    def test_summary(self):
        s = ocr_parser._extract_summary_ocr(OCR_INLINE_TEXT)
        assert s['opening_balance'] == 1729.72
        assert s['closing_balance'] == 430.18
        assert s['credit_count'] == 4
        assert s['credit_total'] == 11000.01
        assert s['debit_count'] == 7
        assert s['debit_total'] == 12299.55


# Run with: pytest tests/test_statements.py -v
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
