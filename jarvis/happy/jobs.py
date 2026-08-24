"""Happy background jobs — analytics purge, target refresh, escalation ladder."""
import logging
from datetime import datetime, timezone

from happy.repositories import SurfaceRepository, CampaignRepository
from happy.services.escalation import due_step

logger = logging.getLogger("jarvis.happy.jobs")

RETENTION_DAYS = 30


def _as_dt(value):
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return value


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


def process_escalations(now=None):
    """Escalation ladder (spec §5.4). For each live mandatory campaign, advance
    unacknowledged targeted users through the escalation steps (one per run, in
    order), notifying and auditing. Returns the number of steps fired."""
    now = now or datetime.now(timezone.utc)
    srepo = SurfaceRepository()
    crepo = CampaignRepository()
    campaigns = crepo.query_all(
        "SELECT id, title, published_at, ack_deadline_at FROM happy.campaigns "
        "WHERE status = 'live' AND ack_mode <> 'none'"
    )
    fired = 0
    for c in campaigns:
        pub, deadline = _as_dt(c.get("published_at")), _as_dt(c.get("ack_deadline_at"))
        unacked = srepo.query_all(
            """SELECT t.user_id, COALESCE(e.last_step, 0) AS last_step
                 FROM happy.campaign_targets t
                 LEFT JOIN happy.acknowledgements a
                        ON a.campaign_id = t.campaign_id AND a.user_id = t.user_id
                 LEFT JOIN happy.escalation_state e
                        ON e.campaign_id = t.campaign_id AND e.user_id = t.user_id
                WHERE t.campaign_id = %s AND a.id IS NULL""",
            (c["id"],),
        )
        for r in unacked:
            step = due_step(now, pub, deadline, r["last_step"])
            if not step:
                continue
            _fire_escalation_step(srepo, c, r["user_id"], step)
            srepo.execute(
                """INSERT INTO happy.escalation_state (campaign_id, user_id, last_step, last_fired_at)
                   VALUES (%s, %s, %s, NOW())
                   ON CONFLICT (campaign_id, user_id)
                   DO UPDATE SET last_step = EXCLUDED.last_step, last_fired_at = NOW()""",
                (c["id"], r["user_id"], step),
            )
            fired += 1
    logger.info("happy: escalation fired %s steps across %s campaigns", fired, len(campaigns))
    return fired


def _fire_escalation_step(srepo, campaign, user_id, step):
    """Notify (in-app + push) and audit one escalation step. Step 3 also notifies
    the employee's direct manager. Notification failures never block the ladder."""
    title = f"Confirmare necesară: {campaign['title']}"
    try:
        from core.notifications.notify import notify_users
        if step in (1, 2, 3, 4):
            notify_users([user_id], title, message="Ai o confirmare de citit.",
                         link="/app/hub", category="happy_announce")
        if step == 3:
            for mgr in _direct_manager_ids(srepo, user_id):
                notify_users([mgr], f"Confirmare restantă în echipă: {campaign['title']}",
                             message="Un membru al echipei nu a confirmat o notificare obligatorie.",
                             link="/app/hub", category="happy_announce")
    except Exception:
        logger.exception("happy: escalation notify failed (step=%s campaign=%s)", step, campaign["id"])
    srepo.audit("escalation_step", campaign["id"], user_id, {"step": step})


def rollup_campaign_stats(now=None):
    """Aggregate raw campaign_events into campaign_daily_stats (spec §10) so the
    Board reads rollups, never raw events — and the funnel survives the 30-day
    purge. Runs nightly BEFORE purge_happy_events. Returns rows written."""
    now = now or datetime.now(timezone.utc)
    repo = SurfaceRepository()
    n = repo.execute(
        """INSERT INTO happy.campaign_daily_stats
               (campaign_id, day, cohort_key, targeted, reached, read_8s, clicked, acknowledged, dismissed)
           SELECT e.campaign_id, e.created_at::date AS day, 'all',
                  (SELECT count(*) FROM happy.campaign_targets t WHERE t.campaign_id = e.campaign_id),
                  count(DISTINCT e.user_id) FILTER (WHERE e.event_type = 'impression'),
                  count(DISTINCT e.user_id) FILTER (WHERE e.event_type = 'read'),
                  count(DISTINCT e.user_id) FILTER (WHERE e.event_type = 'click'),
                  count(DISTINCT e.user_id) FILTER (WHERE e.event_type = 'ack'),
                  count(DISTINCT e.user_id) FILTER (WHERE e.event_type = 'dismiss')
             FROM happy.campaign_events e
            WHERE e.created_at >= (%s::date - INTERVAL '1 day')
            GROUP BY e.campaign_id, e.created_at::date
           ON CONFLICT (campaign_id, day, cohort_key) DO UPDATE
             SET targeted = EXCLUDED.targeted, reached = EXCLUDED.reached, read_8s = EXCLUDED.read_8s,
                 clicked = EXCLUDED.clicked, acknowledged = EXCLUDED.acknowledged, dismissed = EXCLUDED.dismissed""",
        (now,),
    )
    logger.info("happy: rolled up campaign stats (%s rows)", n)
    return n


def grant_monthly_giveable(now=None):
    """Grant the monthly giveable allowance to every active user and expire the
    prior month's leftover (spec §7.4). Idempotent per month (period guard in
    _ensure_wallet). Manager top-up is a later refinement. Returns users processed."""
    from happy.repositories import PraiseRepository
    now = now or datetime.now(timezone.utc)
    repo = PraiseRepository()
    users = repo.query_all("SELECT id FROM users WHERE is_active")
    for u in users:
        try:
            repo.get_wallet(u["id"], now)   # ensures + grants/expires for this period
        except Exception:
            logger.exception("happy: monthly grant failed for user %s", u["id"])
    logger.info("happy: monthly giveable granted to %s active users", len(users))
    return len(users)


def _direct_manager_ids(srepo, user_id):
    try:
        row = srepo.query_one(
            """SELECT ds.manager_ids
                 FROM users u
                 JOIN department_structure ds
                   ON ds.company = u.company AND ds.department = u.department
                WHERE u.id = %s LIMIT 1""",
            (user_id,),
        )
        return list(row["manager_ids"]) if row and row.get("manager_ids") else []
    except Exception:
        return []
