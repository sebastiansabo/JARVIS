"""Background task: auto-archive invoices whose archive_after has passed."""

from core.utils.logging_config import get_logger

logger = get_logger('jarvis.tasks.archive')


def archive_pending_invoices():
    """Archive invoices that have passed their archive_after deadline.

    Reads archive_enabled setting; skips if disabled.
    Called periodically by APScheduler (default every 15 minutes).
    """
    try:
        from core.notifications.repositories import NotificationRepository
        settings = NotificationRepository().get_settings()
        if settings.get('archive_enabled', 'true') != 'true':
            return

        from accounting.invoices.repositories.invoice_repository import (
            InvoiceRepository, clear_invoices_cache,
        )
        repo = InvoiceRepository()
        count = repo.archive_pending_invoices()
        if count:
            clear_invoices_cache()
            logger.info(f'Auto-archived {count} invoice(s)')
    except Exception as e:
        logger.error(f'Archive job failed: {e}', exc_info=True)
