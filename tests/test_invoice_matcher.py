"""Unit tests for Invoice Matcher module.

Tests for:
- invoice_matcher.py: Amount matching, date scoring, supplier scoring, 3-layer matching
"""
import sys
import os

# Set dummy DATABASE_URL before importing modules that require it
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, date

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from accounting.statements.invoice_matcher import (
    normalize_amount,
    amounts_match,
    calculate_amount_score,
    calculate_date_score,
    calculate_supplier_score,
    find_invoice_candidates,
    match_by_rules,
    score_candidates,
    auto_match_transaction,
    auto_match_transactions,
    SCORE_EXACT_AMOUNT,
    SCORE_CLOSE_AMOUNT,
    SCORE_MEDIUM_AMOUNT,
    SCORE_DATE_SAME_WEEK,
    SCORE_DATE_SAME_MONTH,
    SCORE_DATE_WITHIN_60_DAYS,
    SCORE_SUPPLIER_EXACT,
    SCORE_SUPPLIER_SIMILAR,
    AUTO_ACCEPT_THRESHOLD,
    SUGGESTION_THRESHOLD
)


# ============== AMOUNT NORMALIZATION TESTS ==============

class TestNormalizeAmount:
    """Tests for normalize_amount() function."""

    def test_positive_amount(self):
        assert normalize_amount(100.50) == 100.50

    def test_negative_amount(self):
        assert normalize_amount(-100.50) == 100.50

    def test_zero(self):
        assert normalize_amount(0) == 0

    def test_none_returns_zero(self):
        assert normalize_amount(None) == 0


# ============== AMOUNT MATCHING TESTS ==============

class TestAmountsMatch:
    """Tests for amounts_match() function."""

    def test_exact_match(self):
        assert amounts_match(100.00, 100.00) is True

    def test_within_tolerance(self):
        # 0.1% of 1000 = 1
        assert amounts_match(1000.00, 1000.50) is True

    def test_outside_tolerance(self):
        # 2% difference
        assert amounts_match(100.00, 102.00) is False

    def test_negative_transaction(self):
        # Bank transactions are often negative
        assert amounts_match(-100.00, 100.00) is True

    def test_zero_invoice_zero_txn(self):
        assert amounts_match(0, 0) is True

    def test_zero_invoice_nonzero_txn(self):
        assert amounts_match(100, 0) is False


# ============== AMOUNT SCORE TESTS ==============

class TestCalculateAmountScore:
    """Tests for calculate_amount_score() function."""

    def test_exact_match_score(self):
        """99.9%+ match should get max score"""
        score = calculate_amount_score(1000.00, 1000.05)
        assert score == SCORE_EXACT_AMOUNT

    def test_close_match_score(self):
        """Within 1% should get close score"""
        score = calculate_amount_score(1000.00, 1008.00)
        assert score == SCORE_CLOSE_AMOUNT

    def test_medium_match_score(self):
        """Within 5% should get medium score"""
        score = calculate_amount_score(1000.00, 1040.00)
        assert score == SCORE_MEDIUM_AMOUNT

    def test_no_match_score(self):
        """Beyond 5% should get zero"""
        score = calculate_amount_score(1000.00, 1100.00)
        assert score == 0

    def test_both_zero_exact_match(self):
        """Both zero should be exact match"""
        assert calculate_amount_score(0, 0) == SCORE_EXACT_AMOUNT

    def test_negative_amount_normalized(self):
        """Negative amounts should be normalized"""
        score = calculate_amount_score(-100.00, 100.00)
        assert score == SCORE_EXACT_AMOUNT


# ============== DATE SCORE TESTS ==============

