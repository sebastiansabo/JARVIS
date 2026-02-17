"""Tests for the KPI formula engine (safe parser/evaluator)."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from marketing.services.formula_engine import extract_variables, evaluate, validate


# ---- extract_variables ----

class TestExtractVariables:
    def test_simple_division(self):
        assert extract_variables('spent / leads') == ['spent', 'leads']

    def test_multiplication(self):
        assert extract_variables('clicks / impressions * 100') == ['clicks', 'impressions']

    def test_complex_with_parens(self):
        result = extract_variables('(likes + comments + shares) / impressions * 100')
        assert set(result) == {'likes', 'comments', 'shares', 'impressions'}
        assert len(result) == 4

    def test_none_returns_empty(self):
        assert extract_variables(None) == []

    def test_empty_string_returns_empty(self):
        assert extract_variables('') == []

    def test_whitespace_only_returns_empty(self):
        assert extract_variables('   ') == []

    def test_invalid_syntax_returns_empty(self):
        assert extract_variables('spent / ') == []

    def test_single_variable(self):
        assert extract_variables('total') == ['total']

    def test_no_duplicates(self):
        result = extract_variables('a + a + b')
        assert set(result) == {'a', 'b'}
        assert len(result) == 2


# ---- evaluate ----

class TestEvaluate:
    def test_simple_division(self):
        result = evaluate('spent / leads', {'spent': 1000.0, 'leads': 50.0})
        assert result == 20.0

    def test_multiplication_with_constant(self):
        result = evaluate('clicks / impressions * 100', {'clicks': 500.0, 'impressions': 10000.0})
        assert result == 5.0

    def test_complex_formula(self):
        result = evaluate(
            '(likes + comments + shares) / impressions * 100',
            {'likes': 100, 'comments': 50, 'shares': 50, 'impressions': 10000}
        )
        assert result == 2.0

    def test_cpm_formula(self):
        result = evaluate('spent / impressions * 1000', {'spent': 500.0, 'impressions': 100000.0})
        assert result == 5.0

    def test_subtraction(self):
        result = evaluate('revenue - spent', {'revenue': 5000.0, 'spent': 3000.0})
        assert result == 2000.0

    def test_addition(self):
        result = evaluate('a + b + c', {'a': 10, 'b': 20, 'c': 30})
        assert result == 60.0

    def test_negative_result(self):
        result = evaluate('a - b', {'a': 10, 'b': 30})
        assert result == -20.0

    def test_parentheses_priority(self):
        result = evaluate('(a + b) * c', {'a': 2, 'b': 3, 'c': 4})
        assert result == 20.0

    def test_returns_float(self):
        result = evaluate('a + b', {'a': 1, 'b': 2})
        assert isinstance(result, float)


# ---- evaluate errors ----

class TestEvaluateErrors:
    def test_division_by_zero(self):
        with pytest.raises(ZeroDivisionError):
            evaluate('a / b', {'a': 100, 'b': 0})

    def test_undefined_variable(self):
        with pytest.raises(ValueError, match='Undefined variable'):
            evaluate('a / b', {'a': 100})

    def test_empty_formula(self):
        with pytest.raises(ValueError, match='Empty formula'):
            evaluate('', {'a': 1})

    def test_none_formula(self):
        with pytest.raises(ValueError, match='Empty formula'):
            evaluate(None, {'a': 1})


# ---- safety ----

class TestSafety:
    def test_rejects_function_call(self):
        with pytest.raises(ValueError, match='Unsafe'):
            evaluate('abs(a)', {'a': -1})

    def test_rejects_import(self):
        with pytest.raises((ValueError, SyntaxError)):
            evaluate('__import__("os")', {})

    def test_rejects_attribute_access(self):
        with pytest.raises(ValueError, match='Unsafe'):
            evaluate('a.__class__', {'a': 1})

    def test_rejects_list_comprehension(self):
        with pytest.raises((ValueError, SyntaxError)):
            evaluate('[x for x in range(10)]', {})

    def test_rejects_lambda(self):
        with pytest.raises((ValueError, SyntaxError)):
            evaluate('lambda: 1', {})


# ---- validate ----

class TestValidate:
    def test_valid_formula(self):
        is_valid, error, variables = validate('spent / leads')
        assert is_valid is True
        assert error is None
        assert variables == ['spent', 'leads']

    def test_empty_formula(self):
        is_valid, error, variables = validate('')
        assert is_valid is True
        assert variables == []

    def test_none_formula(self):
        is_valid, error, variables = validate(None)
        assert is_valid is True
        assert variables == []

    def test_syntax_error(self):
        is_valid, error, variables = validate('spent /')
        assert is_valid is False
        assert 'Syntax' in error

    def test_unsafe_formula(self):
        is_valid, error, variables = validate('abs(x)')
        assert is_valid is False
        assert 'Unsafe' in error
