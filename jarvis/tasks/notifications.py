"""Notification-related scheduled tasks."""
import logging

logger = logging.getLogger('jarvis.tasks.notifications')


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


def run_smart_notifications():
    """Run smart notification checks (KPI thresholds, budget utilization, invoice anomalies, e-Factura backlog)."""
    try:
        from core.notifications.smart_service import SmartNotificationService
        svc = SmartNotificationService()
        svc.run_all_checks()
    except Exception as e:
        logger.error(f"Smart notification task failed: {e}")


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
