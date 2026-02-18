"""Unit tests for CompanyRepository and module-level VAT functions.

Tests for core.organization.repositories.company_repository:
- _normalize_vat (pure function, no DB)
- _extract_vat_numbers (pure function, no DB)
- CompanyRepository.match_by_vat (mocks get_all_with_vat_and_brands)
"""
import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from core.organization.repositories.company_repository import (
    _normalize_vat,
    _extract_vat_numbers,
    CompanyRepository,
)


class TestNormalizeVat:
    """Tests for _normalize_vat() pure function."""

    def test_strips_spaces_from_prefix(self):
        """'RO 225615' -> 'RO225615'"""
        assert _normalize_vat('RO 225615') == 'RO225615'

    def test_removes_cui_prefix(self):
        """'CUI: 225615' -> '225615'"""
        assert _normalize_vat('CUI: 225615') == '225615'

    def test_removes_cif_and_ro_prefix(self):
        """'CIF:RO 225615' -> 'RO225615'"""
        assert _normalize_vat('CIF:RO 225615') == 'RO225615'

    def test_empty_string(self):
        """Empty string returns empty string."""
        assert _normalize_vat('') == ''

    def test_none(self):
        """None returns empty string."""
        assert _normalize_vat(None) == ''

    def test_already_normalized(self):
        """Already normalized VAT passes through."""
        assert _normalize_vat('RO12345678') == 'RO12345678'

    def test_lowercase_is_uppercased(self):
        """Lowercase input is uppercased."""
        assert _normalize_vat('ro12345678') == 'RO12345678'

    def test_strips_whitespace(self):
        """Leading/trailing whitespace is stripped."""
        assert _normalize_vat('  RO12345678  ') == 'RO12345678'

    def test_removes_dashes(self):
        """Dashes between parts are removed."""
        assert _normalize_vat('RO-123-456') == 'RO123456'

    def test_removes_dots(self):
        """Dots are removed."""
        assert _normalize_vat('RO.123.456') == 'RO123456'

    def test_removes_vat_prefix(self):
        """VAT: prefix is removed."""
        assert _normalize_vat('VAT: RO12345678') == 'RO12345678'

    def test_removes_tax_id_prefix(self):
        """TAX ID: prefix is removed."""
        assert _normalize_vat('TAX ID: 12345678') == '12345678'

    def test_removes_nr_prefix(self):
        """NR. prefix is removed."""
        assert _normalize_vat('NR. 12345678') == '12345678'

    def test_cui_without_colon(self):
        """CUI prefix without colon is removed."""
        assert _normalize_vat('CUI 225615') == '225615'

    def test_slashes_removed(self):
        """Slashes are removed."""
        assert _normalize_vat('RO/225/615') == 'RO225615'


class TestExtractVatNumbers:
    """Tests for _extract_vat_numbers() pure function."""

    def test_extracts_from_ro_prefix(self):
        """'RO225615' -> '225615'"""
        assert _extract_vat_numbers('RO225615') == '225615'

    def test_extracts_from_ie_prefix(self):
        """'IE9692928F' -> '9692928' (letters stripped)."""
        assert _extract_vat_numbers('IE9692928F') == '9692928'

    def test_empty_string(self):
        """Empty string returns empty string."""
        assert _extract_vat_numbers('') == ''

    def test_none(self):
        """None returns empty string."""
        assert _extract_vat_numbers(None) == ''

    def test_numbers_only(self):
        """Pure numeric string passes through."""
        assert _extract_vat_numbers('12345678') == '12345678'

    def test_letters_only(self):
        """All-letter string returns empty."""
        assert _extract_vat_numbers('ABCDEF') == ''

    def test_mixed_with_spaces(self):
        """Spaces and letters stripped, numbers kept."""
        assert _extract_vat_numbers('RO 123 456') == '123456'

    def test_special_characters(self):
        """Special chars stripped, numbers kept."""
        assert _extract_vat_numbers('RO-12.34/56') == '123456'


