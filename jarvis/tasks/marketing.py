"""Marketing scheduled tasks."""
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger('jarvis.tasks.marketing')


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


def auto_archive_completed_projects():
    """Auto-archive marketing projects that have been 'completed' for 24+ hours."""
    try:
        from marketing.repositories import ProjectRepository
        repo = ProjectRepository()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        rows = repo.query_all(
            "SELECT id, name FROM mkt_projects WHERE status = 'completed' AND updated_at <= %s AND deleted_at IS NULL",
            (cutoff,),
        )
        archived = 0
        for row in rows:
            try:
                repo.archive(row['id'])
                archived += 1
                logger.info(f"Auto-archived project '{row['name']}' (id={row['id']})")
            except Exception as e:
                logger.warning(f"Failed to auto-archive project {row['id']}: {e}")
        if archived > 0:
            logger.info(f"Auto-archive: {archived} completed project(s) archived")
    except Exception as e:
        logger.error(f"Auto-archive completed projects task failed: {e}")
