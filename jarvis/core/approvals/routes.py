"""API routes for the approval engine."""

import logging
from flask import jsonify, request
from flask_login import login_required, current_user

from . import approvals_bp
from .engine import (
    ApprovalEngine, ApprovalError, NoMatchingFlowError, AlreadyPendingError,
    NotAuthorizedError, AlreadyDecidedError, InvalidStateError,
)
from .repositories import FlowRepository, AuditRepository, DelegationRepository
from core.utils.api_helpers import safe_error_response, handle_api_errors

logger = logging.getLogger('jarvis.core.approvals.routes')

_engine = ApprovalEngine()
_flow_repo = FlowRepository()
_audit_repo = AuditRepository()
_delegation_repo = DelegationRepository()


# ════════════════════════════════════════════
# Approval Requests
# ════════════════════════════════════════════

@approvals_bp.route('/api/requests', methods=['POST'])
@login_required
def api_submit_request():
    """Submit an entity for approval."""
    data = request.get_json()
    entity_type = (data.get('entity_type') or '').strip()
    entity_id = data.get('entity_id')
    context = data.get('context') or {}
    priority = data.get('priority', 'normal')
    due_by = data.get('due_by')
    note = data.get('note')

    if not entity_type or entity_id is None:
        return jsonify({'success': False, 'error': 'entity_type and entity_id are required'}), 400

    if note:
        context['requester_note'] = note

    try:
        result = _engine.submit(
            entity_type, int(entity_id), context, current_user.id,
            priority=priority, due_by=due_by,
        )
        return jsonify({'success': True, 'request': _serialize_request(result)})
    except AlreadyPendingError as e:
        return jsonify({'success': False, 'error': str(e)}), 409
    except NoMatchingFlowError as e:
        return jsonify({'success': False, 'error': str(e)}), 404
    except Exception as e:
        logger.exception(f'Submit approval failed: {e}')
        return jsonify({'success': False, 'error': 'Failed to submit approval request'}), 500


@approvals_bp.route('/api/requests', methods=['GET'])
@login_required
def api_list_requests():
    """List approval requests with optional filters."""
    status = request.args.get('status')
    entity_type = request.args.get('entity_type')
    limit = min(int(request.args.get('limit', 50)), 200)
    offset = int(request.args.get('offset', 0))

    from .repositories import RequestRepository
    repo = RequestRepository()
    rows = repo.list_requests(
        status=status, entity_type=entity_type,
        limit=limit, offset=offset,
    )
    return jsonify({'requests': [_serialize_request(r) for r in rows]})


@approvals_bp.route('/api/requests/<int:request_id>', methods=['GET'])
@login_required
def api_get_request(request_id):
    """Get request detail with decisions and audit log."""
    from .repositories import RequestRepository, DecisionRepository
    req = RequestRepository().get_by_id(request_id)
    if not req:
        return jsonify({'success': False, 'error': 'Request not found'}), 404

    decisions = DecisionRepository().get_decisions_for_request(request_id)
    audit = _audit_repo.get_for_request(request_id)
    steps = _flow_repo.get_steps_for_flow(req['flow_id'])

    result = _serialize_request(req)
    result['decisions'] = [_serialize_decision(d) for d in decisions]
    result['audit'] = [_serialize_audit(a) for a in audit]
    result['steps'] = [_serialize_step(s) for s in steps]
    return jsonify(result)


@approvals_bp.route('/api/requests/<int:request_id>/decide', methods=['POST'])
@login_required
def api_decide(request_id):
    """Approve/reject/return the current step."""
    data = request.get_json()
    decision = (data.get('decision') or '').strip()
    comment = data.get('comment')
    conditions = data.get('conditions')
    delegated_to = data.get('delegate_to')
    delegation_reason = data.get('delegation_reason')

    if decision not in ('approved', 'rejected', 'returned', 'delegated', 'abstained'):
        return jsonify({'success': False, 'error': 'Invalid decision type'}), 400

    if decision in ('rejected', 'returned') and not comment:
        return jsonify({'success': False, 'error': 'Comment is required for reject/return'}), 400

    try:
        result = _engine.decide(
            request_id, decision, current_user.id,
            comment=comment, conditions=conditions,
            delegated_to=delegated_to, delegation_reason=delegation_reason,
        )
        return jsonify({'success': True, 'request': _serialize_request(result)})
    except NotAuthorizedError as e:
        return jsonify({'success': False, 'error': str(e)}), 403
    except AlreadyDecidedError as e:
        return jsonify({'success': False, 'error': str(e)}), 409
    except InvalidStateError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.exception(f'Decide failed: {e}')
        return jsonify({'success': False, 'error': 'Failed to record decision'}), 500


