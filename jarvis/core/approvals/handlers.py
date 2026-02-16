"""Approval event handlers — fires in-app notifications + entity status changes.

Registered at app startup via register_approval_hooks().
"""

import logging
from core.notifications.notify import notify_user, notify_users

logger = logging.getLogger('jarvis.core.approvals.handlers')


def register_approval_hooks():
    """Register all approval event handlers. Call once at app startup."""
    from core.approvals.hooks import on

    on('approval.submitted', _on_submitted)
    on('approval.approved', _on_approved)
    on('approval.rejected', _on_rejected)
    on('approval.returned', _on_returned)
    on('approval.step_advanced', _on_step_advanced)
    on('approval.reminder', _on_reminder)

    logger.info('Approval notification hooks registered')


def _on_submitted(payload):
    """Notify step 1 approvers that a new request needs their attention."""
    request_id = payload.get('request_id')
    entity_type = payload.get('entity_type', '')
    entity_id = payload.get('entity_id')
    flow_name = payload.get('flow_name', '')

    approver_ids = _get_current_step_approvers(request_id)
    if approver_ids:
        notify_users(
            approver_ids,
            f'New approval request: {entity_type} #{entity_id}',
            message=f'Flow: {flow_name}. Please review and approve.',
            link='/app/approvals',
            entity_type=entity_type,
            entity_id=entity_id,
            type='approval',
        )


def _on_approved(payload):
    """Notify requester their request was approved. Update entity status."""
    request_id = payload.get('request_id')
    entity_type = payload.get('entity_type', '')
    entity_id = payload.get('entity_id')
    auto = payload.get('auto_approved', False)

    requester_id = _get_requester(request_id)
    if requester_id:
        msg = 'Auto-approved' if auto else 'All approval steps completed'
        notify_user(
            requester_id,
            f'{entity_type.replace("_", " ").title()} #{entity_id} approved',
            message=msg,
            link='/app/approvals',
            entity_type=entity_type,
            entity_id=entity_id,
            type='approval',
        )

    # Auto-update invoice status to 'approved'
    if entity_type == 'invoice' and entity_id:
        try:
            from accounting.invoices.repositories.invoice_repository import InvoiceRepository
            InvoiceRepository().update(entity_id, status='approved')
            logger.info(f'Invoice #{entity_id} status set to approved via approval hook')
        except Exception as e:
            logger.error(f'Failed to update invoice status on approval: {e}')


def _on_rejected(payload):
    """Notify requester their request was rejected."""
    request_id = payload.get('request_id')
    entity_type = payload.get('entity_type', '')
    entity_id = payload.get('entity_id')
    note = payload.get('resolution_note', '')

    requester_id = _get_requester(request_id)
    if requester_id:
        notify_user(
            requester_id,
            f'{entity_type.replace("_", " ").title()} #{entity_id} rejected',
            message=note or 'Your request was rejected.',
            link='/app/approvals',
            entity_type=entity_type,
            entity_id=entity_id,
            type='approval',
        )


def _on_returned(payload):
    """Notify requester their request was returned for changes."""
    request_id = payload.get('request_id')
    entity_type = payload.get('entity_type', '')
    entity_id = payload.get('entity_id')
    comment = payload.get('comment', '')

    requester_id = _get_requester(request_id)
    if requester_id:
        notify_user(
            requester_id,
            f'{entity_type.replace("_", " ").title()} #{entity_id} returned',
            message=comment or 'Please review and resubmit.',
            link='/app/approvals',
            entity_type=entity_type,
            entity_id=entity_id,
            type='approval',
        )


def _on_step_advanced(payload):
    """Notify next step approvers that a request needs their attention."""
    request_id = payload.get('request_id')
    entity_type = payload.get('entity_type', '')
    entity_id = payload.get('entity_id')
    step_name = payload.get('step_name', '')

    approver_ids = _get_current_step_approvers(request_id)
    if approver_ids:
        notify_users(
            approver_ids,
            f'Approval request awaiting your review',
            message=f'{entity_type.replace("_", " ").title()} #{entity_id} — Step: {step_name}',
            link='/app/approvals',
            entity_type=entity_type,
            entity_id=entity_id,
            type='approval',
        )


def _on_reminder(payload):
    """Remind current step approvers about a pending request."""
    request_id = payload.get('request_id')

    approver_ids = _get_current_step_approvers(request_id)
    if approver_ids:
        notify_users(
            approver_ids,
            'Reminder: Approval request pending your decision',
            link='/app/approvals',
            type='approval',
        )


# ── Helpers ──

def _get_requester(request_id):
    """Get the user_id of who submitted the request."""
    try:
        from core.approvals.repositories import RequestRepository
        req = RequestRepository().get_by_id(request_id)
        return req['requested_by'] if req else None
    except Exception as e:
        logger.error(f'Failed to get requester for request {request_id}: {e}')
        return None


def _get_current_step_approvers(request_id):
    """Get user IDs of approvers for the current step of a request."""
    try:
        from core.approvals.repositories import RequestRepository, FlowRepository
        from database import get_db, get_cursor, release_db

        req = RequestRepository().get_by_id(request_id)
        if not req or not req.get('current_step_id'):
            return []

        step = FlowRepository().get_step_by_id(req['current_step_id'])
        if not step:
            return []

        approver_type = step.get('approver_type', '')

        if approver_type == 'specific_user' and step.get('approver_user_id'):
            return [step['approver_user_id']]

        if approver_type == 'role' and step.get('approver_role_name'):
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute('''
                    SELECT u.id FROM users u
                    JOIN roles r ON r.id = u.role_id
                    WHERE r.name = %s AND u.is_active = TRUE
                ''', (step['approver_role_name'],))
                return [row['id'] for row in cursor.fetchall()]
            finally:
                release_db(conn)

        if approver_type == 'department_manager':
            # Would need entity context to resolve department — skip for now
            return []

        return []
    except Exception as e:
        logger.error(f'Failed to get approvers for request {request_id}: {e}')
        return []
