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
_scheduler_deferred = False  # True when another worker holds the lock


def cleanup_old_unallocated_invoices():
    """Permanently delete unallocated e-Factura invoices older than 15 days."""
    try:
        from core.connectors.efactura.repositories.invoice_repo import InvoiceRepository
        repo = InvoiceRepository()
        count = repo.delete_old_unallocated(days=15)
        if count > 0:
            logger.info(f"Cleanup: deleted {count} old unallocated e-Factura invoices (>15 days)")
    except Exception as e:
        logger.error(f"Cleanup task failed: {e}")


def cleanup_vin_cache():
    """Delete expired VIN decoder cache entries."""
    try:
        from carpark.connectors.vin_decoder.cache import VINCache
        cache = VINCache()
        count = cache.cleanup_expired()
        if count > 0:
            logger.info(f"Cleanup: deleted {count} expired VIN cache entries")
    except Exception as e:
        logger.error(f"VIN cache cleanup task failed: {e}")


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


def cleanup_push_rate_limit_log():
    """Delete push rate limit log entries older than 7 days."""
    try:
        from core.notifications.repositories import PushRateLimitRepository
        repo = PushRateLimitRepository()
        count = repo.cleanup_old(days=7)
        if count > 0:
            logger.info(f"Cleanup: deleted {count} old push rate limit log entries (>7 days)")
    except Exception as e:
        logger.error(f"Push rate limit cleanup failed: {e}")


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


def extract_ai_knowledge():
    """Extract learned patterns from positively-rated AI responses."""
    try:
        from ai_agent.services.knowledge_service import KnowledgeService
        svc = KnowledgeService()
        result = svc.extract_from_feedback()
        extracted = result.get('extracted', 0)
        merged = result.get('merged', 0)
        if extracted or merged:
            logger.info(f"Knowledge extraction: {extracted} new, {merged} merged")
    except Exception as e:
        logger.error(f"Knowledge extraction task failed: {e}")


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


def field_sales_follow_up_reminders():
    """Trigger 4: Notify KAMs about visits with follow-up date = tomorrow.

    Runs daily at 08:00. Checks kam_visit_notes.structured_note->>'follow_up_date'
    and sends a reminder to the assigned KAM if no follow-up visit is planned.
    """
    try:
        from datetime import date, timedelta
        from field_sales.repositories.visit_repository import VisitRepository
        from field_sales.repositories.client_fs_repository import ClientFSRepository
        from field_sales.notifications import notify_user
        from core.services.notification_service import send_email, is_smtp_configured
        from core.auth.repositories import UserRepository

        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        visit_repo = VisitRepository()
        user_repo = UserRepository()

        # Find notes where follow_up_date is tomorrow
        rows = visit_repo.query_all('''
            SELECT n.visit_id, n.structured_note, v.kam_id, v.client_id,
                   c.display_name AS client_name
            FROM kam_visit_notes n
            JOIN kam_visit_plans v ON v.id = n.visit_id
            JOIN crm_clients c ON c.id = v.client_id
            WHERE n.structured_note->>'follow_up_date' = %s
        ''', (tomorrow,))

        if not rows:
            return

        smtp_ok = is_smtp_configured()
        sent = 0

        for row in rows:
            kam_id = row['kam_id']
            client_name = row.get('client_name', 'Client')

            # Check if a follow-up visit is already planned
            existing = visit_repo.query_one('''
                SELECT id FROM kam_visit_plans
                WHERE kam_id = %s AND client_id = %s
                  AND planned_date = %s AND status = 'planned'
            ''', (kam_id, row['client_id'], tomorrow))
            if existing:
                continue

            # Send reminder
            notify_user(
                kam_id,
                f'Reminder follow-up — {client_name}',
                message=f'Mâine este data de follow-up pentru {client_name}. Planifică o vizită.',
                link='/app/field-sales',
                entity_type='field_sales_visit',
                entity_id=row['visit_id'],
                type='info',
                category='field_sales',
            )

            if smtp_ok:
                user = user_repo.get_by_id(kam_id)
                email = user.get('email') if user else None
                if email:
                    send_email(
                        email,
                        f'[JARVIS] Reminder follow-up — {client_name}',
                        f'<pre>Mâine ({tomorrow}) este data de follow-up pentru {client_name}.\n\nPlanifică o vizită: https://jarvis.autoworld.ro/field-sales</pre>',
                        text_body=f'Mâine ({tomorrow}) este data de follow-up pentru {client_name}.',
                        skip_global_cc=True,
                    )
            sent += 1

        if sent:
            logger.info(f"Field Sales follow-up reminders: {sent} sent for {tomorrow}")
    except Exception as e:
        logger.error(f"Field Sales follow-up reminders failed: {e}")


