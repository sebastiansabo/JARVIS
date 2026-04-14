"""Approval engine scheduled tasks."""
import logging

logger = logging.getLogger('jarvis.tasks.approvals')


def process_approval_tasks():
    """Run approval engine scheduled tasks: timeouts, reminders, expirations, delegation cleanup."""
    try:
        from core.approvals.engine import ApprovalEngine
        from core.approvals.repositories import DelegationRepository
        engine = ApprovalEngine()
        engine.process_timeouts()
        engine.process_reminders()
        engine.process_expirations()
        DelegationRepository().deactivate_expired()
        logger.debug("Approval engine scheduled tasks completed")
    except Exception as e:
        logger.error(f"Approval engine scheduled tasks failed: {e}")
