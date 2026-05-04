"""HR Courses scheduled tasks — certification expiry notifications."""
import logging

logger = logging.getLogger('jarvis.tasks.hr_courses')


def check_course_cert_expiry():
    """Daily check for certifications expiring within 30 days.

    Sends in-app + push notifications to employees whose course
    certifications are about to expire. Uses smart_notification_state
    for 7-day cooldown to avoid notification spam.
    """
    try:
        from hr.courses.repositories.certification_repository import CertificationRepository
        from core.notifications.notify import notify_user
        from database import get_db, get_cursor, release_db

        cert_repo = CertificationRepository()

        # Also expire any overdue certs first
        expired_count = cert_repo.expire_overdue()
        if expired_count:
            logger.info(f"Marked {expired_count} overdue certifications as expired")

        # Get certs expiring in next 30 days
        expiring = cert_repo.get_expiring(days_ahead=30)
        if not expiring:
            logger.debug("No certifications expiring in the next 30 days")
            return

        logger.info(f"Found {len(expiring)} certifications expiring within 30 days")

        # Cooldown: don't re-notify same cert within 7 days
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            notified = 0

            for cert in expiring:
                cooldown_key = f"hr_course_expiry:{cert['id']}"
                cursor.execute('''
                    SELECT 1 FROM smart_notification_state
                    WHERE notification_key = %s
                      AND last_sent_at > CURRENT_TIMESTAMP - INTERVAL '7 days'
                ''', (cooldown_key,))
                if cursor.fetchone():
                    continue  # Already notified recently

                days = cert.get('days_until_expiry', 0)
                course_type = cert.get('course_type_name', 'Unknown')
                employee_id = cert['employee_id']

                if days <= 0:
                    title = f'Certificare expirată: {course_type}'
                    msg = f'Certificarea ta pentru "{course_type}" a expirat. Contactează HR pentru recertificare.'
                elif days <= 7:
                    title = f'Certificare expiră în {days} zile: {course_type}'
                    msg = f'Certificarea ta pentru "{course_type}" expiră în {days} zile. Contactează HR.'
                else:
                    title = f'Certificare expiră în {days} zile: {course_type}'
                    msg = f'Certificarea ta pentru "{course_type}" expiră pe {cert["expiry_date"]}.'

                notify_user(
                    employee_id,
                    title,
                    message=msg,
                    link='/app/profile?tab=courses',
                    entity_type='hr_certification',
                    entity_id=cert['id'],
                    type='warning' if days <= 7 else 'info',
                    category='hr_course_expiry',
                )

                # Update cooldown
                cursor.execute('''
                    INSERT INTO smart_notification_state (notification_key, last_sent_at)
                    VALUES (%s, CURRENT_TIMESTAMP)
                    ON CONFLICT (notification_key)
                    DO UPDATE SET last_sent_at = CURRENT_TIMESTAMP
                ''', (cooldown_key,))

                notified += 1

            conn.commit()
            logger.info(f"Sent {notified} certification expiry notifications")

        finally:
            release_db(conn)

    except Exception as e:
        logger.error(f"Certification expiry check failed: {e}", exc_info=True)
