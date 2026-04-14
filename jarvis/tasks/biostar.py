"""BioStar scheduled tasks."""
import logging

logger = logging.getLogger('jarvis.tasks.biostar')


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