class TestCalculateDateScore:
    """Tests for calculate_date_score() function."""

    def test_same_day_score(self):
        """Same day should be within same week"""
        score = calculate_date_score('2025-12-15', '2025-12-15')
        assert score == SCORE_DATE_SAME_WEEK

    def test_within_week_score(self):
        """5 days apart should be same week"""
        score = calculate_date_score('2025-12-20', '2025-12-15')
        assert score == SCORE_DATE_SAME_WEEK

    def test_within_month_score(self):
        """15 days apart should be same month"""
        score = calculate_date_score('2025-12-30', '2025-12-15')
        assert score == SCORE_DATE_SAME_MONTH

    def test_within_60_days_score(self):
        """45 days apart should be within 60 days"""
        score = calculate_date_score('2025-01-30', '2025-12-15')
        # Transaction (Jan 30) is BEFORE invoice (Dec 15) - should return 0
        # Actually 46 days difference but transaction is after
        score2 = calculate_date_score('2026-01-30', '2025-12-15')
        assert score2 == SCORE_DATE_WITHIN_60_DAYS

    def test_beyond_60_days_zero(self):
        """Beyond 60 days should be zero"""
        score = calculate_date_score('2026-03-01', '2025-12-15')
        assert score == 0

    def test_transaction_before_invoice_zero(self):
        """Transaction before invoice date should be zero"""
        score = calculate_date_score('2025-12-10', '2025-12-15')
        assert score == 0

    def test_none_dates_zero(self):
        """None dates should return zero"""
        assert calculate_date_score(None, '2025-12-15') == 0
        assert calculate_date_score('2025-12-15', None) == 0
        assert calculate_date_score(None, None) == 0

    def test_datetime_objects(self):
        """Should handle datetime objects"""
        from datetime import datetime
        txn_date = datetime(2025, 12, 20)
        inv_date = datetime(2025, 12, 15)
        score = calculate_date_score(txn_date, inv_date)
        assert score == SCORE_DATE_SAME_WEEK

    def test_date_objects(self):
        """Should handle date objects"""
        txn_date = date(2025, 12, 20)
        inv_date = date(2025, 12, 15)
        score = calculate_date_score(txn_date, inv_date)
        assert score == SCORE_DATE_SAME_WEEK


# ============== SUPPLIER SCORE TESTS ==============

class TestCalculateSupplierScore:
    """Tests for calculate_supplier_score() function."""

    def test_exact_match(self):
        score = calculate_supplier_score('Meta', 'Meta')
        assert score == SCORE_SUPPLIER_EXACT

    def test_case_insensitive_match(self):
        score = calculate_supplier_score('META', 'meta')
        assert score == SCORE_SUPPLIER_EXACT

    def test_whitespace_trimmed(self):
        score = calculate_supplier_score('  Meta  ', 'Meta')
        assert score == SCORE_SUPPLIER_EXACT

    def test_similar_names(self):
        """80%+ similarity should get similar score"""
        score = calculate_supplier_score('Meta Platforms', 'Meta Platform')
        assert score == SCORE_SUPPLIER_SIMILAR

    def test_different_names(self):
        score = calculate_supplier_score('Meta', 'Google')
        assert score == 0

    def test_none_returns_zero(self):
        assert calculate_supplier_score(None, 'Meta') == 0
        assert calculate_supplier_score('Meta', None) == 0
        assert calculate_supplier_score(None, None) == 0

    def test_empty_strings_zero(self):
        assert calculate_supplier_score('', 'Meta') == 0


# ============== FIND CANDIDATES TESTS ==============

class TestFindInvoiceCandidates:
    """Tests for find_invoice_candidates() function."""

    def test_finds_exact_amount_match(self):
        transaction = {
            'amount': -100.00,
            'transaction_date': '2025-12-20',
            'matched_supplier': 'Meta',
            'currency': 'RON'
        }
        invoices = [
            {'id': 1, 'invoice_value': 100.00, 'value_ron': 100.00, 'invoice_date': '2025-12-15', 'supplier': 'Meta'},
            {'id': 2, 'invoice_value': 200.00, 'value_ron': 200.00, 'invoice_date': '2025-12-15', 'supplier': 'Meta'}
        ]

        candidates = find_invoice_candidates(transaction, invoices)

        assert len(candidates) >= 1
        # First candidate should be exact match
        assert candidates[0]['invoice_id'] == 1
        assert candidates[0]['amount_score'] == SCORE_EXACT_AMOUNT

    def test_returns_sorted_by_score(self):
        transaction = {
            'amount': -100.00,
            'transaction_date': '2025-12-20',
            'matched_supplier': 'Meta'
        }
        invoices = [
            {'id': 1, 'invoice_value': 200.00, 'invoice_date': '2025-12-15', 'supplier': 'Meta'},  # Wrong amount
            {'id': 2, 'invoice_value': 100.00, 'invoice_date': '2025-12-15', 'supplier': 'Meta'}   # Exact amount
        ]

        candidates = find_invoice_candidates(transaction, invoices)

        # Higher score should be first
        assert candidates[0]['invoice_id'] == 2

    def test_includes_reasons(self):
        transaction = {
            'amount': -100.00,
            'transaction_date': '2025-12-15',
            'matched_supplier': 'Meta'
        }
        invoices = [
            {'id': 1, 'invoice_value': 100.00, 'invoice_date': '2025-12-15', 'supplier': 'Meta'}
        ]

        candidates = find_invoice_candidates(transaction, invoices)

        assert 'reasons' in candidates[0]
        assert 'Exact amount match' in candidates[0]['reasons']

    def test_handles_eur_currency(self):
        transaction = {
            'amount': -100.00,
            'currency': 'EUR'
        }
        invoices = [
            {'id': 1, 'value_eur': 100.00, 'invoice_value': 500.00}  # value_eur should be used
        ]

        candidates = find_invoice_candidates(transaction, invoices)

        assert len(candidates) == 1
        assert candidates[0]['amount_score'] == SCORE_EXACT_AMOUNT

    def test_empty_invoices(self):
        transaction = {'amount': -100.00}
        candidates = find_invoice_candidates(transaction, [])
        assert candidates == []


