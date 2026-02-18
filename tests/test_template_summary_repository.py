"""Unit tests for TemplateRepository and SummaryRepository.

Tests for accounting.templates.repositories.template_repository:
- get_all (with cache, without cache)
- get (found, not found)
- get_by_name (found, not found)
- save (success, duplicate)
- update (success, no fields, not found)
- delete (success, not found)

Tests for accounting.invoices.repositories.summary_repository:
- by_company (no filters, with filters, cache hit)
- by_department (no filters, with company filter)
- by_brand (no filters)
- by_supplier (no filters)
"""
import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from accounting.templates.repositories.template_repository import TemplateRepository, _templates_cache, clear_templates_cache
from accounting.invoices.repositories.summary_repository import SummaryRepository, _summary_cache, clear_summary_cache

_B = 'core.base_repository'  # DB functions (get_db, get_cursor, release_db, dict_from_row)
_T = 'accounting.templates.repositories.template_repository'  # Module-specific (clear_templates_cache)


def _mock_db():
    return MagicMock(), MagicMock()


# ==================== TemplateRepository ====================

class TestTemplateGetAll:

    def setup_method(self):
        clear_templates_cache()

    @patch(f'{_B}.dict_from_row')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_returns_list(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        row = {'id': 1, 'name': 'Meta Template', 'supplier': 'Meta'}
        mock_cursor.fetchall.return_value = [row]
        mock_dict.side_effect = lambda r: dict(r)

        result = TemplateRepository().get_all()

        assert len(result) == 1
        assert result[0]['name'] == 'Meta Template'

    @patch(f'{_B}.dict_from_row')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_uses_cache(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        """Second call uses cache."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [{'id': 1, 'name': 'Test'}]
        mock_dict.side_effect = lambda r: dict(r)

        repo = TemplateRepository()
        result1 = repo.get_all()
        result2 = repo.get_all()

        assert result1 == result2
        assert mock_get_db.call_count == 1


class TestTemplateGet:

    @patch(f'{_B}.dict_from_row')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_found(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        row = {'id': 1, 'name': 'Meta'}
        mock_cursor.fetchone.return_value = row
        mock_dict.return_value = row

        result = TemplateRepository().get(1)
        assert result['name'] == 'Meta'

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_not_found(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        result = TemplateRepository().get(999)
        assert result is None


class TestTemplateGetByName:

    @patch(f'{_B}.dict_from_row')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_found(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        row = {'id': 1, 'name': 'Meta'}
        mock_cursor.fetchone.return_value = row
        mock_dict.return_value = row

        result = TemplateRepository().get_by_name('Meta')
        assert result['name'] == 'Meta'

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_not_found(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        result = TemplateRepository().get_by_name('Nonexistent')
        assert result is None


class TestTemplateSave:

    def setup_method(self):
        clear_templates_cache()

    @patch(f'{_T}.clear_templates_cache')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_success(self, mock_get_db, mock_get_cursor, mock_release, mock_clear):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'id': 10}

        result = TemplateRepository().save(name='New Template', supplier='Test SRL')

        assert result == 10
        mock_conn.commit.assert_called_once()
        mock_clear.assert_called_once()

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_duplicate_raises(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception('duplicate key')

        with pytest.raises(ValueError, match='already exists'):
            TemplateRepository().save(name='Existing')

        mock_conn.rollback.assert_called_once()


class TestTemplateUpdate:

    def test_no_fields_returns_false(self):
        result = TemplateRepository().update(template_id=1)
        assert result is False

    @patch(f'{_T}.clear_templates_cache')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_success(self, mock_get_db, mock_get_cursor, mock_release, mock_clear):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        result = TemplateRepository().update(template_id=1, name='Updated')

        assert result is True
        sql = mock_cursor.execute.call_args[0][0]
        assert 'name = %s' in sql
        assert 'updated_at = CURRENT_TIMESTAMP' in sql
        mock_clear.assert_called_once()

    @patch(f'{_T}.clear_templates_cache')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_not_found(self, mock_get_db, mock_get_cursor, mock_release, mock_clear):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 0

        result = TemplateRepository().update(template_id=999, name='Ghost')

        assert result is False
        mock_clear.assert_not_called()


class TestTemplateDelete:

    @patch(f'{_T}.clear_templates_cache')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_success(self, mock_get_db, mock_get_cursor, mock_release, mock_clear):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        result = TemplateRepository().delete(1)

        assert result is True
        mock_clear.assert_called_once()

    @patch(f'{_T}.clear_templates_cache')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_not_found(self, mock_get_db, mock_get_cursor, mock_release, mock_clear):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 0

        result = TemplateRepository().delete(999)

        assert result is False
        mock_clear.assert_not_called()


# ==================== SummaryRepository ====================

class TestSummaryByCompany:

    def setup_method(self):
        clear_summary_cache()

    @patch(f'{_B}.dict_from_row')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_no_filters(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        row = {'company': 'DWA', 'total_value_ron': 50000, 'invoice_count': 10}
        mock_cursor.fetchall.return_value = [row]
        mock_dict.side_effect = lambda r: dict(r)

        result = SummaryRepository().by_company()

        assert len(result) == 1
        assert result[0]['company'] == 'DWA'
        sql = mock_cursor.execute.call_args[0][0]
        assert 'GROUP BY a.company' in sql

    @patch(f'{_B}.dict_from_row')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_with_date_filter(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []
        mock_dict.side_effect = lambda r: dict(r)

        SummaryRepository().by_company(start_date='2025-01-01', end_date='2025-12-31')

        sql = mock_cursor.execute.call_args[0][0]
        assert 'invoice_date >= %s' in sql
        assert 'invoice_date <= %s' in sql

    @patch(f'{_B}.dict_from_row')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_cache_hit(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        """Second call with same params uses cache."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [{'company': 'DWA', 'total_value_ron': 1000}]
        mock_dict.side_effect = lambda r: dict(r)

        repo = SummaryRepository()
        repo.by_company()
        repo.by_company()

        assert mock_get_db.call_count == 1


class TestSummaryByDepartment:

    def setup_method(self):
        clear_summary_cache()

    @patch(f'{_B}.dict_from_row')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_no_filters(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        row = {'company': 'DWA', 'department': 'Marketing', 'total_value_ron': 30000}
        mock_cursor.fetchall.return_value = [row]
        mock_dict.side_effect = lambda r: dict(r)

        result = SummaryRepository().by_department()

        assert len(result) == 1
        sql = mock_cursor.execute.call_args[0][0]
        assert 'GROUP BY a.company, a.department' in sql

    @patch(f'{_B}.dict_from_row')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_with_company_filter(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []
        mock_dict.side_effect = lambda r: dict(r)

        SummaryRepository().by_department(company='DWA')

        sql = mock_cursor.execute.call_args[0][0]
        assert 'a.company = %s' in sql


class TestSummaryByBrand:

    def setup_method(self):
        clear_summary_cache()

    @patch(f'{_B}.dict_from_row')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_no_filters(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        row = {'brand': 'BT', 'total_value_ron': 20000, 'invoice_count': 5}
        mock_cursor.fetchall.return_value = [row]
        mock_dict.side_effect = lambda r: dict(r)

        result = SummaryRepository().by_brand()

        assert len(result) == 1
        assert result[0]['brand'] == 'BT'
        sql = mock_cursor.execute.call_args[0][0]
        assert 'GROUP BY a.brand' in sql


class TestSummaryBySupplier:

    def setup_method(self):
        clear_summary_cache()

    @patch(f'{_B}.dict_from_row')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_no_filters(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        row = {'supplier': 'Meta', 'total_value_ron': 15000, 'invoice_count': 3}
        mock_cursor.fetchall.return_value = [row]
        mock_dict.side_effect = lambda r: dict(r)

        result = SummaryRepository().by_supplier()

        assert len(result) == 1
        assert result[0]['supplier'] == 'Meta'
        sql = mock_cursor.execute.call_args[0][0]
        assert 'GROUP BY i.supplier' in sql

    @patch(f'{_B}.dict_from_row')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_with_all_filters(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []
        mock_dict.side_effect = lambda r: dict(r)

        SummaryRepository().by_supplier(
            company='DWA', start_date='2025-01-01', end_date='2025-12-31',
            department='Marketing', brand='BT'
        )

        sql = mock_cursor.execute.call_args[0][0]
        assert 'a.company = %s' in sql
        assert 'a.department = %s' in sql
        assert 'a.brand = %s' in sql
        assert 'invoice_date >= %s' in sql


class TestSummaryConnectionRelease:

    def setup_method(self):
        clear_summary_cache()

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_releases_on_error(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception('DB error')

        with pytest.raises(Exception):
            SummaryRepository().by_company()

        mock_release.assert_called_once_with(mock_conn)
