"""Scheduled purge of trashed HR leave permits (Coș).

HR can move a leave to Trash on the Leave-Permits tab; it stays recoverable for
TRASH_RETENTION_DAYS, after which this daily job hard-deletes it. Scoped to leave
submissions only (see purge_trashed_leaves).
"""
from core.utils.logging_config import get_logger

logger = get_logger('jarvis.tasks')

TRASH_RETENTION_DAYS = 7


def purge_old_trashed_leaves():
    """Hard-delete leave permits trashed more than TRASH_RETENTION_DAYS ago."""
    try:
        from core.connectors.connecteam.services.leave_permit_actions import purge_trashed_leaves
        removed = purge_trashed_leaves(days=TRASH_RETENTION_DAYS)
        if removed:
            logger.info(
                f"HR leave Trash purge: removed {removed} leave(s) "
                f"trashed >{TRASH_RETENTION_DAYS}d"
            )
    except Exception as e:
        logger.error(f"HR leave Trash purge failed: {e}")
