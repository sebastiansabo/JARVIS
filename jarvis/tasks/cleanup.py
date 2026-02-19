"""
Scheduled cleanup tasks for JARVIS.

Uses APScheduler BackgroundScheduler to run periodic maintenance jobs.
Only one worker starts the scheduler (file-lock guard) to avoid
duplicate execution and wasted DB connections.
"""

import os
import atexit
import fcntl
from apscheduler.schedulers.background import BackgroundScheduler
from core.utils.logging_config import get_logger

logger = get_logger('jarvis.tasks.cleanup')

scheduler = BackgroundScheduler(daemon=True)
_lock_file = None


def cleanup_old_unallocated_invoices():
    """Permanently delete unallocated e-Factura invoices older than 15 days."""
    try:
        from core.connectors.efactura.repositories.invoice_repo import EFacturaInvoiceRepository
        repo = EFacturaInvoiceRepository()
        count = repo.delete_old_unallocated(days=15)
        if count > 0:
            logger.info(f"Cleanup: deleted {count} old unallocated e-Factura invoices (>15 days)")
    except Exception as e:
        logger.error(f"Cleanup task failed: {e}")


def reindex_rag_documents():
    """Reindex all RAG document sources for the AI agent."""
    try:
        from ai_agent.services.rag_service import RAGService
        svc = RAGService()
        result = svc.index_all_sources()
        total = result.data.get('total', 0) if result.success else 0
        logger.info(f"RAG reindex complete: {total} documents indexed")
    except Exception as e:
        logger.error(f"RAG reindex task failed: {e}")


def process_approval_tasks():
    """Run approval engine scheduled tasks: timeouts, reminders, expirations, delegation cleanup."""
    try:
        from core.approvals.engine import ApprovalEngine
        from core.approvals.repositories import DelegationRepository
        engine = ApprovalEngine()
        engine.process_timeouts()
        engine.process_reminders()
        engine.process_expirations()
        DelegationRepository().deactivate_expired()
        logger.debug("Approval engine scheduled tasks completed")
    except Exception as e:
        logger.error(f"Approval engine scheduled tasks failed: {e}")


def cleanup_old_notifications():
    """Delete in-app notifications older than 30 days."""
    try:
        from core.notifications.repositories.in_app_repo import InAppNotificationRepository
        repo = InAppNotificationRepository()
        count = repo.delete_old(days=30)
        if count > 0:
            logger.info(f"Cleanup: deleted {count} old notifications (>30 days)")
    except Exception as e:
        logger.error(f"Notification cleanup task failed: {e}")


def run_smart_notifications():
    """Run smart notification checks (KPI thresholds, budget utilization, invoice anomalies, e-Factura backlog)."""
    try:
        from core.notifications.smart_service import SmartNotificationService
        svc = SmartNotificationService()
        svc.run_all_checks()
    except Exception as e:
        logger.error(f"Smart notification task failed: {e}")


def sync_marketing_kpis():
    """Sync all marketing KPIs that have linked budget lines or dependencies."""
    try:
        from marketing.repositories import KpiRepository
        repo = KpiRepository()
        kpi_ids = repo.get_all_syncable_kpi_ids()
        synced = 0
        for kpi_id in kpi_ids:
            try:
                result = repo.sync_kpi(kpi_id)
                if result.get('synced'):
                    synced += 1
            except Exception as e:
                logger.warning(f"Failed to sync KPI {kpi_id}: {e}")
        if synced > 0:
            logger.info(f"Marketing KPI sync: {synced}/{len(kpi_ids)} KPIs updated")
    except Exception as e:
        logger.error(f"Marketing KPI sync task failed: {e}")


def run_daily_digest():
    """Generate and send daily AI-powered digest to admins/managers."""
    try:
        from ai_agent.services.digest_service import generate_and_send
        result = generate_and_send()
        if result.get('skipped'):
            logger.debug(f"Daily digest skipped: {result['skipped']}")
        elif result.get('sent_to'):
            logger.info(f"Daily digest sent to {result['sent_to']} users")
    except Exception as e:
        logger.error(f"Daily digest task failed: {e}")


def _acquire_scheduler_lock():
    """Try to acquire an exclusive file lock. Returns True if this process won."""
    global _lock_file
    try:
        lock_path = os.path.join(os.path.dirname(__file__), '..', '.scheduler.lock')
        _lock_file = open(lock_path, 'w')
        fcntl.flock(_lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_file.write(str(os.getpid()))
        _lock_file.flush()
        return True
    except (IOError, OSError):
        if _lock_file:
            _lock_file.close()
            _lock_file = None
        return False


def start_scheduler():
    """Start the background scheduler with all cleanup jobs.

    Uses a file lock so only one gunicorn worker runs the scheduler.
    Other workers skip silently.
    """
    if scheduler.running:
        return

    if not _acquire_scheduler_lock():
        logger.debug(f"Scheduler lock held by another worker, skipping (pid={os.getpid()})")
        return

    scheduler.add_job(
        cleanup_old_unallocated_invoices,
        'interval',
        hours=6,
        id='cleanup_old_unallocated',
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )

    scheduler.add_job(
        reindex_rag_documents,
        'cron',
        hour=0,
        minute=0,
        id='rag_reindex_daily',
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )

    scheduler.add_job(
        process_approval_tasks,
        'interval',
        hours=1,
        id='approval_engine_tasks',
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )

    scheduler.add_job(
        cleanup_old_notifications,
        'cron',
        hour=1,
        minute=0,
        id='cleanup_old_notifications',
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )

    scheduler.add_job(
        run_smart_notifications,
        'interval',
        hours=4,
        id='smart_notifications',
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )

    scheduler.add_job(
        sync_marketing_kpis,
        'cron',
        hour=6,
        minute=0,
        id='sync_marketing_kpis',
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )

    scheduler.add_job(
        run_daily_digest,
        'cron',
        hour=8,
        minute=0,
        id='daily_digest',
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )

    scheduler.start()
    atexit.register(lambda: scheduler.shutdown(wait=False))
    logger.info(f"Background scheduler started (pid={os.getpid()})")


def stop_scheduler():
    """Stop the background scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped")