def field_sales_overdue_visit_alerts():
    """Trigger 5: Alert managers about overdue visits (planned but not completed).

    Runs daily at 18:00. Checks kam_visit_plans with status='planned'
    and planned_date < today.
    """
    try:
        from datetime import date
        from field_sales.repositories.visit_repository import VisitRepository
        from core.services.notification_service import (
            send_email, get_managers_for_department, is_smtp_configured,
        )
        from core.notifications.notify import notify_users
        from core.auth.repositories import UserRepository

        today = date.today().isoformat()
        visit_repo = VisitRepository()
        user_repo = UserRepository()

        overdue = visit_repo.query_all('''
            SELECT v.id, v.kam_id, v.client_id, v.planned_date, v.visit_type,
                   c.display_name AS client_name
            FROM kam_visit_plans v
            JOIN crm_clients c ON c.id = v.client_id
            WHERE v.status = 'planned' AND v.planned_date < %s
            ORDER BY v.planned_date
        ''', (today,))

        if not overdue:
            return

        smtp_ok = is_smtp_configured()

        # Group by KAM for consolidated notifications
        by_kam = {}
        for v in overdue:
            kam_id = v['kam_id']
            if kam_id not in by_kam:
                by_kam[kam_id] = []
            by_kam[kam_id].append(v)

        notified_managers = set()

        for kam_id, visits in by_kam.items():
            user = user_repo.get_by_id(kam_id)
            if not user:
                continue
            kam_name = user.get('name', 'KAM')
            department = user.get('department')
            company = user.get('company')

            managers = get_managers_for_department(department, company) if department else []
            manager_emails = [m.get('email') for m in managers if m.get('email')]
            manager_ids = [m.get('id') for m in managers if m.get('id')]

            if not manager_ids:
                continue

            visit_lines = '\n'.join(
                f"  - {v.get('client_name', '?')} · {v.get('planned_date')} · {v.get('visit_type', 'general')}"
                for v in visits
            )

            subject = f'[JARVIS] {len(visits)} vizit{"e" if len(visits) > 1 else "ă"} restant{"e" if len(visits) > 1 else "ă"} — {kam_name}'
            body = f"""{kam_name} are {len(visits)} vizit{"e" if len(visits) > 1 else "ă"} restant{"e" if len(visits) > 1 else "ă"}:

{visit_lines}

Verificați în JARVIS Field Sales."""

            if smtp_ok:
                for email in manager_emails:
                    send_email(email, subject, f'<pre>{body}</pre>', text_body=body, skip_global_cc=True)

            # Deduplicate manager notifications
            new_ids = [mid for mid in manager_ids if mid not in notified_managers]
            if new_ids:
                notify_users(
                    new_ids,
                    f'{len(visits)} vizite restante — {kam_name}',
                    message=f'Vizite neefectuate de {kam_name}',
                    link='/app/field-sales',
                    entity_type='field_sales_visit',
                    type='warning',
                    category='field_sales',
                )
                notified_managers.update(new_ids)

        total_overdue = len(overdue)
        logger.info(f"Field Sales overdue alerts: {total_overdue} overdue visits across {len(by_kam)} KAMs")
    except Exception as e:
        logger.error(f"Field Sales overdue visit alerts failed: {e}")