@approvals_bp.route('/api/requests/<int:request_id>/cancel', methods=['POST'])
@login_required
def api_cancel_request(request_id):
    """Cancel a pending request."""
    data = request.get_json() or {}
    reason = data.get('reason')

    try:
        result = _engine.cancel(request_id, current_user.id, reason=reason)
        return jsonify({'success': True, 'request': _serialize_request(result)})
    except InvalidStateError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.exception(f'Cancel failed: {e}')
        return jsonify({'success': False, 'error': 'Failed to cancel request'}), 500


@approvals_bp.route('/api/requests/<int:request_id>/resubmit', methods=['POST'])
@login_required
def api_resubmit(request_id):
    """Resubmit a rejected/returned request with updated context."""
    data = request.get_json()
    new_context = data.get('context') or {}

    try:
        result = _engine.resubmit(request_id, new_context, current_user.id)
        return jsonify({'success': True, 'request': _serialize_request(result)})
    except (InvalidStateError, NoMatchingFlowError, AlreadyPendingError) as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.exception(f'Resubmit failed: {e}')
        return jsonify({'success': False, 'error': 'Failed to resubmit'}), 500


@approvals_bp.route('/api/requests/<int:request_id>/escalate', methods=['POST'])
@login_required
def api_escalate(request_id):
    """Manual escalation."""
    data = request.get_json() or {}
    reason = data.get('reason', 'manual')
    escalate_to = data.get('escalate_to')

    try:
        result = _engine.escalate(
            request_id, reason=reason, actor_id=current_user.id,
            escalate_to_user_id=escalate_to,
        )
        return jsonify({'success': True, 'request': _serialize_request(result)})
    except (InvalidStateError, ApprovalError) as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.exception(f'Escalate failed: {e}')
        return jsonify({'success': False, 'error': 'Failed to escalate'}), 500


# ════════════════════════════════════════════
# User Queue
# ════════════════════════════════════════════

@approvals_bp.route('/api/my-queue', methods=['GET'])
@login_required
def api_my_queue():
    """Get pending decisions for current user."""
    entity_type = request.args.get('entity_type')
    items = _engine.get_pending_for_user(current_user.id, entity_type=entity_type)
    return jsonify({'queue': [_serialize_queue_item(r) for r in items]})


@approvals_bp.route('/api/my-queue/count', methods=['GET'])
@login_required
def api_my_queue_count():
    """Badge count for UI."""
    count = _engine.get_queue_count(current_user.id)
    return jsonify({'count': count})


@approvals_bp.route('/api/my-requests', methods=['GET'])
@login_required
def api_my_requests():
    """Requests submitted by current user."""
    from .repositories import RequestRepository
    rows = RequestRepository().list_requests(requested_by=current_user.id)
    return jsonify({'requests': [_serialize_request(r) for r in rows]})


# ════════════════════════════════════════════
# Flows (Admin)
# ════════════════════════════════════════════

@approvals_bp.route('/api/flows', methods=['GET'])
@login_required
def api_list_flows():
    """List all approval flows."""
    active_only = request.args.get('active_only', 'true').lower() == 'true'
    flows = _flow_repo.get_all_flows(active_only=active_only)
    return jsonify({'flows': flows})


@approvals_bp.route('/api/flows', methods=['POST'])
@login_required
def api_create_flow():
    """Create a new approval flow."""
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Admin access required'}), 403

    data = request.get_json()
    name = (data.get('name') or '').strip()
    slug = (data.get('slug') or '').strip()
    entity_type = (data.get('entity_type') or '').strip()

    if not all([name, slug, entity_type]):
        return jsonify({'success': False, 'error': 'name, slug, and entity_type are required'}), 400

    try:
        flow_id = _flow_repo.create_flow(
            name, slug, entity_type, current_user.id,
            description=data.get('description'),
            trigger_conditions=data.get('trigger_conditions'),
            priority=data.get('priority', 0),
            allow_parallel_steps=data.get('allow_parallel_steps', False),
            auto_approve_below=data.get('auto_approve_below'),
            auto_reject_after_hours=data.get('auto_reject_after_hours'),
        )
        return jsonify({'success': True, 'id': flow_id})
    except Exception as e:
        if 'unique' in str(e).lower():
            return jsonify({'success': False, 'error': 'Flow slug already exists'}), 409
        return safe_error_response(e)


@approvals_bp.route('/api/flows/<int:flow_id>', methods=['GET'])
@login_required
def api_get_flow(flow_id):
    """Get flow with steps."""
    flow = _flow_repo.get_flow_with_steps(flow_id)
    if not flow:
        return jsonify({'success': False, 'error': 'Flow not found'}), 404
    return jsonify(flow)


