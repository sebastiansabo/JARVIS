"""Status transition when a user saves an invoice's allocations.

Root-cause fix: allocating an invoice must move it from an unbudgeted state to the
budgeted status ('Bugetata') — never clobbering downstream states like 'processed'.
"""
from accounting.invoices.services.invoice_service import (
    BUDGETED_STATUS,
    budgeted_status_after_allocation,
)


def test_budgeted_status_is_bugetata():
    assert BUDGETED_STATUS == 'Bugetata'


def test_new_transitions_to_bugetata():
    assert budgeted_status_after_allocation('new') == 'Bugetata'


def test_nebugetata_transitions_to_bugetata():
    # e-Factura imports arrive as 'Nebugetata'; budgeting them makes them 'Bugetata'.
    assert budgeted_status_after_allocation('Nebugetata') == 'Bugetata'


def test_already_budgeted_is_unchanged():
    assert budgeted_status_after_allocation('Bugetata') is None


def test_processed_is_not_clobbered():
    # Re-editing allocations on an exported invoice must NOT send it back to Bugetata.
    assert budgeted_status_after_allocation('processed') is None


def test_other_states_unchanged():
    for status in ('approved', 'eronata', 'incomplete', None, ''):
        assert budgeted_status_after_allocation(status) is None


# ── drive the real InvoiceService.update_allocations (accounting module path) ──

from unittest.mock import MagicMock

from accounting.invoices.services.invoice_service import InvoiceService, UserContext

_ALLOCS = [{'company': 'Autoworld ONE S.R.L.', 'department': 'Info', 'allocation_percent': 100}]
_USER = UserContext(user_id=1, user_email='a@b.c', role_name='Admin')


def _service_for(status):
    svc = InvoiceService()
    svc.invoice_repo = MagicMock()
    svc.invoice_repo.get_with_allocations.return_value = {
        'status': status, 'allocation_mode': 'whole', 'invoice_number': 'INV-1',
    }
    svc.allocation_repo = MagicMock()
    svc._log_event = MagicMock()
    svc._notify_allocations = MagicMock(return_value=0)
    return svc


def test_saving_allocation_budgets_a_new_invoice():
    svc = _service_for('new')
    result = svc.update_allocations(42, _ALLOCS, send_notification=False, user=_USER)
    assert result.success
    svc.allocation_repo.update_invoice_allocations.assert_called_once_with(42, _ALLOCS)
    svc.invoice_repo.update.assert_called_once_with(42, status='Bugetata')


def test_saving_allocation_budgets_an_efactura_nebugetata_invoice():
    svc = _service_for('Nebugetata')
    svc.update_allocations(42, _ALLOCS, send_notification=False, user=_USER)
    svc.invoice_repo.update.assert_called_once_with(42, status='Bugetata')


def test_saving_allocation_does_not_reset_a_processed_invoice():
    svc = _service_for('processed')
    result = svc.update_allocations(42, _ALLOCS, send_notification=False, user=_USER)
    assert result.success
    svc.allocation_repo.update_invoice_allocations.assert_called_once_with(42, _ALLOCS)
    svc.invoice_repo.update.assert_not_called()
