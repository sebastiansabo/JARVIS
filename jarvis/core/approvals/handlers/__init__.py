"""Approval event handlers package.

Public API: register_approval_hooks() — unchanged import path for app.py.
"""
import logging
import os

logger = logging.getLogger('jarvis.core.approvals.handlers')

# Re-exported for backwards-compatible tests that do `import handlers as h; h._APP_BASE_URL`
_APP_BASE_URL = os.environ.get('APP_BASE_URL', 'https://jarvis.autoworld.ro')


def register_approval_hooks():
    """Register all approval event handlers. Call once at app startup."""
    from core.approvals.hooks import on
    from .event_handlers import (
        _on_submitted, _on_approved, _on_rejected,
        _on_returned, _on_step_advanced, _on_reminder, _on_cancelled,
    )

    on('approval.submitted', _on_submitted)
    on('approval.approved', _on_approved)
    on('approval.rejected', _on_rejected)
    on('approval.returned', _on_returned)
    on('approval.step_advanced', _on_step_advanced)
    on('approval.reminder', _on_reminder)
    on('approval.cancelled', _on_cancelled)

    logger.info('Approval notification hooks registered')
