"""Scheduler wrapper for the Weekly Driving Digest (see foi_parcurs.services.driving_digest_service)."""
import logging
from foi_parcurs.services.driving_digest_service import generate_and_send

logger = logging.getLogger('jarvis.tasks.driving_digest')


def run_weekly_driving_digest():
    try:
        result = generate_and_send()
        logger.info('weekly_driving_digest result: %s', result)
    except Exception:
        logger.error('weekly_driving_digest failed', exc_info=True)
