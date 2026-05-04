"""Sincron scheduled tasks."""
import logging

logger = logging.getLogger('jarvis.tasks.sincron')


def _save_sincron_cron_log(job_id, success, message):
    """Persist last-run result into connector config for UI display."""
    try:
        import json as _json
        from datetime import datetime as _dt
        from core.connectors.repositories.connector_repository import ConnectorRepository
        repo = ConnectorRepository()
        connector = repo.get_by_type('sincron')
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


def sync_sincron_timesheets():
    """Sync current month timesheets from Sincron for all companies."""
    try:
        from core.connectors.sincron.services.sincron_sync_service import SincronSyncService
        svc = SincronSyncService()
        status = svc.get_status()
        if not status.get('connected'):
            _save_sincron_cron_log('sincron_sync_timesheets', False, 'Skipped — not connected')
            return
        result = svc.sync_timesheets()
        if result.get('success'):
            msg = f"{result.get('total_employees', 0)} employees, {result.get('total_records', 0)} records"
            logger.info(f"Sincron timesheet sync: {msg}")
            _save_sincron_cron_log('sincron_sync_timesheets', True, msg)
        else:
            msg = result.get('error', 'Unknown error')
            logger.warning(f"Sincron timesheet sync failed: {msg}")
            _save_sincron_cron_log('sincron_sync_timesheets', False, msg)
    except Exception as e:
        logger.error(f"Sincron timesheet sync task failed: {e}")
        _save_sincron_cron_log('sincron_sync_timesheets', False, str(e))