def _save_biostar_cron_log(job_id, success, message):
    """Persist last-run result into connector config for UI display."""
    try:
        import json as _json
        from datetime import datetime as _dt
        from core.connectors.repositories.connector_repository import ConnectorRepository
        repo = ConnectorRepository()
        connector = repo.get_by_type('biostar')
        if not connector:
            return
        cfg = connector.get('config') or {}
        if isinstance(cfg, str):
            cfg = _json.loads(cfg)
        cron_jobs = cfg.get('cron_jobs', {})
        job_settings = cron_jobs.get(job_id, {})
        job_settings['last_run'] = _dt.now().isoformat()
        job_settings['last_success'] = success
        job_settings['last_message'] = message
        cron_jobs[job_id] = job_settings
        cfg['cron_jobs'] = cron_jobs
        repo.update(connector['id'], config=cfg)
    except Exception as e:
        logger.error(f"Failed to save cron log for {job_id}: {e}")


def sync_biostar_events():
    """Incremental sync of BioStar punch events."""
    try:
        from core.connectors.biostar.services.biostar_sync_service import BioStarSyncService
        svc = BioStarSyncService()
        status = svc.get_status()
        if not status.get('connected'):
            _save_biostar_cron_log('biostar_sync_events', False, 'Skipped — not connected')
            return
        result = svc.sync_events()
        if result.get('success'):
            data = result.get('data', {})
            msg = f"{data.get('inserted', 0)} new, {data.get('skipped', 0)} skipped"
            logger.info(f"BioStar event sync: {msg}")
            _save_biostar_cron_log('biostar_sync_events', True, msg)
        else:
            msg = result.get('error', 'Unknown error')
            logger.warning(f"BioStar event sync failed: {msg}")
            _save_biostar_cron_log('biostar_sync_events', False, msg)
    except Exception as e:
        logger.error(f"BioStar event sync task failed: {e}")
        _save_biostar_cron_log('biostar_sync_events', False, str(e))


def sync_biostar_users():
    """Full sync of BioStar users with auto-mapping."""
    try:
        from core.connectors.biostar.services.biostar_sync_service import BioStarSyncService
        svc = BioStarSyncService()
        status = svc.get_status()
        if not status.get('connected'):
            _save_biostar_cron_log('biostar_sync_users', False, 'Skipped — not connected')
            return
        result = svc.sync_users()
        if result.get('success'):
            data = result.get('data', {})
            msg = f"{data.get('fetched', 0)} fetched, {data.get('mapped', 0)} mapped"
            logger.info(f"BioStar user sync: {msg}")
            _save_biostar_cron_log('biostar_sync_users', True, msg)
        else:
            msg = result.get('error', 'Unknown error')
            logger.warning(f"BioStar user sync failed: {msg}")
            _save_biostar_cron_log('biostar_sync_users', False, msg)
    except Exception as e:
        logger.error(f"BioStar user sync task failed: {e}")
        _save_biostar_cron_log('biostar_sync_users', False, str(e))


def auto_adjust_biostar_schedules():
    """Auto-adjust yesterday's off-schedule punches to comply with work schedule."""
    try:
        from datetime import date, timedelta
        from core.connectors.biostar.services.biostar_sync_service import BioStarSyncService
        svc = BioStarSyncService()
        status = svc.get_status()
        if not status.get('connected'):
            _save_biostar_cron_log('biostar_auto_adjust', False, 'Skipped — not connected')
            return
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        result = svc.auto_adjust_all(yesterday, threshold=15)
        msg = f"{result['adjusted']} of {result['total_flagged']} adjusted for {yesterday}"
        logger.info(f"BioStar auto-adjust: {msg}")
        _save_biostar_cron_log('biostar_auto_adjust', True, msg)
    except Exception as e:
        logger.error(f"BioStar auto-adjust task failed: {e}")
        _save_biostar_cron_log('biostar_auto_adjust', False, str(e))


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