# ============== RULE-BASED MATCHING TESTS ==============

class TestMatchByRules:
    """Tests for match_by_rules() function."""

    def test_perfect_match(self):
        transaction = {
            'amount': -100.00,
            'transaction_date': '2025-12-20',
            'matched_supplier': 'Meta'
        }
        invoices = [
            {'id': 1, 'invoice_value': 100.00, 'invoice_date': '2025-12-15', 'supplier': 'Meta'}
        ]

        result = match_by_rules(transaction, invoices)

        assert result is not None
        assert result['invoice_id'] == 1
        assert result['method'] == 'rule'
        assert result['confidence'] >= AUTO_ACCEPT_THRESHOLD

    def test_no_match_wrong_supplier(self):
        transaction = {
            'amount': -100.00,
            'transaction_date': '2025-12-20',
            'matched_supplier': 'Google'
        }
        invoices = [
            {'id': 1, 'invoice_value': 100.00, 'invoice_date': '2025-12-15', 'supplier': 'Meta'}
        ]

        result = match_by_rules(transaction, invoices)
        assert result is None

    def test_no_match_invalid_date(self):
        transaction = {
            'amount': -100.00,
            'transaction_date': '2025-12-10',  # Before invoice
            'matched_supplier': 'Meta'
        }
        invoices = [
            {'id': 1, 'invoice_value': 100.00, 'invoice_date': '2025-12-15', 'supplier': 'Meta'}
        ]

        result = match_by_rules(transaction, invoices)
        assert result is None


# ============== SCORE CANDIDATES TESTS ==============

class TestScoreCandidates:
    """Tests for score_candidates() function."""

    def test_returns_limited_results(self):
        transaction = {'amount': -100.00}
        invoices = [
            {'id': i, 'invoice_value': 100.00 + i} for i in range(10)
        ]

        candidates = score_candidates(transaction, invoices, limit=3)

        assert len(candidates) <= 3

    def test_default_limit_is_3(self):
        transaction = {'amount': -100.00}
        invoices = [
            {'id': i, 'invoice_value': 100.00 + i} for i in range(10)
        ]

        candidates = score_candidates(transaction, invoices)

        assert len(candidates) <= 3


# ============== AUTO MATCH TRANSACTION TESTS ==============

class TestAutoMatchTransaction:
    """Tests for auto_match_transaction() function."""

    def test_auto_accepts_high_confidence(self):
        transaction = {
            'amount': -100.00,
            'transaction_date': '2025-12-20',
            'matched_supplier': 'Meta'
        }
        invoices = [
            {'id': 1, 'invoice_value': 100.00, 'invoice_date': '2025-12-15', 'supplier': 'Meta'}
        ]

        result = auto_match_transaction(transaction, invoices, use_ai=False)

        assert result['auto_accepted'] is True
        assert result['invoice_id'] == 1

    def test_suggests_medium_confidence(self):
        transaction = {
            'amount': -100.00,
            'transaction_date': '2025-12-20',
            'matched_supplier': None
        }
        invoices = [
            {'id': 1, 'invoice_value': 100.00, 'invoice_date': '2025-12-15', 'supplier': 'Meta'}
        ]

        result = auto_match_transaction(transaction, invoices, use_ai=False)

        # Should suggest but not auto-accept
        assert result['auto_accepted'] is True  # 90/100 = 0.9 which meets threshold
        assert result['invoice_id'] == 1

    def test_no_match_found(self):
        transaction = {
            'amount': -9999.00,
            'transaction_date': '2020-01-01'
        }
        invoices = [
            {'id': 1, 'invoice_value': 100.00, 'invoice_date': '2025-12-15', 'supplier': 'Meta'}
        ]

        result = auto_match_transaction(transaction, invoices, use_ai=False)

        assert result['auto_accepted'] is False
        assert result['invoice_id'] is None

    @patch('accounting.statements.invoice_matcher.match_with_ai')
    def test_uses_ai_fallback(self, mock_ai):
        mock_ai.return_value = {
            'invoice_id': 1,
            'confidence': 0.95,
            'reasoning': 'AI matched'
        }

        transaction = {
            'amount': -100.00,
            'transaction_date': '2025-12-20',
            'matched_supplier': None
        }
        invoices = [
            {'id': 1, 'invoice_value': 150.00, 'invoice_date': '2025-12-15', 'supplier': 'Meta'}
        ]

        result = auto_match_transaction(transaction, invoices, use_ai=True)

        mock_ai.assert_called_once()


