"""invoice entity handlers."""
import logging

logger = logging.getLogger('jarvis.core.approvals.handlers.entity_invoice')


def handle_approved(entity_id):
    try:
        from accounting.invoices.repositories.invoice_repository import InvoiceRepository
        InvoiceRepository().update(entity_id, status='approved')
        logger.info(f'Invoice #{entity_id} status set to approved via approval hook')
    except Exception as e:
        logger.error(f'Failed to update invoice status on approval: {e}')
