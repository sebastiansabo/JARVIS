"""Unit tests for AllocationRepository.

Tests for accounting.invoices.repositories.allocation_repository:
- get_by_company (with results, empty)
- get_by_department (with results, empty)
- update (single field, multiple fields, no fields, not found)
- delete (success, not found)
- update_comment (success, not found)
- add (basic, with responsible user lookup, user not found)
- update_invoice_allocations (success, invoice not found, with reinvoice destinations)
- get_reinvoice_destinations (with results, empty)
- save_reinvoice_destinations (success, with allocation_value calc)
- save_reinvoice_destinations_batch (success, rollback on error)
"""
import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from accounting.invoices.repositories.allocation_repository import AllocationRepository

_P = 'core.base_repository'


def _mock_db():
    return MagicMock(), MagicMock()


# ==================== get_by_company() ====================

class TestGetByCompany:

    @patch(f'{_P}.dict_from_row')
    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_with_results(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        row = {'id': 1, 'company': 'DWA', 'supplier': 'Test'}
        mock_cursor.fetchall.return_value = [row]
        mock_dict.side_effect = lambda r: dict(r)

        repo = AllocationRepository()
        result = repo.get_by_company('DWA')

        assert len(result) == 1
        assert result[0]['company'] == 'DWA'
        mock_release.assert_called_once_with(mock_conn)

    @patch(f'{_P}.dict_from_row')
    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_empty(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        repo = AllocationRepository()
        result = repo.get_by_company('NONEXISTENT')

        assert result == []


# ==================== get_by_department() ====================

class TestGetByDepartment:

    @patch(f'{_P}.dict_from_row')
    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_with_results(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        row = {'id': 1, 'company': 'DWA', 'department': 'Marketing'}
        mock_cursor.fetchall.return_value = [row]
        mock_dict.side_effect = lambda r: dict(r)

        repo = AllocationRepository()
        result = repo.get_by_department('DWA', 'Marketing')

        assert len(result) == 1
        params = mock_cursor.execute.call_args[0][1]
        assert params == ('DWA', 'Marketing')

    @patch(f'{_P}.dict_from_row')
    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_empty(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        repo = AllocationRepository()
        result = repo.get_by_department('DWA', 'Unknown')

        assert result == []


# ==================== update() ====================

class TestUpdate:

    def test_no_fields_returns_false(self):
        repo = AllocationRepository()
        result = repo.update(allocation_id=1)

        assert result is False

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_single_field(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        repo = AllocationRepository()
        result = repo.update(allocation_id=10, company='AWP')

        assert result is True
        sql = mock_cursor.execute.call_args[0][0]
        assert 'company = %s' in sql
        mock_conn.commit.assert_called_once()

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_multiple_fields(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        repo = AllocationRepository()
        result = repo.update(allocation_id=10, company='AWP', department='Service', allocation_percent=50.0)

        assert result is True
        sql = mock_cursor.execute.call_args[0][0]
        assert 'company = %s' in sql
        assert 'department = %s' in sql
        assert 'allocation_percent = %s' in sql

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_not_found(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 0

        repo = AllocationRepository()
        result = repo.update(allocation_id=999, company='DWA')

        assert result is False


# ==================== delete() ====================

class TestDelete:

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_success(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        repo = AllocationRepository()
        result = repo.delete(42)

        assert result is True
        sql = mock_cursor.execute.call_args[0][0]
        assert 'DELETE FROM allocations' in sql
        mock_conn.commit.assert_called_once()

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_not_found(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 0

        repo = AllocationRepository()
        result = repo.delete(999)

        assert result is False


# ==================== update_comment() ====================

class TestUpdateComment:

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_success(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        repo = AllocationRepository()
        result = repo.update_comment(10, 'New comment')

        assert result is True
        params = mock_cursor.execute.call_args[0][1]
        assert params == ('New comment', 10)

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_not_found(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 0

        repo = AllocationRepository()
        result = repo.update_comment(999, 'comment')

        assert result is False


# ==================== add() ====================

class TestAdd:

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_basic_add(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'id': 100}

        repo = AllocationRepository()
        result = repo.add(
            invoice_id=1, company='DWA', department='Marketing',
            allocation_percent=100.0, allocation_value=1000.0,
        )

        assert result == 100
        mock_conn.commit.assert_called_once()
        mock_release.assert_called_once_with(mock_conn)

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_with_responsible_user_found(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        # First fetchone = user lookup, second = allocation id
        mock_cursor.fetchone.side_effect = [
            {'id': 5},    # user found
            {'id': 200},  # allocation id
        ]

        repo = AllocationRepository()
        result = repo.add(
            invoice_id=1, company='DWA', department='Marketing',
            allocation_percent=100.0, allocation_value=1000.0,
            responsible='John Doe',
        )

        assert result == 200
        # Should have 2 execute calls: user lookup + insert
        assert mock_cursor.execute.call_count == 2

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_with_responsible_user_not_found(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        # First fetchone = user lookup (None), second = allocation id
        mock_cursor.fetchone.side_effect = [
            None,         # user not found
            {'id': 300},  # allocation id
        ]

        repo = AllocationRepository()
        result = repo.add(
            invoice_id=1, company='DWA', department='Marketing',
            allocation_percent=100.0, allocation_value=1000.0,
            responsible='Unknown Person',
        )

        assert result == 300

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_add_rollback_on_error(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception('DB error')

        repo = AllocationRepository()
        with pytest.raises(Exception, match='DB error'):
            repo.add(
                invoice_id=1, company='DWA', department='Marketing',
                allocation_percent=100.0, allocation_value=1000.0,
            )

        mock_conn.rollback.assert_called_once()
        mock_release.assert_called_once_with(mock_conn)


# ==================== update_invoice_allocations() ====================

class TestUpdateInvoiceAllocations:

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_invoice_not_found(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        repo = AllocationRepository()
        with pytest.raises(ValueError, match='not found'):
            repo.update_invoice_allocations(999, [])

        mock_conn.rollback.assert_called_once()
        mock_release.assert_called_once_with(mock_conn)

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_success_basic(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        # fetchone calls: invoice lookup, allocation id
        mock_cursor.fetchone.side_effect = [
            {'invoice_value': 1000.0, 'subtract_vat': False, 'net_value': None},  # invoice
            {'id': 50},  # allocation id
        ]

        repo = AllocationRepository()
        result = repo.update_invoice_allocations(1, [{
            'company': 'DWA',
            'department': 'Marketing',
            'allocation_percent': 100.0,
        }])

        assert result is True
        mock_conn.commit.assert_called_once()

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_with_reinvoice_destinations(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            {'invoice_value': 2000.0, 'subtract_vat': False, 'net_value': None},  # invoice
            {'id': 60},  # allocation id
        ]

        repo = AllocationRepository()
        result = repo.update_invoice_allocations(1, [{
            'company': 'DWA',
            'department': 'Service',
            'allocation_percent': 100.0,
            'reinvoice_destinations': [
                {'company': 'AWP', 'percentage': 30, 'department': 'Service'},
            ],
        }])

        assert result is True
        # Should have: invoice lookup, delete old allocs, allocation insert, reinvoice insert = at least 4 executes
        assert mock_cursor.execute.call_count >= 4


# ==================== get_reinvoice_destinations() ====================

class TestGetReinvoiceDestinations:

    @patch(f'{_P}.dict_from_row')
    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_with_results(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        row = {'id': 1, 'allocation_id': 10, 'company': 'AWP', 'percentage': 30}
        mock_cursor.fetchall.return_value = [row]
        mock_dict.side_effect = lambda r: dict(r)

        repo = AllocationRepository()
        result = repo.get_reinvoice_destinations(10)

        assert len(result) == 1
        assert result[0]['company'] == 'AWP'

    @patch(f'{_P}.dict_from_row')
    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_empty(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        repo = AllocationRepository()
        result = repo.get_reinvoice_destinations(999)

        assert result == []


# ==================== save_reinvoice_destinations() ====================

class TestSaveReinvoiceDestinations:

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_success(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        repo = AllocationRepository()
        result = repo.save_reinvoice_destinations(10, [
            {'company': 'AWP', 'percentage': 30, 'value': 300},
        ])

        assert result is True
        mock_conn.commit.assert_called_once()
        # Should have: delete old + insert new = 2 executes
        assert mock_cursor.execute.call_count == 2

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_with_allocation_value_calc(self, mock_get_db, mock_get_cursor, mock_release):
        """When allocation_value is provided, calculates dest value from percentage."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        repo = AllocationRepository()
        repo.save_reinvoice_destinations(10, [
            {'company': 'AWP', 'percentage': 25},
        ], allocation_value=1000.0)

        # The insert call should have value = 1000 * 25/100 = 250
        insert_call = mock_cursor.execute.call_args_list[1]  # second call is insert
        insert_params = insert_call[0][1]
        assert insert_params[-1] == 250.0  # value is last param

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_rollback_on_error(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        # Delete succeeds, insert fails
        mock_cursor.execute.side_effect = [None, Exception('constraint violation')]

        repo = AllocationRepository()
        with pytest.raises(Exception):
            repo.save_reinvoice_destinations(10, [
                {'company': 'AWP', 'percentage': 30},
            ])

        mock_conn.rollback.assert_called_once()
        mock_release.assert_called_once_with(mock_conn)


# ==================== save_reinvoice_destinations_batch() ====================

class TestSaveReinvoiceDestinationsBatch:

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_success(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        batch = [
            (10, [{'company': 'AWP', 'percentage': 30}], 1000.0),
            (20, [{'company': 'DWA', 'percentage': 50}], 2000.0),
        ]

        repo = AllocationRepository()
        result = repo.save_reinvoice_destinations_batch(batch)

        assert result is True
        mock_conn.commit.assert_called_once()
        # 2 deletes + 2 inserts = 4 execute calls
        assert mock_cursor.execute.call_count == 4

    @patch(f'{_P}.release_db')
    @patch(f'{_P}.get_cursor')
    @patch(f'{_P}.get_db')
    def test_rollback_on_error(self, mock_get_db, mock_get_cursor, mock_release):
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception('DB error')

        repo = AllocationRepository()
        with pytest.raises(Exception):
            repo.save_reinvoice_destinations_batch([
                (10, [{'company': 'AWP', 'percentage': 30}], 1000.0),
            ])

        mock_conn.rollback.assert_called_once()
        mock_release.assert_called_once_with(mock_conn)
