"""HR attendance scheduled tasks — missing punch detection & notifications."""
import logging

logger = logging.getLogger('jarvis.tasks.hr_attendance')


def check_missing_punches():
    """Daily check for yesterday's missing punches — notify managers + HR.

    Runs at 10:00 AM (after BioStar sync at 01:00).
    Skips weekends. Respects per-employee notify_missing_punch toggle.
    Uses smart_notification_state for 24h cooldown per employee+date.
    """
    from datetime import date, timedelta

    yesterday = date.today() - timedelta(days=1)
    if yesterday.weekday() >= 5:  # Saturday=5, Sunday=6
        logger.debug("Skipping missing punch check — yesterday was a weekend")
        return

    try:
        from hr.events.repositories.employee_overview_repository import EmployeeOverviewRepository
        from core.notifications.notify import notify_users, notify_node_cascade
        from database import get_db, get_cursor, release_db

        repo = EmployeeOverviewRepository()
        missing = repo.get_all_missing_punches_for_date(yesterday)

        if not missing:
            logger.info(f"No missing punches for {yesterday}")
            return

        logger.info(f"Found {len(missing)} employees with missing punches for {yesterday}")

        # Cooldown check — skip employees already notified for this date
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            to_notify = []
            for emp in missing:
                entity_key = f"{emp['user_id']}_{yesterday.isoformat()}"
                cursor.execute('''
                    SELECT 1 FROM smart_notification_state
                    WHERE alert_type = 'missing_punch'
                      AND entity_type = 'user_date'
                      AND entity_id = %s
                      AND last_alerted_at > NOW() - INTERVAL '24 hours'
                ''', (hash(entity_key) % 2147483647,))
                if not cursor.fetchone():
                    to_notify.append(emp)

            if not to_notify:
                logger.info("All missing punch notifications already sent (cooldown)")
                return

            # Send notifications for each employee
            date_str = yesterday.strftime('%d %b %Y')
            for emp in to_notify:
                user_id = emp['user_id']
                user_name = emp['user_name']
                node_id = emp.get('node_id')
                company = emp.get('company')

                title = f"Pontaj lipsa: {user_name}"
                message = f"{user_name} nu are pontaj pentru {date_str} si nu are concediu sau invoire activ(a)."
                link = f"/app/hr/employees/{user_id}"

                notified_ids = set()

                # L1-L5: cascade up the structure_nodes hierarchy
                if node_id:
                    try:
                        notify_node_cascade(
                            node_id, title, message=message, link=link,
                            entity_type='user', entity_id=user_id,
                            type='warning', category='hr_attendance',
                        )
                    except Exception as e:
                        logger.error(f"Failed cascade notify for {user_name} node {node_id}: {e}")

                # L0: company responsables
                if company:
                    try:
                        cursor.execute('''
                            SELECT cr.user_id
                            FROM company_responsables cr
                            JOIN companies c ON c.id = cr.company_id
                            WHERE c.company = %s
                        ''', (company,))
                        l0_ids = [r['user_id'] for r in cursor.fetchall()
                                  if r['user_id'] not in notified_ids]
                        if l0_ids:
                            notify_users(
                                l0_ids, title, message=message, link=link,
                                entity_type='user', entity_id=user_id,
                                type='warning', category='hr_attendance',
                            )
                    except Exception as e:
                        logger.error(f"Failed L0 notify for {user_name}: {e}")

                # HR role users in same company
                if company:
                    try:
                        cursor.execute('''
                            SELECT u.id FROM users u
                            JOIN roles r ON r.id = u.role_id
                            WHERE r.name = 'HR'
                              AND u.company = %s
                              AND u.is_active = TRUE
                        ''', (company,))
                        hr_ids = [r['id'] for r in cursor.fetchall()
                                  if r['id'] not in notified_ids]
                        if hr_ids:
                            notify_users(
                                hr_ids, title, message=message, link=link,
                                entity_type='user', entity_id=user_id,
                                type='warning', category='hr_attendance',
                            )
                    except Exception as e:
                        logger.error(f"Failed HR notify for {user_name}: {e}")

                # Record cooldown
                entity_key = f"{user_id}_{yesterday.isoformat()}"
                entity_hash = hash(entity_key) % 2147483647
                cursor.execute('''
                    INSERT INTO smart_notification_state
                        (alert_type, entity_type, entity_id, last_alerted_at, last_value)
                    VALUES ('missing_punch', 'user_date', %s, NOW(), 0)
                    ON CONFLICT (alert_type, entity_type, entity_id)
                    DO UPDATE SET last_alerted_at = NOW()
                ''', (entity_hash,))

            conn.commit()
            logger.info(f"Sent missing punch notifications for {len(to_notify)} employees")
        finally:
            release_db(conn)

    except Exception as e:
        logger.error(f"Missing punch check failed: {e}", exc_info=True)
