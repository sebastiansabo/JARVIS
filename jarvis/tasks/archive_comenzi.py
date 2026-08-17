"""Background task: delayed auto-archive of completed Comenzi anexas/contracts.

Every run (default 15 min): arm `archive_after` on newly fully-invoiced anexas
and fully-complete contracts, clear it on re-opened ones, and archive whatever
has passed its deadline (contract archive cascades to anexas + invoices).
Reads archive_enabled / archive_delay_hours; skips entirely when disabled.
"""
from core.utils.logging_config import get_logger
from accounting.facturare.repositories.invoice_storage_repository import InvoiceStorageRepository
from accounting.facturare.services.completion import is_anexa_complete, is_contract_complete

logger = get_logger('jarvis.tasks.archive_comenzi')


def _archive_settings():
    """(enabled, delay_hours) from notification settings; safe fallback (True, 24)."""
    try:
        from core.notifications.repositories import NotificationRepository
        s = NotificationRepository().get_settings()
        return (s.get('archive_enabled', 'true') == 'true',
                int(s.get('archive_delay_hours', '24')))
    except Exception:
        return (True, 24)


def archive_pending_comenzi():
    try:
        enabled, delay = _archive_settings()
        if not enabled:
            return
        repo = InvoiceStorageRepository()
        armed = cancelled = archived = 0

        for a in repo.list_active_anexas():
            try:
                complete = is_anexa_complete(repo, a['id'])
                if complete and a.get('archive_after') is None:
                    armed += repo.set_anexa_archive_after(a['id'], delay)
                elif not complete and a.get('archive_after') is not None:
                    cancelled += repo.clear_anexa_archive_after(a['id'])
            except Exception as e:
                logger.error('Anexa %s archive-eval failed: %s', a.get('id'), e, exc_info=True)

        for c in repo.list_active_contracts():
            try:
                complete = is_contract_complete(repo, c['id'])
                if complete and c.get('archive_after') is None:
                    armed += repo.set_contract_archive_after(c['id'], delay)
                elif not complete and c.get('archive_after') is not None:
                    cancelled += repo.clear_contract_archive_after(c['id'])
            except Exception as e:
                logger.error('Contract %s archive-eval failed: %s', c.get('id'), e, exc_info=True)

        archived += repo.archive_due_anexas()
        archived += repo.archive_due_contracts()

        if armed or cancelled or archived:
            try:
                from accounting.facturare.routes_orders import _invalidate_doc_items_cache
                _invalidate_doc_items_cache()
            except Exception:
                pass
            logger.info('Comenzi archive sweep: armed=%d cancelled=%d archived=%d',
                        armed, cancelled, archived)
    except Exception as e:
        logger.error('Comenzi archive sweep failed: %s', e, exc_info=True)
