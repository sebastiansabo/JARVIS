"""Happy background jobs — nightly analytics purge + new-joiner target refresh."""
import logging

from happy.repositories import SurfaceRepository, CampaignRepository

logger = logging.getLogger("jarvis.happy.jobs")

RETENTION_DAYS = 30


def purge_happy_events(retention_days=RETENTION_DAYS):
    """DELETE happy.campaign_events older than N days.

    Enforces the Law 190/2018 Art. 5 30-day retention cap in code, not policy prose
    (spec §9.1). happy.acknowledgements is retained separately (compliance basis).
    Returns the number of rows deleted.
    """
    n = SurfaceRepository().execute(
        "DELETE FROM happy.campaign_events WHERE created_at < NOW() - make_interval(days => %s)",
        (retention_days,),
    )
    logger.info("happy: purged %s campaign_events older than %s days", n, retention_days)
    return n


def refresh_happy_targets():
    """New-joiner inheritance (spec §5.5).

    Additively re-materialize campaign_targets for every live campaign so users
    created after publication inherit open must-reads. Returns campaigns processed.
    """
    repo = CampaignRepository()
    live = repo.query_all("SELECT id FROM happy.campaigns WHERE status = 'live'")
    for row in live:
        try:
            repo.refresh_targets(row["id"], prune=False)
        except Exception:
            logger.exception("happy: refresh_targets failed for campaign %s", row["id"])
    logger.info("happy: refreshed targets for %s live campaigns", len(live))
    return len(live)