@approvals_bp.route('/api/flows/<int:flow_id>', methods=['PUT'])
@login_required
@handle_api_errors
def api_update_flow(flow_id):
    """Update a flow."""
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Admin access required'}), 403

    data = request.get_json()
    updated = _flow_repo.update_flow(flow_id, **data)
    if updated:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Flow not found'}), 404


@approvals_bp.route('/api/flows/<int:flow_id>', methods=['DELETE'])
@login_required
def api_delete_flow(flow_id):
    """Deactivate a flow (soft delete)."""
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Admin access required'}), 403

    if _flow_repo.deactivate_flow(flow_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Flow not found'}), 404


# ════════════════════════════════════════════
# Steps (Admin)
# ════════════════════════════════════════════

@approvals_bp.route('/api/flows/<int:flow_id>/steps', methods=['POST'])
@login_required
@handle_api_errors
def api_create_step(flow_id):
    """Add a step to a flow."""
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Admin access required'}), 403

    data = request.get_json()
    name = (data.get('name') or '').strip()
    approver_type = (data.get('approver_type') or '').strip()

    if not all([name, approver_type]):
        return jsonify({'success': False, 'error': 'name and approver_type are required'}), 400

    # Auto-calculate step_order
    existing_steps = _flow_repo.get_steps_for_flow(flow_id)
    step_order = data.get('step_order', len(existing_steps) + 1)

    step_id = _flow_repo.create_step(
        flow_id, name, step_order, approver_type,
        approver_user_id=data.get('approver_user_id'),
        approver_role_name=data.get('approver_role_name'),
        requires_all=data.get('requires_all', False),
        min_approvals=data.get('min_approvals', 1),
        skip_conditions=data.get('skip_conditions'),
        timeout_hours=data.get('timeout_hours'),
        escalation_step_id=data.get('escalation_step_id'),
        escalation_user_id=data.get('escalation_user_id'),
        notify_on_pending=data.get('notify_on_pending', True),
        notify_on_decision=data.get('notify_on_decision', True),
        reminder_after_hours=data.get('reminder_after_hours'),
    )
    return jsonify({'success': True, 'id': step_id})


@approvals_bp.route('/api/flows/<int:flow_id>/steps/<int:step_id>', methods=['PUT'])
@login_required
@handle_api_errors
def api_update_step(flow_id, step_id):
    """Update a step."""
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Admin access required'}), 403

    data = request.get_json()
    updated = _flow_repo.update_step(step_id, **data)
    if updated:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Step not found'}), 404


@approvals_bp.route('/api/flows/<int:flow_id>/steps/<int:step_id>', methods=['DELETE'])
@login_required
def api_delete_step(flow_id, step_id):
    """Remove a step."""
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Admin access required'}), 403

    if _flow_repo.delete_step(step_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Step not found'}), 404


@approvals_bp.route('/api/flows/<int:flow_id>/steps/reorder', methods=['PATCH'])
@login_required
def api_reorder_steps(flow_id):
    """Reorder steps."""
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Admin access required'}), 403

    data = request.get_json()
    step_ids = data.get('step_ids', [])
    if not step_ids:
        return jsonify({'success': False, 'error': 'step_ids required'}), 400

    _flow_repo.reorder_steps(flow_id, step_ids)
    return jsonify({'success': True})


# ════════════════════════════════════════════
# Delegations
# ════════════════════════════════════════════

@approvals_bp.route('/api/delegations', methods=['GET'])
@login_required
def api_list_delegations():
    """Get delegations for current user."""
    delegations = _delegation_repo.get_active_for_user(current_user.id)
    return jsonify({'delegations': delegations})


@approvals_bp.route('/api/delegations', methods=['POST'])
@login_required
@handle_api_errors
def api_create_delegation():
    """Create a new delegation."""
    data = request.get_json()
    delegate_id = data.get('delegate_id')
    starts_at = data.get('starts_at')
    ends_at = data.get('ends_at')

    if not all([delegate_id, starts_at, ends_at]):
        return jsonify({'success': False, 'error': 'delegate_id, starts_at, ends_at are required'}), 400

    delegation_id = _delegation_repo.create(
        current_user.id, int(delegate_id), starts_at, ends_at,
        reason=data.get('reason'),
        entity_type=data.get('entity_type'),
        flow_id=data.get('flow_id'),
    )
    return jsonify({'success': True, 'id': delegation_id})


@approvals_bp.route('/api/delegations/<int:delegation_id>', methods=['DELETE'])
@login_required
def api_delete_delegation(delegation_id):
    """Revoke a delegation."""
    if _delegation_repo.deactivate(delegation_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Delegation not found'}), 404


# ════════════════════════════════════════════
# Audit
# ════════════════════════════════════════════

@approvals_bp.route('/api/requests/<int:request_id>/audit', methods=['GET'])
@login_required
def api_request_audit(request_id):
    """Audit trail for a request."""
    audit = _audit_repo.get_for_request(request_id)
    return jsonify({'audit': [_serialize_audit(a) for a in audit]})


@approvals_bp.route('/api/audit', methods=['GET'])
@login_required
def api_global_audit():
    """Global audit log (admin only)."""
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Admin access required'}), 403

    limit = min(int(request.args.get('limit', 100)), 500)
    offset = int(request.args.get('offset', 0))
    action = request.args.get('action')
    actor_id = request.args.get('actor_id')

    audit = _audit_repo.get_global(limit=limit, offset=offset,
                                   action=action, actor_id=actor_id)
    return jsonify({'audit': [_serialize_audit(a) for a in audit]})


# ════════════════════════════════════════════
# Entity History
# ════════════════════════════════════════════

@approvals_bp.route('/api/entity/<entity_type>/<int:entity_id>/history', methods=['GET'])
@login_required
def api_entity_history(entity_type, entity_id):
    """Full approval history for an entity, including decisions."""
    from .repositories import DecisionRepository
    decision_repo = DecisionRepository()
    history = _engine.get_history_for_entity(entity_type, entity_id)
    result = []
    for r in history:
        item = _serialize_request(r)
        decisions = decision_repo.get_decisions_for_request(r['id'])
        item['decisions'] = [_serialize_decision(d) for d in decisions]
        result.append(item)
    return jsonify({'history': result})


# ════════════════════════════════════════════
# Serializers
# ════════════════════════════════════════════

def _serialize_request(r):
    """Serialize a request dict for JSON response."""
    if not r:
        return None
    return {
        'id': r['id'],
        'entity_type': r.get('entity_type'),
        'entity_id': r.get('entity_id'),
        'flow_id': r.get('flow_id'),
        'flow_name': r.get('flow_name'),
        'flow_slug': r.get('flow_slug'),
        'current_step_id': r.get('current_step_id'),
        'current_step_name': r.get('current_step_name'),
        'status': r.get('status'),
        'context_snapshot': r.get('context_snapshot'),
        'requested_by': {
            'id': r.get('requested_by'),
            'name': r.get('requested_by_name'),
            'email': r.get('requested_by_email'),
        },
        'requested_at': _dt(r.get('requested_at')),
        'resolved_at': _dt(r.get('resolved_at')),
        'resolution_note': r.get('resolution_note'),
        'priority': r.get('priority'),
        'due_by': _dt(r.get('due_by')),
        'created_at': _dt(r.get('created_at')),
        'updated_at': _dt(r.get('updated_at')),
    }


def _serialize_queue_item(r):
    """Serialize a queue item (request with waiting_hours)."""
    base = _serialize_request(r)
    ctx = r.get('context_snapshot') or {}
    base['title'] = ctx.get('title', f"{r.get('entity_type')}/{r.get('entity_id')}")
    base['amount'] = ctx.get('amount')
    base['waiting_hours'] = round(r.get('waiting_hours', 0), 1)
    return base


def _serialize_decision(d):
    return {
        'id': d['id'],
        'request_id': d.get('request_id'),
        'step_id': d.get('step_id'),
        'step_name': d.get('step_name'),
        'decided_by': {
            'id': d.get('decided_by'),
            'name': d.get('decided_by_name'),
            'email': d.get('decided_by_email'),
        },
        'decision': d.get('decision'),
        'comment': d.get('comment'),
        'conditions': d.get('conditions'),
        'delegated_to': {
            'id': d.get('delegated_to'),
            'name': d.get('delegated_to_name'),
        } if d.get('delegated_to') else None,
        'decided_at': _dt(d.get('decided_at')),
    }


def _serialize_step(s):
    return {
        'id': s['id'],
        'flow_id': s.get('flow_id'),
        'name': s.get('name'),
        'step_order': s.get('step_order'),
        'approver_type': s.get('approver_type'),
        'approver_user_id': s.get('approver_user_id'),
        'approver_role_name': s.get('approver_role_name'),
        'requires_all': s.get('requires_all'),
        'min_approvals': s.get('min_approvals'),
        'skip_conditions': s.get('skip_conditions'),
        'timeout_hours': s.get('timeout_hours'),
        'reminder_after_hours': s.get('reminder_after_hours'),
    }


def _serialize_audit(a):
    return {
        'id': a['id'],
        'request_id': a.get('request_id'),
        'action': a.get('action'),
        'actor_id': a.get('actor_id'),
        'actor_name': a.get('actor_name'),
        'actor_type': a.get('actor_type'),
        'details': a.get('details'),
        'created_at': _dt(a.get('created_at')),
    }


def _dt(val):
    """Format datetime for JSON."""
    if val is None:
        return None
    if isinstance(val, str):
        return val
    return val.isoformat()
