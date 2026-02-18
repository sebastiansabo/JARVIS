"""Unit tests for InvoiceRepository.

Tests for accounting.invoices.repositories.invoice_repository:
- save (basic, with reinvoice destinations, duplicate raises ValueError)
- get_all (no filters, with filters, include_deleted)
- get_with_allocations (found, not found, with reinvoice destinations)
- delete (success, not found)
- restore (success, not found)
- get_drive_link (found, not found)
- get_drive_links (multiple, empty input, no results)
- permanently_delete (success, not found)
- bulk_soft_delete (success, empty list)
- bulk_restore (success, empty list)
- bulk_permanently_delete (success, empty list)
- cleanup_old_deleted (deletes old, nothing to delete)
- update (single field, multiple fields, no fields, not found, duplicate raises ValueError)
- check_number_exists (exists, not exists, with exclude_id)
- search (text match, numeric match, with filters, empty query)
"""
import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import pytest
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from accounting.invoices.repositories.invoice_repository import InvoiceRepository

# Patch target prefixes
_B = 'core.base_repository'  # DB functions (get_db, get_cursor, release_db, dict_from_row)
_P = 'accounting.invoices.repositories.invoice_repository'  # Module-specific (clear_invoices_cache, dict_from_row)


def _mock_db():
    """Create mock conn, cursor, and setup get_db/get_cursor returns."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    return mock_conn, mock_cursor


# ==================== save() ====================

class TestSave:
    """Tests for InvoiceRepository.save()."""

    @patch(f'{_P}.clear_invoices_cache')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_save_basic_invoice(self, mock_get_db, mock_get_cursor, mock_release, mock_clear_cache):
        """Save invoice with one allocation returns invoice ID."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        # First fetchone = invoice id, second = manager lookup, third = allocation id
        mock_cursor.fetchone.side_effect = [
            {'id': 42},   # invoice INSERT RETURNING id
            None,         # manager lookup (no match)
            {'id': 101},  # allocation INSERT RETURNING id
        ]

        repo = InvoiceRepository()
        result = repo.save(
            supplier='Test SRL',
            invoice_template='standard',
            invoice_number='INV-001',
            invoice_date='2025-12-01',
            invoice_value=1000.0,
            currency='RON',
            drive_link='https://drive.google.com/abc',
            distributions=[{
                'company': 'DWA',
                'department': 'Marketing',
                'allocation': 1.0,
                'brand': None,
                'subdepartment': None,
            }],
            value_ron=1000.0,
        )

        assert result == 42
        mock_conn.commit.assert_called_once()
        mock_release.assert_called_once_with(mock_conn)
        mock_clear_cache.assert_called_once()

    @patch(f'{_P}.clear_invoices_cache')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_save_with_reinvoice_destinations(self, mock_get_db, mock_get_cursor, mock_release, mock_clear_cache):
        """Save invoice with reinvoice destinations inserts them."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            {'id': 50},   # invoice id
            None,         # manager lookup
            {'id': 200},  # allocation id
        ]

        repo = InvoiceRepository()
        result = repo.save(
            supplier='Test SRL',
            invoice_template='standard',
            invoice_number='INV-002',
            invoice_date='2025-12-01',
            invoice_value=2000.0,
            currency='RON',
            drive_link=None,
            distributions=[{
                'company': 'DWA',
                'department': 'Service',
                'allocation': 1.0,
                'reinvoice_destinations': [
                    {'company': 'AWP', 'percentage': 30, 'department': 'Service'},
                ],
            }],
        )

        assert result == 50
        # Should have at least 3 execute calls: invoice insert, manager lookup, allocation insert, reinvoice dest insert
        assert mock_cursor.execute.call_count >= 4

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_save_duplicate_raises_value_error(self, mock_get_db, mock_get_cursor, mock_release):
        """Save with duplicate invoice number raises ValueError."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        mock_cursor.execute.side_effect = Exception('duplicate key value violates unique constraint')

        repo = InvoiceRepository()
        with pytest.raises(ValueError, match='already exists'):
            repo.save(
                supplier='Test SRL',
                invoice_template='standard',
                invoice_number='INV-DUPE',
                invoice_date='2025-12-01',
                invoice_value=500.0,
                currency='RON',
                drive_link=None,
                distributions=[],
            )

        mock_conn.rollback.assert_called_once()
        mock_release.assert_called_once_with(mock_conn)

    @patch(f'{_P}.clear_invoices_cache')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_save_with_vat_subtraction(self, mock_get_db, mock_get_cursor, mock_release, mock_clear_cache):
        """Save with subtract_vat=True uses net_value for allocation calculation."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [
            {'id': 60},   # invoice id
            None,         # manager lookup
            {'id': 300},  # allocation id
        ]

        repo = InvoiceRepository()
        result = repo.save(
            supplier='VAT Supplier',
            invoice_template='standard',
            invoice_number='INV-VAT',
            invoice_date='2025-12-01',
            invoice_value=1190.0,
            currency='RON',
            drive_link=None,
            distributions=[{
                'company': 'DWA',
                'department': 'Marketing',
                'allocation': 1.0,
            }],
            subtract_vat=True,
            vat_rate=19.0,
            net_value=1000.0,
        )

        assert result == 60
        # The allocation value should be based on net_value (1000) not invoice_value (1190)
        alloc_insert_call = mock_cursor.execute.call_args_list[2]  # Third execute call = allocation insert
        alloc_params = alloc_insert_call[0][1]
        # allocation_value is at index 6 in the params tuple
        assert alloc_params[6] == 1000.0  # net_value * 1.0 allocation * (100-0)/100


# ==================== get_all() ====================

class TestGetAll:
    """Tests for InvoiceRepository.get_all()."""

    @patch(f'{_B}.dict_from_row')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_all_no_filters(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        """Get all with defaults returns list of dicts."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        row1 = {'id': 1, 'supplier': 'A', 'invoice_number': 'INV-1'}
        row2 = {'id': 2, 'supplier': 'B', 'invoice_number': 'INV-2'}
        mock_cursor.fetchall.return_value = [row1, row2]
        mock_dict.side_effect = lambda r: dict(r)

        repo = InvoiceRepository()
        result = repo.get_all()

        assert len(result) == 2
        assert result[0]['id'] == 1
        mock_release.assert_called_once_with(mock_conn)

    @patch(f'{_B}.dict_from_row')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_all_with_company_filter(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        """Get all with company filter joins allocations table."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []
        mock_dict.side_effect = lambda r: dict(r)

        repo = InvoiceRepository()
        result = repo.get_all(company='DWA')

        assert result == []
        sql = mock_cursor.execute.call_args[0][0]
        assert 'JOIN allocations' in sql
        assert 'a.company = %s' in sql

    @patch(f'{_B}.dict_from_row')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_all_include_deleted(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        """Get all with include_deleted=True filters for deleted invoices."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []
        mock_dict.side_effect = lambda r: dict(r)

        repo = InvoiceRepository()
        repo.get_all(include_deleted=True)

        sql = mock_cursor.execute.call_args[0][0]
        assert 'deleted_at IS NOT NULL' in sql

    @patch(f'{_B}.dict_from_row')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_all_with_date_range(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        """Get all with date filters includes date conditions."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []
        mock_dict.side_effect = lambda r: dict(r)

        repo = InvoiceRepository()
        repo.get_all(start_date='2025-01-01', end_date='2025-12-31')

        sql = mock_cursor.execute.call_args[0][0]
        params = mock_cursor.execute.call_args[0][1]
        assert 'invoice_date >= %s' in sql
        assert 'invoice_date <= %s' in sql
        assert '2025-01-01' in params
        assert '2025-12-31' in params


# ==================== get_with_allocations() ====================

class TestGetWithAllocations:
    """Tests for InvoiceRepository.get_with_allocations()."""

    @patch(f'{_B}.dict_from_row')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_found_with_allocations(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        """Returns invoice dict with allocations list."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        invoice_row = {'id': 1, 'supplier': 'Test'}
        alloc_row = {'id': 10, 'invoice_id': 1, 'company': 'DWA'}

        mock_cursor.fetchone.return_value = invoice_row
        mock_cursor.fetchall.side_effect = [
            [alloc_row],  # allocations
            [],           # reinvoice destinations
        ]
        mock_dict.side_effect = lambda r: dict(r)

        repo = InvoiceRepository()
        result = repo.get_with_allocations(1)

        assert result is not None
        assert result['id'] == 1
        assert len(result['allocations']) == 1
        assert result['allocations'][0]['company'] == 'DWA'
        assert result['allocations'][0]['reinvoice_destinations'] == []
        mock_release.assert_called_once_with(mock_conn)

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_not_found(self, mock_get_db, mock_get_cursor, mock_release):
        """Returns None when invoice doesn't exist."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        repo = InvoiceRepository()
        result = repo.get_with_allocations(999)

        assert result is None
        mock_release.assert_called_once_with(mock_conn)

    @patch(f'{_B}.dict_from_row')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_with_reinvoice_destinations(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        """Allocations include their reinvoice destinations."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        invoice_row = {'id': 5, 'supplier': 'Reinvoice Test'}
        alloc_row = {'id': 20, 'invoice_id': 5, 'company': 'DWA'}
        rd_row = {'id': 1, 'allocation_id': 20, 'company': 'AWP', 'percentage': 30, 'value': 300}

        mock_cursor.fetchone.return_value = invoice_row
        mock_cursor.fetchall.side_effect = [
            [alloc_row],  # allocations
            [rd_row],     # reinvoice destinations
        ]
        mock_dict.side_effect = lambda r: dict(r)

        repo = InvoiceRepository()
        result = repo.get_with_allocations(5)

        assert len(result['allocations'][0]['reinvoice_destinations']) == 1
        assert result['allocations'][0]['reinvoice_destinations'][0]['company'] == 'AWP'


# ==================== delete() ====================

class TestDelete:
    """Tests for InvoiceRepository.delete() — soft delete."""

    @patch(f'{_P}.clear_invoices_cache')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_delete_success(self, mock_get_db, mock_get_cursor, mock_release, mock_clear_cache):
        """Soft delete returns True when invoice exists."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        repo = InvoiceRepository()
        result = repo.delete(42)

        assert result is True
        mock_conn.commit.assert_called_once()
        mock_clear_cache.assert_called_once()
        mock_release.assert_called_once_with(mock_conn)

    @patch(f'{_P}.clear_invoices_cache')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_delete_not_found(self, mock_get_db, mock_get_cursor, mock_release, mock_clear_cache):
        """Soft delete returns False when invoice doesn't exist."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 0

        repo = InvoiceRepository()
        result = repo.delete(999)

        assert result is False
        mock_clear_cache.assert_not_called()


# ==================== restore() ====================

class TestRestore:
    """Tests for InvoiceRepository.restore()."""

    @patch(f'{_P}.clear_invoices_cache')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_restore_success(self, mock_get_db, mock_get_cursor, mock_release, mock_clear_cache):
        """Restore returns True when deleted invoice exists."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        repo = InvoiceRepository()
        result = repo.restore(42)

        assert result is True
        mock_conn.commit.assert_called_once()
        mock_clear_cache.assert_called_once()

    @patch(f'{_P}.clear_invoices_cache')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_restore_not_found(self, mock_get_db, mock_get_cursor, mock_release, mock_clear_cache):
        """Restore returns False when invoice isn't in bin."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 0

        repo = InvoiceRepository()
        result = repo.restore(999)

        assert result is False
        mock_clear_cache.assert_not_called()


# ==================== get_drive_link() ====================

class TestGetDriveLink:
    """Tests for InvoiceRepository.get_drive_link()."""

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_found(self, mock_get_db, mock_get_cursor, mock_release):
        """Returns drive link when invoice exists."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {'drive_link': 'https://drive.google.com/abc'}

        repo = InvoiceRepository()
        result = repo.get_drive_link(1)

        assert result == 'https://drive.google.com/abc'
        mock_release.assert_called_once_with(mock_conn)

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_not_found(self, mock_get_db, mock_get_cursor, mock_release):
        """Returns None when invoice doesn't exist."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        repo = InvoiceRepository()
        result = repo.get_drive_link(999)

        assert result is None


# ==================== get_drive_links() ====================

class TestGetDriveLinks:
    """Tests for InvoiceRepository.get_drive_links()."""

    def test_empty_input(self):
        """Empty invoice_ids returns empty list without DB call."""
        repo = InvoiceRepository()
        result = repo.get_drive_links([])
        assert result == []

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_multiple_links(self, mock_get_db, mock_get_cursor, mock_release):
        """Returns list of non-null drive links."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {'drive_link': 'https://drive.google.com/a'},
            {'drive_link': 'https://drive.google.com/b'},
        ]

        repo = InvoiceRepository()
        result = repo.get_drive_links([1, 2, 3])

        assert len(result) == 2
        assert 'https://drive.google.com/a' in result

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_no_links_found(self, mock_get_db, mock_get_cursor, mock_release):
        """Returns empty list when no invoices have drive links."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        repo = InvoiceRepository()
        result = repo.get_drive_links([1, 2])

        assert result == []


# ==================== permanently_delete() ====================

class TestPermanentlyDelete:
    """Tests for InvoiceRepository.permanently_delete()."""

    @patch(f'{_P}.clear_invoices_cache')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_success(self, mock_get_db, mock_get_cursor, mock_release, mock_clear_cache):
        """Permanently deletes invoice and returns True."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        repo = InvoiceRepository()
        result = repo.permanently_delete(42)

        assert result is True
        sql = mock_cursor.execute.call_args[0][0]
        assert 'DELETE FROM invoices' in sql
        mock_clear_cache.assert_called_once()

    @patch(f'{_P}.clear_invoices_cache')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_not_found(self, mock_get_db, mock_get_cursor, mock_release, mock_clear_cache):
        """Returns False when invoice doesn't exist."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 0

        repo = InvoiceRepository()
        result = repo.permanently_delete(999)

        assert result is False
        mock_clear_cache.assert_not_called()


# ==================== bulk_soft_delete() ====================

class TestBulkSoftDelete:
    """Tests for InvoiceRepository.bulk_soft_delete()."""

    def test_empty_list(self):
        """Empty list returns 0 without DB call."""
        repo = InvoiceRepository()
        assert repo.bulk_soft_delete([]) == 0

    @patch(f'{_P}.clear_invoices_cache')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_deletes_multiple(self, mock_get_db, mock_get_cursor, mock_release, mock_clear_cache):
        """Soft deletes multiple invoices and returns count."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 3

        repo = InvoiceRepository()
        result = repo.bulk_soft_delete([1, 2, 3])

        assert result == 3
        mock_conn.commit.assert_called_once()
        mock_clear_cache.assert_called_once()

    @patch(f'{_P}.clear_invoices_cache')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_partial_delete(self, mock_get_db, mock_get_cursor, mock_release, mock_clear_cache):
        """Returns actual count when some IDs are already deleted."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1  # only 1 of 3 was active

        repo = InvoiceRepository()
        result = repo.bulk_soft_delete([1, 2, 3])

        assert result == 1


# ==================== bulk_restore() ====================

class TestBulkRestore:
    """Tests for InvoiceRepository.bulk_restore()."""

    def test_empty_list(self):
        """Empty list returns 0 without DB call."""
        repo = InvoiceRepository()
        assert repo.bulk_restore([]) == 0

    @patch(f'{_P}.clear_invoices_cache')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_restores_multiple(self, mock_get_db, mock_get_cursor, mock_release, mock_clear_cache):
        """Restores multiple invoices and returns count."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 2

        repo = InvoiceRepository()
        result = repo.bulk_restore([10, 20])

        assert result == 2
        mock_conn.commit.assert_called_once()
        mock_clear_cache.assert_called_once()


# ==================== bulk_permanently_delete() ====================

class TestBulkPermanentlyDelete:
    """Tests for InvoiceRepository.bulk_permanently_delete()."""

    def test_empty_list(self):
        """Empty list returns 0 without DB call."""
        repo = InvoiceRepository()
        assert repo.bulk_permanently_delete([]) == 0

    @patch(f'{_P}.clear_invoices_cache')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_deletes_multiple(self, mock_get_db, mock_get_cursor, mock_release, mock_clear_cache):
        """Permanently deletes multiple invoices and returns count."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 4

        repo = InvoiceRepository()
        result = repo.bulk_permanently_delete([1, 2, 3, 4])

        assert result == 4
        sql = mock_cursor.execute.call_args[0][0]
        assert 'DELETE FROM invoices' in sql


# ==================== cleanup_old_deleted() ====================

class TestCleanupOldDeleted:
    """Tests for InvoiceRepository.cleanup_old_deleted()."""

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_deletes_old(self, mock_get_db, mock_get_cursor, mock_release):
        """Deletes invoices older than specified days and returns count."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 5

        repo = InvoiceRepository()
        result = repo.cleanup_old_deleted(days=30)

        assert result == 5
        mock_conn.commit.assert_called_once()
        params = mock_cursor.execute.call_args[0][1]
        assert params == (30,)

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_nothing_to_delete(self, mock_get_db, mock_get_cursor, mock_release):
        """Returns 0 when no old deleted invoices exist."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 0

        repo = InvoiceRepository()
        result = repo.cleanup_old_deleted()

        assert result == 0


# ==================== update() ====================

class TestUpdate:
    """Tests for InvoiceRepository.update()."""

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_no_fields_returns_false(self, mock_get_db, mock_get_cursor, mock_release):
        """Update with no kwargs returns False without executing SQL."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        repo = InvoiceRepository()
        result = repo.update(invoice_id=1)

        assert result is False

    @patch(f'{_P}.clear_invoices_cache')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_update_single_field(self, mock_get_db, mock_get_cursor, mock_release, mock_clear_cache):
        """Update with one field builds correct SQL."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        repo = InvoiceRepository()
        result = repo.update(invoice_id=42, supplier='New Supplier')

        assert result is True
        sql = mock_cursor.execute.call_args[0][0]
        params = mock_cursor.execute.call_args[0][1]
        assert 'supplier = %s' in sql
        assert 'updated_at = CURRENT_TIMESTAMP' in sql
        assert params[0] == 'New Supplier'
        assert params[-1] == 42
        mock_clear_cache.assert_called_once()

    @patch(f'{_P}.clear_invoices_cache')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_update_multiple_fields(self, mock_get_db, mock_get_cursor, mock_release, mock_clear_cache):
        """Update with multiple fields includes all in SQL."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        repo = InvoiceRepository()
        result = repo.update(invoice_id=10, supplier='Updated', status='Bugetata', payment_status='paid')

        assert result is True
        sql = mock_cursor.execute.call_args[0][0]
        assert 'supplier = %s' in sql
        assert 'status = %s' in sql
        assert 'payment_status = %s' in sql

    @patch(f'{_P}.clear_invoices_cache')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_update_not_found(self, mock_get_db, mock_get_cursor, mock_release, mock_clear_cache):
        """Update returns False when no rows affected."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 0

        repo = InvoiceRepository()
        result = repo.update(invoice_id=999, supplier='Ghost')

        assert result is False
        mock_clear_cache.assert_not_called()

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_update_duplicate_raises_value_error(self, mock_get_db, mock_get_cursor, mock_release):
        """Update raises ValueError on duplicate key violation."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception('duplicate key value violates unique constraint')

        repo = InvoiceRepository()
        with pytest.raises(ValueError, match='already exists'):
            repo.update(invoice_id=1, invoice_number='TAKEN-001')

        mock_conn.rollback.assert_called_once()
        mock_release.assert_called_once_with(mock_conn)

    @patch(f'{_P}.clear_invoices_cache')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_update_subtract_vat_false_clears_vat_fields(self, mock_get_db, mock_get_cursor, mock_release, mock_clear_cache):
        """Setting subtract_vat=False clears vat_rate and net_value."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1

        repo = InvoiceRepository()
        repo.update(invoice_id=1, subtract_vat=False)

        sql = mock_cursor.execute.call_args[0][0]
        assert 'subtract_vat = %s' in sql
        assert 'vat_rate = %s' in sql
        assert 'net_value = %s' in sql


# ==================== check_number_exists() ====================

class TestCheckNumberExists:
    """Tests for InvoiceRepository.check_number_exists()."""

    @patch(f'{_B}.dict_from_row')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_exists(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        """Returns exists=True with invoice data when number found."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        row = {'id': 1, 'supplier': 'Test', 'invoice_number': 'INV-001'}
        mock_cursor.fetchone.return_value = row
        mock_dict.return_value = row

        repo = InvoiceRepository()
        result = repo.check_number_exists('INV-001')

        assert result['exists'] is True
        assert result['invoice']['invoice_number'] == 'INV-001'

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_not_exists(self, mock_get_db, mock_get_cursor, mock_release):
        """Returns exists=False when number not found."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        repo = InvoiceRepository()
        result = repo.check_number_exists('INV-NONE')

        assert result['exists'] is False
        assert result['invoice'] is None

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_with_exclude_id(self, mock_get_db, mock_get_cursor, mock_release):
        """Uses exclude_id in query when provided."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        repo = InvoiceRepository()
        repo.check_number_exists('INV-001', exclude_id=42)

        sql = mock_cursor.execute.call_args[0][0]
        params = mock_cursor.execute.call_args[0][1]
        assert 'id != %s' in sql
        assert params == ('INV-001', 42)


# ==================== search() ====================

class TestSearch:
    """Tests for InvoiceRepository.search()."""

    @patch(f'{_B}.dict_from_row')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_text_search(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        """Search by text returns matching invoices."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        row = {'id': 1, 'supplier': 'Meta Platforms'}
        mock_cursor.fetchall.return_value = [row]
        mock_dict.side_effect = lambda r: dict(r)

        repo = InvoiceRepository()
        result = repo.search('Meta')

        assert len(result) == 1
        assert result[0]['supplier'] == 'Meta Platforms'
        sql = mock_cursor.execute.call_args[0][0]
        assert 'ILIKE' in sql
        assert 'deleted_at IS NULL' in sql

    @patch(f'{_B}.dict_from_row')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_numeric_search(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        """Search with numeric value includes ABS comparison."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []
        mock_dict.side_effect = lambda r: dict(r)

        repo = InvoiceRepository()
        result = repo.search('1500')

        sql = mock_cursor.execute.call_args[0][0]
        assert 'ABS(i.invoice_value' in sql

    @patch(f'{_B}.dict_from_row')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_search_with_company_filter(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        """Search with company filter joins allocations."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []
        mock_dict.side_effect = lambda r: dict(r)

        repo = InvoiceRepository()
        repo.search('test', filters={'company': 'DWA'})

        sql = mock_cursor.execute.call_args[0][0]
        assert 'JOIN allocations' in sql
        assert 'a.company = %s' in sql

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_empty_query(self, mock_get_db, mock_get_cursor, mock_release):
        """Empty query returns empty list without DB call."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor

        repo = InvoiceRepository()
        result = repo.search('   ')

        assert result == []

    @patch(f'{_B}.dict_from_row')
    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_search_with_date_and_status_filters(self, mock_get_db, mock_get_cursor, mock_release, mock_dict):
        """Search with date range and status filters includes all conditions."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []
        mock_dict.side_effect = lambda r: dict(r)

        repo = InvoiceRepository()
        repo.search('test', filters={
            'start_date': '2025-01-01',
            'end_date': '2025-12-31',
            'status': 'Bugetata',
            'payment_status': 'paid',
        })

        sql = mock_cursor.execute.call_args[0][0]
        assert 'invoice_date >= %s' in sql
        assert 'invoice_date <= %s' in sql
        assert 'i.status = %s' in sql
        assert 'i.payment_status = %s' in sql


# ==================== Connection release safety ====================

class TestConnectionRelease:
    """Verify connections are released even on exceptions."""

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_get_all_releases_on_error(self, mock_get_db, mock_get_cursor, mock_release):
        """get_all releases connection even when query throws."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception('DB error')

        repo = InvoiceRepository()
        with pytest.raises(Exception):
            repo.get_all()

        mock_release.assert_called_once_with(mock_conn)

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_delete_releases_on_error(self, mock_get_db, mock_get_cursor, mock_release):
        """delete releases connection even when query throws."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception('DB error')

        repo = InvoiceRepository()
        with pytest.raises(Exception):
            repo.delete(1)

        mock_release.assert_called_once_with(mock_conn)

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_search_releases_on_error(self, mock_get_db, mock_get_cursor, mock_release):
        """search releases connection even when query throws."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception('DB error')

        repo = InvoiceRepository()
        with pytest.raises(Exception):
            repo.search('test')

        mock_release.assert_called_once_with(mock_conn)

    @patch(f'{_B}.release_db')
    @patch(f'{_B}.get_cursor')
    @patch(f'{_B}.get_db')
    def test_update_releases_on_error(self, mock_get_db, mock_get_cursor, mock_release):
        """update releases connection even on non-duplicate exceptions."""
        mock_conn, mock_cursor = _mock_db()
        mock_get_db.return_value = mock_conn
        mock_get_cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception('connection reset')

        repo = InvoiceRepository()
        with pytest.raises(Exception, match='connection reset'):
            repo.update(invoice_id=1, supplier='Test')

        mock_release.assert_called_once_with(mock_conn)
