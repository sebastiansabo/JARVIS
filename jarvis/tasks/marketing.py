"""Marketing scheduled tasks."""
import logging

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
