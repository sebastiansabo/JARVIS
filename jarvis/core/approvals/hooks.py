"""Simple in-process callback registry for approval events.

Usage:
    from core.approvals.hooks import on, fire

    # Register handler
    on('approval.approved', my_handler)

    # Fire event (called by ApprovalEngine)
    fire('approval.approved', {'request_id': 1, 'entity_type': 'invoice', 'entity_id': 42})

Events:
    approval.submitted    — request created
    approval.decided      — individual decision made
    approval.step_advanced — moved to next step
    approval.approved     — final approval (all steps done)
    approval.rejected     — rejected at any step
    approval.returned     — sent back for revision
    approval.cancelled    — withdrawn by requester
    approval.escalated    — escalated due to timeout or manual
    approval.expired      — timed out without decision
    approval.reminder     — reminder sent to approver
"""

import logging

logger = logging.getLogger('jarvis.core.approvals.hooks')

_registry: dict[str, list] = {}


def on(event_type: str, callback):
    """Register a callback for an event type."""
    _registry.setdefault(event_type, []).append(callback)
    logger.debug(f"Registered hook for {event_type}: {callback.__name__}")


def fire(event_type: str, payload: dict):
    """Call all registered callbacks for event_type."""
    callbacks = _registry.get(event_type, [])
    for cb in callbacks:
        try:
            cb(payload)
        except Exception as e:
            logger.error(f"Hook error for {event_type} in {cb.__name__}: {e}", exc_info=True)


def clear(event_type: str = None):
    """Clear hooks. If event_type given, clear only that type. Used in tests."""
    if event_type:
        _registry.pop(event_type, None)
    else:
        _registry.clear()
