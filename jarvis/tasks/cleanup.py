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

from tasks.archive_invoices import archive_pending_invoices as archive_invoices_task
from tasks.archive_comenzi import archive_pending_comenzi
from tasks.efactura import cleanup_old_unallocated_invoices
from tasks.ai_tasks import reindex_rag_documents, extract_ai_knowledge, run_daily_digest
from tasks.approvals import process_approval_tasks
from tasks.notifications import cleanup_old_notifications, run_smart_notifications, cleanup_push_rate_limit_log
from tasks.marketing import sync_marketing_kpis, auto_archive_completed_projects
from tasks.field_sales import field_sales_follow_up_reminders, field_sales_overdue_visit_alerts
from tasks.biostar import sync_biostar_events, sync_biostar_users, auto_adjust_biostar_schedules
from tasks.sincron import sync_sincron_timesheets
from tasks.verification import run_end_of_month_verification
from tasks.hr_attendance import check_missing_punches, send_pontaje_digest, send_monthly_pontaje_summary, send_hr_weekly_digest
from tasks.hr_courses import check_course_cert_expiry
from tasks.foi_parcurs_expiry import check_vehicle_document_expiry
from tasks.bnr_monitor import check_bnr_feed
from tasks.foi_parcurs_blocks import check_scheduled_blocks
from tasks.carpark import cleanup_vin_cache, expire_reservations, carpark_aging_alerts
from tasks.holidays import populate_holidays
from tasks.telemetry import close_stale_sessions, cleanup_old_telemetry
from tasks.foi_parcurs_sessions import run_session_lifecycle
from tasks.hr_leave_trash import purge_old_trashed_leaves
from tasks.driving_digest import run_weekly_driving_digest
from happy.jobs import purge_happy_events, refresh_happy_targets, process_escalations as happy_process_escalations, grant_monthly_giveable as happy_grant_monthly_giveable, rollup_campaign_stats as happy_rollup_campaign_stats

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
        archive_invoices_task,
        'interval',
        minutes=15,
        id='archive_invoices',
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )

    scheduler.add_job(
        archive_pending_comenzi,
        'interval',
        minutes=15,
        id='archive_comenzi',
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

    # HR leave permits — purge Coș/Trash older than 7 days (03:15 daily)
    scheduler.add_job(
        purge_old_trashed_leaves,
        'cron',
        hour=3,
        minute=15,
        id='purge_old_trashed_leaves',
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
        auto_archive_completed_projects,
        'interval',
        hours=1,
        id='auto_archive_completed_projects',
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
        'biostar_auto_adjust': {'func': auto_adjust_biostar_schedules, 'hour': 7, 'minute': 15},
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

    # Sincron — weekly timesheet sync (Mon 04:00 UTC / 07:00 Romania)
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
                day_of_week=_sincron_settings.get('day_of_week', 'mon'),
                hour=_sincron_settings.get('hour', 4),
                minute=_sincron_settings.get('minute', 0),
                id='sincron_sync_timesheets',
                replace_existing=True,
                misfire_grace_time=300,
                coalesce=True,
            )

    # HR Courses — certification expiry check (08:00 daily)
    scheduler.add_job(
        check_course_cert_expiry,
        'cron',
        hour=8,
        minute=30,
        id='hr_course_cert_expiry',
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )

    # Foi de Parcurs — vehicle document (Rovinietă/RCA/ITP) expiry check (08:45 daily)
    scheduler.add_job(
        check_vehicle_document_expiry,
        'cron',
        hour=8,
        minute=45,
        id='fp_vehicle_document_expiry',
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )

    # Facturare — BNR FX-feed health check (14:15 daily, after BNR ~13:00 publish)
    scheduler.add_job(
        check_bnr_feed,
        'cron',
        hour=14,
        minute=15,
        id='bnr_feed_monitor',
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )

    # Foi de Parcurs — scheduled-block start/end notifications (08:50 daily)
    scheduler.add_job(
        check_scheduled_blocks,
        'cron',
        hour=8,
        minute=50,
        id='fp_scheduled_block_boundaries',
        replace_existing=True,
        misfire_grace_time=3600,
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

    # HR — pontaje daily digest (10:30 Romania time = 07:30 UTC summer)
    scheduler.add_job(
        send_pontaje_digest,
        'cron',
        hour=7,
        minute=30,
        id='hr_pontaje_digest',
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )

    # HR — monthly pontaje summary (1st of each month at 08:00 UTC = 11:00 Romania summer)
    scheduler.add_job(
        send_monthly_pontaje_summary,
        'cron',
        day=1,
        hour=8,
        minute=0,
        id='hr_pontaje_monthly_summary',
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )

    # HR — weekly HR digest (Monday 07:00 UTC = 10:00 Romania summer)
    scheduler.add_job(
        send_hr_weekly_digest,
        'cron',
        day_of_week='mon',
        hour=7,
        minute=0,
        id='hr_weekly_digest',
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )

    # Foi de Parcurs — weekly driving digest (Monday 05:00 UTC = 08:00 Romania summer)
    scheduler.add_job(
        run_weekly_driving_digest,
        'cron',
        day_of_week='mon',
        hour=5,
        minute=0,
        id='weekly_driving_digest',
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

    # CarPark Dispo — expire reservations past their reservation_end (hourly)
    scheduler.add_job(
        expire_reservations,
        'interval',
        hours=1,
        id='carpark_expire_reservations',
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )

    # CarPark Dispo — aging-stock alerts, unsold > 60 days (08:00 daily)
    scheduler.add_job(
        carpark_aging_alerts,
        'cron',
        hour=8,
        minute=0,
        id='carpark_aging_alerts',
        replace_existing=True,
        misfire_grace_time=3600,
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

    # Foi de Parcurs — TD session lifecycle: notify missed-at-start + archive past-grace (every 10 minutes)
    scheduler.add_job(
        run_session_lifecycle,
        'interval',
        minutes=10,
        id='foi_parcurs_sessions',
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )

    # End-of-month verification — runs at 20:30 on the last day of each month
    scheduler.add_job(
        run_end_of_month_verification,
        'cron',
        day='last',
        hour=20,
        minute=30,
        id='end_of_month_verification',
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )

    # ── Voucher jobs ──────────────────────────────────

    def _archive_redeemed_vouchers():
        """Every 30 min: move redeemed vouchers to archived after 2 hours."""
        try:
            from accounting.vouchers.repositories import VoucherRepository
            count = VoucherRepository().archive_redeemed()
            if count:
                logger.info('Archived %d redeemed voucher(s)', count)
        except Exception:
            logger.exception('Failed to run voucher archive job')

    def _expire_vouchers():
        """Daily: expire active vouchers past their expiry date."""
        try:
            from accounting.vouchers.repositories import VoucherRepository
            count = VoucherRepository().expire_active()
            if count:
                logger.info('Expired %d voucher(s)', count)
        except Exception:
            logger.exception('Failed to run voucher expiry job')

    def _voucher_expiry_warnings():
        """Daily: send 7-day expiry warnings to voucher issuers."""
        try:
            from datetime import date as _date, timedelta
            from accounting.vouchers.repositories import VoucherRepository
            from core.services.notification_service import send_email

            target = _date.today() + timedelta(days=7)
            vouchers = VoucherRepository().get_expiring_on(target)
            for v in vouchers:
                try:
                    send_email(
                        to_email=v['issued_by_email'],
                        subject=f"Voucher {v['voucher_code']} expires in 7 days",
                        html_body=f"<p>Your voucher <strong>{v['voucher_code']}</strong> for client {v['client_name']} expires on {v['expires_at']}.</p>",
                    )
                except Exception:
                    logger.exception('Failed to send expiry warning for %s', v['voucher_code'])
            if vouchers:
                logger.info('Sent %d voucher expiry warning(s)', len(vouchers))
        except Exception:
            logger.exception('Failed to run voucher expiry warning job')

    def _voucher_monthly_digest():
        """1st business day: send monthly voucher digest."""
        from datetime import date as _date
        today = _date.today()
        # Only run on first 3 days of month (covers weekends)
        if today.day > 3:
            return
        # Only run on weekdays
        if today.weekday() >= 5:
            return
        try:
            from accounting.vouchers.digest import send_monthly_digest
            send_monthly_digest()
        except Exception:
            logger.exception('Failed to run monthly voucher digest')

    scheduler.add_job(
        _archive_redeemed_vouchers,
        'interval',
        minutes=30,
        id='archive_redeemed_vouchers',
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )

    scheduler.add_job(
        _expire_vouchers,
        'cron',
        hour=0, minute=30,
        id='expire_vouchers',
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )

    scheduler.add_job(
        _voucher_expiry_warnings,
        'cron',
        hour=9, minute=0,
        id='voucher_expiry_warnings',
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )

    scheduler.add_job(
        _voucher_monthly_digest,
        'cron',
        hour=9, minute=15,
        day=1,
        id='voucher_monthly_digest',
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )

    # Happy: nightly stats rollup (BEFORE purge) so the Board funnel survives the purge
    scheduler.add_job(
        happy_rollup_campaign_stats,
        'cron',
        hour=1, minute=15,
        id='happy_rollup_campaign_stats',
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )

    # Happy: nightly 30-day analytics purge (Law 190/2018 Art. 5) + new-joiner target refresh
    scheduler.add_job(
        purge_happy_events,
        'cron',
        hour=1, minute=30,
        id='happy_purge_events',
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )

    scheduler.add_job(
        refresh_happy_targets,
        'cron',
        hour=2, minute=0,
        id='happy_refresh_targets',
        replace_existing=True,
        misfire_grace_time=300,
        coalesce=True,
    )

    # Happy: escalation ladder for unacknowledged mandatory campaigns (spec §5.4)
    scheduler.add_job(
        happy_process_escalations,
        'cron',
        hour=8, minute=30,
        id='happy_process_escalations',
        replace_existing=True,
        misfire_grace_time=600,
        coalesce=True,
    )

    # Happy: monthly giveable grant + prior-month expiry (spec §7.4), 1st of month
    scheduler.add_job(
        happy_grant_monthly_giveable,
        'cron',
        day=1, hour=0, minute=15,
        id='happy_grant_monthly_giveable',
        replace_existing=True,
        misfire_grace_time=3600,
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