class TestMatchByVat:
    """Tests for CompanyRepository.match_by_vat()."""

    def _make_company(self, company_id, name, vat, brands=''):
        return {
            'id': company_id,
            'company': name,
            'vat': vat,
            'brands': brands,
            'brands_list': [],
        }

    @patch.object(CompanyRepository, 'get_all_with_vat_and_brands')
    def test_exact_match_after_normalization(self, mock_get_all):
        """Finds company when normalized VATs match exactly."""
        companies = [
            self._make_company(1, 'AUTOWORLD SRL', 'RO12345678'),
            self._make_company(2, 'OTHER SRL', 'RO99999999'),
        ]
        mock_get_all.return_value = companies

        repo = CompanyRepository()
        result = repo.match_by_vat('RO 12345678')

        assert result is not None
        assert result['id'] == 1
        assert result['company'] == 'AUTOWORLD SRL'

    @patch.object(CompanyRepository, 'get_all_with_vat_and_brands')
    def test_numeric_match(self, mock_get_all):
        """Finds company by numeric-only match when exact fails."""
        companies = [
            self._make_company(1, 'AUTOWORLD SRL', 'RO225615'),
        ]
        mock_get_all.return_value = companies

        repo = CompanyRepository()
        result = repo.match_by_vat('CUI 225615')

        assert result is not None
        assert result['id'] == 1
        assert result['company'] == 'AUTOWORLD SRL'

    @patch.object(CompanyRepository, 'get_all_with_vat_and_brands')
    def test_no_match(self, mock_get_all):
        """Returns None when no company matches."""
        companies = [
            self._make_company(1, 'AUTOWORLD SRL', 'RO12345678'),
        ]
        mock_get_all.return_value = companies

        repo = CompanyRepository()
        result = repo.match_by_vat('XX999999')

        assert result is None

    def test_empty_vat_returns_none(self):
        """Empty VAT string returns None without querying DB."""
        repo = CompanyRepository()
        result = repo.match_by_vat('')

        assert result is None

    def test_none_vat_returns_none(self):
        """None VAT returns None without querying DB."""
        repo = CompanyRepository()
        result = repo.match_by_vat(None)

        assert result is None

    @patch.object(CompanyRepository, 'get_all_with_vat_and_brands')
    def test_exact_match_takes_priority_over_numeric(self, mock_get_all):
        """Exact normalized match is returned even if numeric would also match."""
        companies = [
            self._make_company(1, 'COMPANY A', 'RO225615'),
            self._make_company(2, 'COMPANY B', '225615'),
        ]
        mock_get_all.return_value = companies

        repo = CompanyRepository()
        # 'RO225615' normalizes to 'RO225615' — exact match with company 1
        result = repo.match_by_vat('RO225615')

        assert result is not None
        assert result['id'] == 1

    @patch.object(CompanyRepository, 'get_all_with_vat_and_brands')
    def test_company_with_empty_vat_skipped(self, mock_get_all):
        """Companies with empty/None VAT are not matched."""
        companies = [
            self._make_company(1, 'NO VAT CO', ''),
            self._make_company(2, 'NULL VAT CO', None),
            self._make_company(3, 'REAL CO', 'RO12345678'),
        ]
        mock_get_all.return_value = companies

        repo = CompanyRepository()
        result = repo.match_by_vat('RO12345678')

        assert result is not None
        assert result['id'] == 3

    @patch.object(CompanyRepository, 'get_all_with_vat_and_brands')
    def test_cif_prefix_match(self, mock_get_all):
        """'CIF:RO 225615' matches company with 'RO225615'."""
        companies = [
            self._make_company(1, 'CIF COMPANY', 'RO225615'),
        ]
        mock_get_all.return_value = companies

        repo = CompanyRepository()
        result = repo.match_by_vat('CIF:RO 225615')

        assert result is not None
        assert result['id'] == 1

    @patch.object(CompanyRepository, 'get_all_with_vat_and_brands')
    def test_ie_numeric_match(self, mock_get_all):
        """Irish VAT 'IE9692928F' matched by numeric '9692928'."""
        companies = [
            self._make_company(1, 'META IRELAND', 'IE9692928F'),
        ]
        mock_get_all.return_value = companies

        repo = CompanyRepository()
        # Search with just the numeric portion
        result = repo.match_by_vat('9692928')

        assert result is not None
        assert result['id'] == 1


class TestCompanyRepositoryGetAll:
    """Tests for CompanyRepository.get_all() with cache."""

    @patch('core.base_repository.release_db')
    @patch('core.base_repository.get_cursor')
    @patch('core.base_repository.get_db')
    @patch('core.organization.repositories.company_repository._is_cache_valid')
    def test_fetches_from_db_when_cache_invalid(self, mock_cache_valid, mock_get_db, mock_get_cursor, mock_release):
        """Queries DB when cache is not valid."""
        mock_cache_valid.return_value = False
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {'id': 1, 'company': 'Test Co', 'vat': 'RO123'},
        ]

        repo = CompanyRepository()
        result = repo.get_all()

        assert len(result) == 1
        mock_cursor.execute.assert_called_once()
        mock_release.assert_called_once_with(mock_conn)


class TestCompanyRepositoryGet:
    """Tests for CompanyRepository.get() by ID."""

    @patch('core.base_repository.dict_from_row')
    @patch('core.base_repository.release_db')
    @patch('core.base_repository.get_cursor')
    @patch('core.base_repository.get_db')
    def test_found(self, mock_get_db, mock_get_cursor, mock_release, mock_dict_from_row):
        """Returns company dict when found."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        row = {'id': 1, 'company': 'Test Co', 'vat': 'RO123'}
        mock_cursor.fetchone.return_value = row
        mock_dict_from_row.return_value = row

        repo = CompanyRepository()
        result = repo.get(1)

        assert result is not None
        assert result['id'] == 1

    @patch('core.base_repository.release_db')
    @patch('core.base_repository.get_cursor')
    @patch('core.base_repository.get_db')
    def test_not_found(self, mock_get_db, mock_get_cursor, mock_release):
        """Returns None when company ID doesn't exist."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        repo = CompanyRepository()
        result = repo.get(999)

        assert result is None
