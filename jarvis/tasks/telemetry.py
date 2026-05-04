"""Telemetry background tasks — session cleanup and data retention."""

from core.utils.logging_config import get_logger
from core.telemetry.repository import TelemetryRepository

logger = get_logger('jarvis.tasks.telemetry')
_repo = TelemetryRepository()


def close_stale_sessions():
    """Close sessions with no heartbeat for >5 minutes."""
    try:
        count = _repo.close_stale_sessions(stale_minutes=5)
        if count:
            logger.info(f'Closed {count} stale telemetry sessions')
    except Exception as e:
        logger.error(f'Failed to close stale sessions: {e}')


def cleanup_old_telemetry():
    """Delete telemetry data older than 90 days."""
    try:
        events_deleted = _repo.delete_old_events(retention_days=90)
        sessions_deleted = _repo.delete_old_sessions(retention_days=90)
        if events_deleted or sessions_deleted:
            logger.info(f'Telemetry cleanup: {events_deleted} events, {sessions_deleted} sessions deleted')
    except Exception as e:
        logger.error(f'Telemetry cleanup failed: {e}')
