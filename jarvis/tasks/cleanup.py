"""
Task scheduler — registers all background jobs.

Uses APScheduler BackgroundScheduler to run periodic maintenance jobs.
Only one worker starts the scheduler (file-lock guard) to avoid
duplicate execution and wasted DB connections.
"""

import os
import atexit
import fcntl
from apscheduler.schedulers.background import BackgroundScheduler
from core.utils.logging_config import get_logger

from tasks.efactura import cleanup_old_unallocated_invoices
from tasks.ai_tasks import reindex_rag_documents, extract_ai_knowledge, run_daily_digest
from tasks.approvals import process_approval_tasks
from tasks.notifications import cleanup_old_notifications, run_smart_notifications, cleanup_push_rate_limit_log
from tasks.marketing import sync_marketing_kpis
from tasks.field_sales import field_sales_follow_up_reminders, field_sales_overdue_visit_alerts
from tasks.biostar import sync_biostar_events, sync_biostar_users, auto_adjust_biostar_schedules
from tasks.sincron import sync_sincron_timesheets
from tasks.hr_attendance import check_missing_punches
from tasks.carpark import cleanup_vin_cache
from tasks.holidays import populate_holidays
from tasks.telemetry import close_stale_sessions, cleanup_old_telemetry

logger = get_logger('jarvis.tasks')

scheduler = BackgroundScheduler(daemon=True)
_lock_file = None
_scheduler_deferred = False  # True when another worker holds the lock


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

    global _scheduler_deferred
    if not _acquire_scheduler_lock():
        _scheduler_deferred = True
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
        'interval',
        hours=4,
        id='rag_reindex_periodic',
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )

    scheduler.add_job(
        extract_ai_knowledge,
        'interval',
        hours=6,
        id='extract_ai_knowledge',
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
        cleanup_push_rate_limit_log,
        'cron',
        hour=2,
        minute=0,
        id='cleanup_push_rate_limit_log',
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

    # Field Sales — follow-up reminders (08:00 daily)
    scheduler.add_job(
        field_sales_follow_up_reminders,
        'cron',
        hour=8,
        minute=0,
        id='field_sales_follow_up_reminders',
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )

    # Field Sales — overdue visit alerts (18:00 daily)
    scheduler.add_job(
        field_sales_overdue_visit_alerts,
        'cron',
        hour=18,
        minute=0,
        id='field_sales_overdue_visit_alerts',
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )

    # BioStar jobs — read schedule from connector config if available
    _biostar_defaults = {
        'biostar_sync_events': {'func': sync_biostar_events, 'hour': 1, 'minute': 0},
        'biostar_sync_users': {'func': sync_biostar_users, 'hour': 2, 'minute': 0},
        'biostar_auto_adjust': {'func': auto_adjust_biostar_schedules, 'hour': 3, 'minute': 0},
    }
    _biostar_cron = {}
    try:
        import json as _json
        from core.connectors.repositories.connector_repository import ConnectorRepository
        connector = ConnectorRepository().get_by_type('biostar')
        if connector:
            cfg = connector.get('config') or {}
            if isinstance(cfg, str):
                cfg = _json.loads(cfg)
            _biostar_cron = cfg.get('cron_jobs', {})
    except Exception:
        pass

    for job_id, defaults in _biostar_defaults.items():
        settings = _biostar_cron.get(job_id, {})
        if not settings.get('enabled', True):
            logger.info(f"Skipping disabled cron job: {job_id}")
            continue
        if settings.get('schedule_type') == 'interval':
            scheduler.add_job(
                defaults['func'],
                'interval',
                minutes=settings.get('interval_minutes', 60),
                id=job_id,
                replace_existing=True,
                misfire_grace_time=300,
                coalesce=True,
            )
        else:
            scheduler.add_job(
                defaults['func'],
                'cron',
                hour=settings.get('hour', defaults['hour']),
                minute=settings.get('minute', defaults['minute']),
                id=job_id,
                replace_existing=True,
                misfire_grace_time=300,
                coalesce=True,
            )

    # Sincron — daily timesheet sync (04:00 UTC / 07:00 Romania)
    _sincron_cron = {}
    try:
        import json as _json2
        from core.connectors.repositories.connector_repository import ConnectorRepository as _CR2
        _sc = _CR2().get_by_type('sincron')
        if _sc:
            _scfg = _sc.get('config') or {}
            if isinstance(_scfg, str):
                _scfg = _json2.loads(_scfg)
            _sincron_cron = _scfg.get('cron_jobs', {})
    except Exception:
        pass

    _sincron_settings = _sincron_cron.get('sincron_sync_timesheets', {})
    if _sincron_settings.get('enabled', True):
        if _sincron_settings.get('schedule_type') == 'interval':
            scheduler.add_job(
                sync_sincron_timesheets,
                'interval',
                minutes=_sincron_settings.get('interval_minutes', 60),
                id='sincron_sync_timesheets',
                replace_existing=True,
                misfire_grace_time=300,
                coalesce=True,
            )
        else:
            scheduler.add_job(
                sync_sincron_timesheets,
                'cron',
                hour=_sincron_settings.get('hour', 4),
                minute=_sincron_settings.get('minute', 0),
                id='sincron_sync_timesheets',
                replace_existing=True,
                misfire_grace_time=300,
                coalesce=True,
            )

    # HR — missing punch check (10:00 daily, after BioStar sync completes)
    scheduler.add_job(
        check_missing_punches,
        'cron',
        hour=10,
        minute=0,
        id='hr_missing_punch_check',
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )

    # Holidays — auto-populate next year holidays (00:30 daily, idempotent)
    scheduler.add_job(
        populate_holidays,
        'cron',
        hour=0,
        minute=30,
        id='populate_holidays',
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )

    # CarPark — VIN cache cleanup (03:30 daily)
    scheduler.add_job(
        cleanup_vin_cache,
        'cron',
        hour=3,
        minute=30,
        id='carpark_vin_cache_cleanup',
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )

    # Telemetry — close stale sessions (every 2 minutes)
    scheduler.add_job(
        close_stale_sessions,
        'interval',
        minutes=2,
        id='telemetry_close_stale_sessions',
        replace_existing=True,
        misfire_grace_time=60,
        coalesce=True,
    )

    # Telemetry — cleanup old data (03:00 daily)
    scheduler.add_job(
        cleanup_old_telemetry,
        'cron',
        hour=3,
        minute=0,
        id='telemetry_cleanup_old_data',
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )

    scheduler.start()
    atexit.register(lambda: scheduler.shutdown(wait=False))
    logger.info(f"Background scheduler started (pid={os.getpid()})")


def is_scheduler_ok():
    """Check if the scheduler is healthy across all workers.

    Returns True if this worker runs the scheduler OR another worker holds the lock.
    Returns False only if start_scheduler() was never called or genuinely failed.
    """
    if scheduler.running:
        return True
    if _scheduler_deferred:
        return True  # another worker has it — that's fine
    return False


def stop_scheduler():
    """Stop the background scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped")