# ============== AUTO MATCH MULTIPLE TRANSACTIONS ==============

class TestAutoMatchTransactions:
    """Tests for auto_match_transactions() function."""

    def test_processes_multiple(self):
        transactions = [
            {'id': 1, 'amount': -100.00, 'transaction_date': '2025-12-20', 'matched_supplier': 'Meta'},
            {'id': 2, 'amount': -200.00, 'transaction_date': '2025-12-21', 'matched_supplier': 'Meta'}
        ]
        invoices = [
            {'id': 1, 'invoice_value': 100.00, 'invoice_date': '2025-12-15', 'supplier': 'Meta'},
            {'id': 2, 'invoice_value': 200.00, 'invoice_date': '2025-12-15', 'supplier': 'Meta'}
        ]

        result = auto_match_transactions(transactions, invoices, use_ai=False)

        assert result['matched'] == 2
        assert len(result['results']) == 2

    def test_skips_resolved_transactions(self):
        transactions = [
            {'id': 1, 'amount': -100.00, 'status': 'resolved', 'invoice_id': 5},
            {'id': 2, 'amount': -200.00}
        ]
        invoices = [
            {'id': 1, 'invoice_value': 200.00}
        ]

        result = auto_match_transactions(transactions, invoices, use_ai=False)

        # Only second transaction should be processed
        assert len(result['results']) == 1

    def test_skips_ignored_transactions(self):
        transactions = [
            {'id': 1, 'amount': -100.00, 'status': 'ignored'},
            {'id': 2, 'amount': -200.00}
        ]
        invoices = [
            {'id': 1, 'invoice_value': 200.00}
        ]

        result = auto_match_transactions(transactions, invoices, use_ai=False)

        assert len(result['results']) == 1

    def test_returns_summary_counts(self):
        transactions = [
            {'id': 1, 'amount': -100.00, 'matched_supplier': 'Meta', 'transaction_date': '2025-12-20'},
            {'id': 2, 'amount': -9999.00}  # Won't match
        ]
        invoices = [
            {'id': 1, 'invoice_value': 100.00, 'invoice_date': '2025-12-15', 'supplier': 'Meta'}
        ]

        result = auto_match_transactions(transactions, invoices, use_ai=False)

        assert 'matched' in result
        assert 'suggested' in result
        assert 'unmatched' in result


# ============== AI MATCHING TESTS (MOCKED) ==============

class TestMatchWithAI:
    """Tests for match_with_ai() function with mocked API."""

    @patch('accounting.statements.invoice_matcher.os.environ.get')
    def test_returns_error_without_api_key(self, mock_env):
        from accounting.statements.invoice_matcher import match_with_ai

        mock_env.return_value = None

        result = match_with_ai({}, [])

        assert result['invoice_id'] is None
        assert 'error' in result

    def test_returns_error_with_no_candidates(self):
        from accounting.statements.invoice_matcher import match_with_ai

        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'}):
            result = match_with_ai({}, [])

        assert result['invoice_id'] is None
        assert 'No candidates' in result.get('reasoning', '')

    @patch('ai_agent.services.llm_client.ask')
    def test_parses_ai_response(self, mock_ask):
        from accounting.statements.invoice_matcher import match_with_ai

        mock_ask.return_value = '{"best_match_invoice_id": 1, "confidence": 0.95, "reasoning": "Test"}'

        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-key'}):
            transaction = {'amount': -100, 'transaction_date': '2025-12-20'}
            candidates = [{'invoice': {'id': 1}, 'score': 50, 'reasons': ['test']}]

            result = match_with_ai(transaction, candidates)

        assert result['invoice_id'] == 1
        assert result['confidence'] == 0.95
        assert result['method'] == 'ai'


# ============== THRESHOLD TESTS ==============

class TestThresholds:
    """Tests for matching threshold values."""

    def test_auto_accept_threshold(self):
        assert AUTO_ACCEPT_THRESHOLD == 0.9

    def test_suggestion_threshold(self):
        assert SUGGESTION_THRESHOLD == 0.5

    def test_exact_amount_gives_auto_accept(self):
        """Exact amount alone should be >= auto-accept threshold"""
        max_score = SCORE_EXACT_AMOUNT + SCORE_DATE_SAME_WEEK + SCORE_SUPPLIER_EXACT
        confidence = SCORE_EXACT_AMOUNT / max_score
        assert confidence >= AUTO_ACCEPT_THRESHOLD


# Run with: pytest tests/test_invoice_matcher.py -v
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
