"""Verification scheduled tasks."""
import logging
from datetime import datetime

logger = logging.getLogger('jarvis.tasks.verification')


def run_end_of_month_verification():
    """Auto-run data verification on the last day of each month."""
    try:
        from core.connectors.verification.verification_service import VerificationService
        now = datetime.now()
        svc = VerificationService()
        result = svc.run_verification(year=now.year, month=now.month, triggered_by=None)
        total = result.get('discrepancy_count', 0)
        logger.info(f"End-of-month verification complete: {total} discrepancies for {now.year}-{now.month:02d}")
    except Exception as e:
        logger.error(f"End-of-month verification failed: {e}")
