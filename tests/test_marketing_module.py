"""Unit tests for the Marketing module.

Tests:
- OkrRepository: CRUD objectives and key results, progress computation
- BudgetRepository: CRUD budget lines
- ProjectRepository: list with filters
"""

import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

_B = 'core.base_repository'


def _mock_db():
    conn = MagicMock()
    cursor = MagicMock()
    return conn, cursor


# ═══════════════════════════════════════════════
# OkrRepository Tests
# ═══════════════════════════════════════════════

class TestOkrRepository:

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_create_objective(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'id': 10}

        from marketing.repositories.okr_repo import OkrRepository
        repo = OkrRepository()
        result = repo.create_objective(project_id=1, title='Increase Brand Awareness', created_by=5)

        assert result == 10
        mock_conn.commit.assert_called()

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_create_objective_with_description(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'id': 11}

        from marketing.repositories.okr_repo import OkrRepository
        repo = OkrRepository()
        result = repo.create_objective(
            project_id=1, title='Drive Engagement', created_by=5,
            description='Focus on social channels', sort_order=2
        )
        assert result == 11

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_update_objective(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        from marketing.repositories.okr_repo import OkrRepository
        repo = OkrRepository()
        result = repo.update_objective(10, title='Updated Title')
        assert result is True

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_update_objective_no_changes(self, mock_get_db, mock_get_cursor, mock_release):
        from marketing.repositories.okr_repo import OkrRepository
        repo = OkrRepository()
        result = repo.update_objective(10, invalid_field='nope')
        assert result is False

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_delete_objective(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        from marketing.repositories.okr_repo import OkrRepository
        repo = OkrRepository()
        assert repo.delete_objective(10) is True

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_delete_objective_not_found(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 0

        from marketing.repositories.okr_repo import OkrRepository
        repo = OkrRepository()
        assert repo.delete_objective(999) is False

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_by_project_empty(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        from marketing.repositories.okr_repo import OkrRepository
        repo = OkrRepository()
        result = repo.get_by_project(99)
        assert result == []

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_by_project_with_progress(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        # First fetchall: objectives
        # Second fetchall: key results
        mock_cursor.fetchall.side_effect = [
            [{'id': 1, 'project_id': 1, 'title': 'Obj 1', 'sort_order': 0}],
            [
                {'id': 10, 'objective_id': 1, 'title': 'KR 1', 'target_value': 100,
                 'current_value': 75, 'linked_kpi_name': None, 'sort_order': 0},
                {'id': 11, 'objective_id': 1, 'title': 'KR 2', 'target_value': 50,
                 'current_value': 50, 'linked_kpi_name': 'CPA', 'sort_order': 1},
            ]
        ]

        from marketing.repositories.okr_repo import OkrRepository
        repo = OkrRepository()
        result = repo.get_by_project(1)

        assert len(result) == 1
        obj = result[0]
        assert len(obj['key_results']) == 2
        assert obj['key_results'][0]['progress'] == 75.0
        assert obj['key_results'][1]['progress'] == 100.0
        assert obj['progress'] == 87.5  # avg(75, 100)

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_progress_zero_target(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        mock_cursor.fetchall.side_effect = [
            [{'id': 1, 'project_id': 1, 'title': 'Obj', 'sort_order': 0}],
            [{'id': 10, 'objective_id': 1, 'title': 'KR', 'target_value': 0,
              'current_value': 50, 'linked_kpi_name': None, 'sort_order': 0}]
        ]

        from marketing.repositories.okr_repo import OkrRepository
        repo = OkrRepository()
        result = repo.get_by_project(1)
        assert result[0]['key_results'][0]['progress'] == 0  # division by zero handled

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_progress_capped_at_100(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        mock_cursor.fetchall.side_effect = [
            [{'id': 1, 'project_id': 1, 'title': 'Obj', 'sort_order': 0}],
            [{'id': 10, 'objective_id': 1, 'title': 'KR', 'target_value': 50,
              'current_value': 200, 'linked_kpi_name': None, 'sort_order': 0}]
        ]

        from marketing.repositories.okr_repo import OkrRepository
        repo = OkrRepository()
        result = repo.get_by_project(1)
        assert result[0]['key_results'][0]['progress'] == 100.0  # capped

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_objective_with_no_key_results(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        mock_cursor.fetchall.side_effect = [
            [{'id': 1, 'project_id': 1, 'title': 'Obj', 'sort_order': 0}],
            []  # no KRs
        ]

        from marketing.repositories.okr_repo import OkrRepository
        repo = OkrRepository()
        result = repo.get_by_project(1)
        assert result[0]['progress'] == 0
        assert result[0]['key_results'] == []

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_create_key_result_basic(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'id': 20}

        from marketing.repositories.okr_repo import OkrRepository
        repo = OkrRepository()
        result = repo.create_key_result(objective_id=1, title='Get 100 leads', target_value=100)
        assert result == 20

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_create_key_result_linked_kpi(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        # First fetchone: KPI current value, Second: RETURNING id
        mock_cursor.fetchone.side_effect = [
            {'current_value': 42.5},  # linked KPI
            {'id': 21}               # new KR id
        ]

        from marketing.repositories.okr_repo import OkrRepository
        repo = OkrRepository()
        result = repo.create_key_result(
            objective_id=1, title='KR linked', target_value=100, linked_kpi_id=5)
        assert result == 21

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_delete_key_result(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        from marketing.repositories.okr_repo import OkrRepository
        repo = OkrRepository()
        assert repo.delete_key_result(20) is True

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_sync_linked_kpis(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 3

        from marketing.repositories.okr_repo import OkrRepository
        repo = OkrRepository()
        result = repo.sync_linked_kpis(project_id=1)
        assert result == 3


# ═══════════════════════════════════════════════
# Formula Engine Tests (marketing-specific)
# ═══════════════════════════════════════════════

class TestFormulaEngineMarketing:
    """Marketing KPI formula validation."""

    def test_cpa_formula(self):
        from marketing.services.formula_engine import evaluate
        result = evaluate('spent / leads', {'spent': 1000.0, 'leads': 50.0})
        assert result == 20.0

    def test_roas_formula(self):
        from marketing.services.formula_engine import evaluate
        result = evaluate('revenue / spent', {'spent': 500.0, 'revenue': 2500.0})
        assert result == 5.0

    def test_conversion_rate(self):
        from marketing.services.formula_engine import evaluate
        result = evaluate('conversions / clicks * 100', {'conversions': 25.0, 'clicks': 500.0})
        assert result == 5.0

    def test_division_by_zero(self):
        from marketing.services.formula_engine import evaluate
        with pytest.raises(ZeroDivisionError):
            evaluate('a / b', {'a': 100, 'b': 0})

    def test_extract_variables(self):
        from marketing.services.formula_engine import extract_variables
        result = extract_variables('spent / leads * 100')
        assert 'spent' in result
        assert 'leads' in result

    def test_validate_valid(self):
        from marketing.services.formula_engine import validate
        is_valid, error, variables = validate('a + b / c')
        assert is_valid is True
        assert error is None
        assert 'a' in variables

    def test_validate_invalid(self):
        from marketing.services.formula_engine import validate
        is_valid, error, variables = validate('import os')
        assert is_valid is False
