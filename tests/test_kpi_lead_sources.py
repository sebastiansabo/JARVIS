"""Tests for the KPI 'Project Leads' source (Phase 3).

- KpiRepository._lead_count_sql — pure filter→SQL builder
- KpiRepository.link/get/unlink lead sources (mocked DB)
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

_B = 'core.base_repository'


class TestLeadCountSql:

    def _repo(self):
        from marketing.repositories.kpi_repo import KpiRepository
        return KpiRepository

    def test_no_filters_counts_all_project_leads(self):
        sql, params = self._repo()._lead_count_sql(5, {})
        assert 'FROM mkt_project_leads' in sql
        assert sql.rstrip().endswith('WHERE project_id = %s')
        assert params == [5]

    def test_status_filter_uses_array_any(self):
        sql, params = self._repo()._lead_count_sql(5, {'status_filter': ['qualified', 'converted']})
        assert 'status = ANY(%s)' in sql
        assert ['qualified', 'converted'] in params

    def test_empty_status_list_ignored(self):
        sql, params = self._repo()._lead_count_sql(5, {'status_filter': []})
        assert 'ANY' not in sql
        assert params == [5]

    def test_source_filter_matches_source_and_utm(self):
        sql, params = self._repo()._lead_count_sql(5, {'source_filter': 'facebook'})
        assert 'ILIKE' in sql
        assert params.count('%facebook%') == 3   # source, utm_source, utm_campaign

    def test_date_range_inclusive_end(self):
        sql, params = self._repo()._lead_count_sql(5, {'date_from': '2026-01-01', 'date_to': '2026-02-01'})
        assert 'created_at >= %s' in sql
        assert "INTERVAL '1 day'" in sql     # date_to is inclusive of the whole day
        assert '2026-01-01' in params and '2026-02-01' in params

    def test_combined_filters_param_order(self):
        sql, params = self._repo()._lead_count_sql(
            9, {'status_filter': ['new'], 'source_filter': 'x', 'date_from': 'd1', 'date_to': 'd2'})
        assert params[0] == 9                 # project_id always first
        assert ['new'] in params


class TestKpiLeadSourceRepo:

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_link_returns_id(self, mock_get_db, mock_get_cursor, mock_release):
        from unittest.mock import MagicMock
        conn, cursor = MagicMock(), MagicMock()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        cursor.fetchone.return_value = {'id': 17}

        from marketing.repositories.kpi_repo import KpiRepository
        result = KpiRepository().link_lead_source(
            3, role='input', metric='count', status_filter=['qualified'],
            source_filter='fb', date_from='2026-01-01', date_to=None)
        assert result == 17
        conn.commit.assert_called()

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_returns_list(self, mock_get_db, mock_get_cursor, mock_release):
        from unittest.mock import MagicMock
        conn, cursor = MagicMock(), MagicMock()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        cursor.fetchall.return_value = [{'id': 1, 'role': 'input'}]

        from marketing.repositories.kpi_repo import KpiRepository
        assert KpiRepository().get_kpi_lead_sources(3) == [{'id': 1, 'role': 'input'}]

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_unlink_true_when_removed(self, mock_get_db, mock_get_cursor, mock_release):
        from unittest.mock import MagicMock
        conn, cursor = MagicMock(), MagicMock()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        cursor.rowcount = 1

        from marketing.repositories.kpi_repo import KpiRepository
        assert KpiRepository().unlink_lead_source(3, 17) is True

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_unlink_false_when_absent(self, mock_get_db, mock_get_cursor, mock_release):
        from unittest.mock import MagicMock
        conn, cursor = MagicMock(), MagicMock()
        mock_get_db.return_value = conn
        mock_get_cursor.return_value = cursor
        cursor.rowcount = 0

        from marketing.repositories.kpi_repo import KpiRepository
        assert KpiRepository().unlink_lead_source(3, 999) is False
