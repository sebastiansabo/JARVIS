"""Tests for e-Factura scheduled lifecycle task."""
import sys
import os
from unittest.mock import patch, MagicMock

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))


def test_lifecycle_runs_both_stages():
    from tasks import efactura

    mock_repo = MagicMock()
    mock_repo.soft_delete_old_unallocated.return_value = 5
    mock_repo.purge_binned_old.return_value = 2

    with patch(
        'core.connectors.efactura.repositories.invoice_repository.EFacturaInvoiceRepository',
        return_value=mock_repo,
    ):
        efactura.cleanup_old_unallocated_invoices()

    mock_repo.soft_delete_old_unallocated.assert_called_once_with(days=efactura.UNALLOCATED_BIN_DAYS)
    mock_repo.purge_binned_old.assert_called_once_with(days=efactura.BIN_PURGE_DAYS)


def test_lifecycle_thresholds_are_ten():
    from tasks import efactura
    assert efactura.UNALLOCATED_BIN_DAYS == 10
    assert efactura.BIN_PURGE_DAYS == 10
