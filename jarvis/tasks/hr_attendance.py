"""HR attendance scheduled tasks — missing punch detection & notifications."""
import hashlib
import logging

logger = logging.getLogger('jarvis.tasks.hr_attendance')


def _stable_hash(key: str) -> int:
    """Deterministic hash that survives process restarts (unlike Python's hash())."""
    return int(hashlib.md5(key.encode()).hexdigest(), 16) % 2147483647


def check_missing_punches():
    """Daily check for missing punches — notify managers + HR.

    Runs at 10:00 AM (after BioStar sync at 01:00).
    Skips weekends (on Monday, also checks Friday).
    Respects per-employee notify_missing_punch toggle.
    Uses smart_notification_state for 24h cooldown per employee+date.
    """
    from datetime import date, timedelta

    today = date.today()
    # Build list of days to check: yesterday, plus Friday if today is Monday
    days_to_check = []
    yesterday = today - timedelta(days=1)
    if yesterday.weekday() < 5:  # Mon-Fri
        days_to_check.append(yesterday)
    if today.weekday() == 0:  # Monday — also check Friday
        friday = today - timedelta(days=3)
        if friday not in days_to_check:
            days_to_check.append(friday)

    if not days_to_check:
        logger.debug("Skipping missing punch check — no weekdays to check")
        return

    try:
        from hr.events.repositories.employee_overview_repository import EmployeeOverviewRepository
        from core.notifications.notify import notify_users, notify_node_cascade
        from database import get_db, get_cursor, release_db

        repo = EmployeeOverviewRepository()
        conn = get_db()
        try:
            cursor = get_cursor(conn)

            for check_date in days_to_check:
                _process_missing_for_date(check_date, repo, cursor, conn)

            conn.commit()
        finally:
            release_db(conn)

    except Exception as e:
        logger.error(f"Missing punch check failed: {e}", exc_info=True)


def _process_missing_for_date(check_date, repo, cursor, conn):
    """Process missing punches for a single date."""
    from core.notifications.notify import notify_users, notify_node_cascade

    missing = repo.get_all_missing_punches_for_date(check_date)

    if not missing:
        logger.info(f"No missing punches for {check_date}")
        return

    logger.info(f"Found {len(missing)} employees with missing punches for {check_date}")

    # Cooldown check — batch lookup
    to_notify = []
    for emp in missing:
        entity_hash = _stable_hash(f"{emp['user_id']}_{check_date.isoformat()}")
        cursor.execute('''
            SELECT 1 FROM smart_notification_state
            WHERE alert_type = 'missing_punch'
              AND entity_type = 'user_date'
              AND entity_id = %s
              AND last_alerted_at > NOW() - INTERVAL '24 hours'
        ''', (entity_hash,))
        if not cursor.fetchone():
            to_notify.append(emp)

    if not to_notify:
        logger.info(f"All missing punch notifications already sent for {check_date} (cooldown)")
        return

    # Pre-fetch L0 and HR users per company (avoid N+1 inside the loop)
    company_l0 = {}  # company -> set of user_ids
    company_hr = {}  # company -> set of user_ids
    companies = {emp.get('company') for emp in to_notify if emp.get('company')}
    for comp in companies:
        cursor.execute('''
            SELECT cr.user_id FROM company_responsables cr
            JOIN companies c ON c.id = cr.company_id WHERE c.company = %s
        ''', (comp,))
        company_l0[comp] = {r['user_id'] for r in cursor.fetchall()}
        cursor.execute('''
            SELECT u.id FROM users u JOIN roles r ON r.id = u.role_id
            WHERE r.name = 'HR' AND u.company = %s AND u.is_active = TRUE
        ''', (comp,))
        company_hr[comp] = {r['id'] for r in cursor.fetchall()}

    # Send notifications for each employee
    date_str = check_date.strftime('%d %b %Y')
    for emp in to_notify:
        user_id = emp['user_id']
        user_name = emp['user_name']
        node_id = emp.get('node_id')
        company = emp.get('company')

        title = f"Pontaj lipsa: {user_name}"
        message = f"{user_name} nu are pontaj pentru {date_str} si nu are concediu sau invoire activ(a)."
        link = f"/app/hr/employees/{user_id}"

        notified_ids = set()
        any_sent = False

        # L1-L5: cascade up the structure_nodes hierarchy
        if node_id:
            try:
                result = notify_node_cascade(
                    node_id, title, message=message, link=link,
                    entity_type='user', entity_id=user_id,
                    type='warning', category='hr_attendance',
                )
                any_sent = True
                # Track notified IDs from cascade result if available
                if isinstance(result, (list, set)):
                    notified_ids.update(result)
            except Exception as e:
                logger.error(f"Failed cascade notify for {user_name} node {node_id}: {e}")

        # L0: company responsables (skip already notified)
        if company:
            try:
                l0_ids = [uid for uid in company_l0.get(company, set())
                          if uid not in notified_ids]
                if l0_ids:
                    notify_users(
                        l0_ids, title, message=message, link=link,
                        entity_type='user', entity_id=user_id,
                        type='warning', category='hr_attendance',
                    )
                    notified_ids.update(l0_ids)
                    any_sent = True
            except Exception as e:
                logger.error(f"Failed L0 notify for {user_name}: {e}")

        # HR role users in same company (skip already notified)
        if company:
            try:
                hr_ids = [uid for uid in company_hr.get(company, set())
                          if uid not in notified_ids]
                if hr_ids:
                    notify_users(
                        hr_ids, title, message=message, link=link,
                        entity_type='user', entity_id=user_id,
                        type='warning', category='hr_attendance',
                    )
                    any_sent = True
            except Exception as e:
                logger.error(f"Failed HR notify for {user_name}: {e}")

        # Record cooldown only if at least one notification was sent
        if any_sent:
            entity_hash = _stable_hash(f"{user_id}_{check_date.isoformat()}")
            cursor.execute('''
                INSERT INTO smart_notification_state
                    (alert_type, entity_type, entity_id, last_alerted_at, last_value)
                VALUES ('missing_punch', 'user_date', %s, NOW(), 0)
                ON CONFLICT (alert_type, entity_type, entity_id)
                DO UPDATE SET last_alerted_at = NOW()
            ''', (entity_hash,))

    logger.info(f"Sent missing punch notifications for {len(to_notify)} employees on {check_date}")
