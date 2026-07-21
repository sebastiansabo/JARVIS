"""e-Factura scheduled tasks."""
import logging

logger = logging.getLogger('jarvis.tasks.efactura')

# Auto-lifecycle thresholds (days)
UNALLOCATED_BIN_DAYS = 10   # Stage 1: unallocated this long (by import date) -> soft-delete to Bin
BIN_PURGE_DAYS = 10         # Stage 2: in Bin this long -> permanent delete


def cleanup_old_unallocated_invoices():
    """Two-stage lifecycle for unallocated e-Factura invoices.

    Stage 1: unallocated for >UNALLOCATED_BIN_DAYS (by created_at) -> soft-delete to Bin (recoverable).
    Stage 2: in Bin for >BIN_PURGE_DAYS -> permanent delete.
    """
    try:
        from core.connectors.efactura.repositories.invoice_repository import EFacturaInvoiceRepository
        repo = EFacturaInvoiceRepository()
        binned = repo.soft_delete_old_unallocated(days=UNALLOCATED_BIN_DAYS)
        purged = repo.purge_binned_old(days=BIN_PURGE_DAYS)
        if binned or purged:
            logger.info(
                f"e-Factura lifecycle: binned {binned} unallocated (>{UNALLOCATED_BIN_DAYS}d), "
                f"purged {purged} from Bin (>{BIN_PURGE_DAYS}d)"
            )
    except Exception as e:
        logger.error(f"e-Factura lifecycle task failed: {e}")
