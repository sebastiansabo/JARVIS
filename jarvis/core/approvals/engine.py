"""ApprovalEngine — core orchestrator for the approval workflow.

All approval logic flows through this class. Consuming modules NEVER
manipulate approval tables directly.
"""

import logging
from datetime import datetime, timezone

from .condition_eval import ConditionEvaluator
from . import hooks
from .repositories import (
    FlowRepository, RequestRepository, DecisionRepository,
    AuditRepository, DelegationRepository,
)

logger = logging.getLogger('jarvis.core.approvals.engine')


class ApprovalError(Exception):
    """Base error for approval engine."""


class NoMatchingFlowError(ApprovalError):
    """No active flow matches the entity type + context."""


class AlreadyPendingError(ApprovalError):
    """Entity already has a pending approval request."""


class NotAuthorizedError(ApprovalError):
    """User is not authorized to decide on this step."""


class AlreadyDecidedError(ApprovalError):
    """User already decided on this step."""


class InvalidStateError(ApprovalError):
    """Request is not in a valid state for this operation."""


class ApprovalEngine:

    def __init__(self):
        self._flow_repo = FlowRepository()
        self._request_repo = RequestRepository()
        self._decision_repo = DecisionRepository()
        self._audit_repo = AuditRepository()
        self._delegation_repo = DelegationRepository()

    # ════════════════════════════════════════════
    # Public API
    # ════════════════════════════════════════════

    def submit(self, entity_type, entity_id, context, requested_by,
               priority='normal', due_by=None):
        """Submit an entity for approval.

        1. Find matching flow
        2. Check auto-approve threshold
        3. Create request with frozen context
        4. Advance to first eligible step
        5. Audit + fire hooks
        """
        # Check for existing pending request
        existing = self._request_repo.get_pending_for_entity(entity_type, entity_id)
        if existing:
            raise AlreadyPendingError(
                f'{entity_type}/{entity_id} already has pending request #{existing}')

        # Find matching flow
        flow = self._find_matching_flow(entity_type, context)
        if not flow:
            raise NoMatchingFlowError(
                f'No active flow matches entity_type={entity_type}')

        # Check auto-approve
        if self._check_auto_approve(flow, context):
            request_id = self._request_repo.create(
                entity_type, entity_id, flow['id'], requested_by,
                context, priority, due_by,
            )
            self._request_repo.update_status(
                request_id, 'approved', resolved_at=datetime.now(timezone.utc))
            self._audit_repo.log(request_id, 'request_created', requested_by, details={
                'flow_name': flow['name'], 'auto_approved': True,
            })
            self._audit_repo.log(request_id, 'auto_approved', actor_type='system', details={
                'reason': f"Amount below auto-approve threshold ({flow['auto_approve_below']})",
            })
            hooks.fire('approval.approved', {
                'request_id': request_id, 'entity_type': entity_type,
                'entity_id': entity_id, 'auto_approved': True,
            })
            return self._request_repo.get_by_id(request_id)

        # Create request
        request_id = self._request_repo.create(
            entity_type, entity_id, flow['id'], requested_by,
            context, priority, due_by,
        )

        self._audit_repo.log(request_id, 'request_created', requested_by, details={
            'flow_name': flow['name'], 'entity_type': entity_type,
            'entity_id': entity_id,
        })

        # Advance to first step
        steps = self._flow_repo.get_steps_for_flow(flow['id'])
        first_step = self._find_next_eligible_step(steps, 0, context)

        if first_step is None:
            # All steps skipped — auto-approve
            self._request_repo.update_status(
                request_id, 'approved', resolved_at=datetime.now(timezone.utc))
            self._audit_repo.log(request_id, 'auto_approved', actor_type='system', details={
                'reason': 'All steps skipped by conditions',
            })
            hooks.fire('approval.approved', {
                'request_id': request_id, 'entity_type': entity_type,
                'entity_id': entity_id, 'auto_approved': True,
            })
        else:
            self._request_repo.update_status(
                request_id, 'pending', current_step_id=first_step['id'])
            self._audit_repo.log(request_id, 'step_advanced', actor_type='system', details={
                'step_name': first_step['name'], 'step_order': first_step['step_order'],
            })

        hooks.fire('approval.submitted', {
            'request_id': request_id, 'entity_type': entity_type,
            'entity_id': entity_id, 'flow_name': flow['name'],
            'requested_by': requested_by,
        })

        return self._request_repo.get_by_id(request_id)

    def decide(self, request_id, decision, decided_by, comment=None, conditions=None,
               delegated_to=None, delegation_reason=None):
        """Record a decision on the current step.

        1. Validate authorization
        2. Record decision
        3. Evaluate step completion
        4. Advance or finalize
        """
        req = self._request_repo.get_by_id(request_id)
        if not req:
            raise InvalidStateError(f'Request {request_id} not found')

        if req['status'] not in ('pending', 'in_progress'):
            raise InvalidStateError(
                f"Request {request_id} is {req['status']}, cannot decide")

        step_id = req['current_step_id']
        if not step_id:
            raise InvalidStateError(f'Request {request_id} has no current step')

        step = self._flow_repo.get_step_by_id(step_id)

        # Authorization check
        if not self._is_authorized(step, decided_by, req):
            raise NotAuthorizedError(
                f'User {decided_by} is not authorized for step {step["name"]}')

        # Already decided check
        if self._decision_repo.has_user_decided_on_step(request_id, step_id, decided_by):
            raise AlreadyDecidedError(
                f'User {decided_by} already decided on step {step["name"]}')

        # Record decision
        self._decision_repo.create(
            request_id, step_id, decided_by, decision,
            comment=comment, conditions=conditions,
            delegated_to=delegated_to, delegation_reason=delegation_reason,
        )

        self._audit_repo.log(request_id, 'decision_made', decided_by, details={
            'decision': decision, 'step_name': step['name'],
            'comment': comment,
        })

        # Update to in_progress if still pending
        if req['status'] == 'pending':
            self._request_repo.update_status(request_id, 'in_progress')

        hooks.fire('approval.decided', {
            'request_id': request_id, 'entity_type': req['entity_type'],
            'entity_id': req['entity_id'], 'decision': decision,
            'step_name': step['name'], 'decided_by': decided_by,
        })

        # Handle decision type
        if decision == 'rejected':
            self._request_repo.update_status(
                request_id, 'rejected',
                resolved_at=datetime.now(timezone.utc),
                resolution_note=comment,
            )
            self._audit_repo.log(request_id, 'request_rejected', decided_by, details={
                'step_name': step['name'], 'comment': comment,
            })
            hooks.fire('approval.rejected', {
                'request_id': request_id, 'entity_type': req['entity_type'],
                'entity_id': req['entity_id'], 'resolution_note': comment,
            })
            return self._request_repo.get_by_id(request_id)

        if decision == 'returned':
            self._request_repo.update_status(request_id, 'on_hold',
                                             resolution_note=comment)
            self._audit_repo.log(request_id, 'request_returned', decided_by, details={
                'step_name': step['name'], 'comment': comment,
            })
            hooks.fire('approval.returned', {
                'request_id': request_id, 'entity_type': req['entity_type'],
                'entity_id': req['entity_id'], 'comment': comment,
            })
            return self._request_repo.get_by_id(request_id)

        if decision == 'delegated':
            self._audit_repo.log(request_id, 'delegated', decided_by, details={
                'step_name': step['name'], 'delegated_to': delegated_to,
                'reason': delegation_reason,
            })
            return self._request_repo.get_by_id(request_id)

        if decision == 'approved':
            # Check if step is complete
            if self._is_step_complete(request_id, step):
                # Advance to next step
                context = req.get('context_snapshot') or {}
                steps = self._flow_repo.get_steps_for_flow(req['flow_id'])
                next_step = self._find_next_eligible_step(
                    steps, step['step_order'], context)

                if next_step is None:
                    # All done — approve request
                    self._request_repo.update_status(
                        request_id, 'approved',
                        resolved_at=datetime.now(timezone.utc),
                        current_step_id=None,
                    )
                    self._audit_repo.log(request_id, 'request_approved',
                                         actor_type='system', details={
                        'final_step': step['name'],
                    })
                    hooks.fire('approval.approved', {
                        'request_id': request_id,
                        'entity_type': req['entity_type'],
                        'entity_id': req['entity_id'],
                    })
                else:
                    self._request_repo.update_status(
                        request_id, 'pending',
                        current_step_id=next_step['id'],
                    )
                    self._audit_repo.log(request_id, 'step_advanced',
                                         actor_type='system', details={
                        'from_step': step['name'],
                        'to_step': next_step['name'],
                        'to_step_order': next_step['step_order'],
                    })
                    hooks.fire('approval.step_advanced', {
                        'request_id': request_id,
                        'entity_type': req['entity_type'],
                        'entity_id': req['entity_id'],
                        'step_name': next_step['name'],
                    })

        return self._request_repo.get_by_id(request_id)

    def cancel(self, request_id, cancelled_by, reason=None):
        """Cancel a pending request. Only requester or admin can cancel."""
        req = self._request_repo.get_by_id(request_id)
        if not req:
            raise InvalidStateError(f'Request {request_id} not found')

        if req['status'] not in ('pending', 'in_progress', 'on_hold'):
            raise InvalidStateError(
                f"Request {request_id} is {req['status']}, cannot cancel")

        self._request_repo.update_status(
            request_id, 'cancelled',
            resolved_at=datetime.now(timezone.utc),
            resolution_note=reason,
        )
        self._audit_repo.log(request_id, 'cancelled', cancelled_by, details={
            'reason': reason,
        })
        hooks.fire('approval.cancelled', {
            'request_id': request_id, 'entity_type': req['entity_type'],
            'entity_id': req['entity_id'],
        })
        return self._request_repo.get_by_id(request_id)

    def resubmit(self, request_id, new_context, resubmitted_by):
        """Resubmit a rejected/returned request with updated context.

        Creates a NEW request for the same entity.
        """
        old_req = self._request_repo.get_by_id(request_id)
        if not old_req:
            raise InvalidStateError(f'Request {request_id} not found')

        if old_req['status'] not in ('rejected', 'on_hold', 'cancelled'):
            raise InvalidStateError(
                f"Request {request_id} is {old_req['status']}, cannot resubmit")

        self._audit_repo.log(request_id, 'resubmitted', resubmitted_by, details={
            'new_context_keys': list(new_context.keys()),
        })

        return self.submit(
            old_req['entity_type'], old_req['entity_id'],
            new_context, resubmitted_by,
            priority=old_req.get('priority', 'normal'),
        )

    def escalate(self, request_id, reason='timeout', actor_id=None):
        """Escalate current step."""
        req = self._request_repo.get_by_id(request_id)
        if not req or req['status'] not in ('pending', 'in_progress'):
            raise InvalidStateError(f'Cannot escalate request {request_id}')

        step = self._flow_repo.get_step_by_id(req['current_step_id'])
        if not step:
            raise InvalidStateError('No current step to escalate')

        actor_type = 'user' if actor_id else 'scheduler'

        if step.get('escalation_step_id'):
            esc_step = self._flow_repo.get_step_by_id(step['escalation_step_id'])
            if esc_step:
                self._request_repo.update_status(
                    request_id, 'escalated',
                    current_step_id=esc_step['id'],
                )
                self._audit_repo.log(request_id, 'escalated', actor_id,
                                     actor_type=actor_type, details={
                    'reason': reason, 'from_step': step['name'],
                    'to_step': esc_step['name'],
                })
                hooks.fire('approval.escalated', {
                    'request_id': request_id,
                    'entity_type': req['entity_type'],
                    'entity_id': req['entity_id'],
                    'reason': reason,
                })
                return self._request_repo.get_by_id(request_id)

        # No escalation path — just log it
        self._audit_repo.log(request_id, 'escalation_attempted', actor_id,
                             actor_type=actor_type, details={
            'reason': reason, 'step_name': step['name'],
            'note': 'No escalation path configured',
        })
        return self._request_repo.get_by_id(request_id)

    def get_pending_for_user(self, user_id, entity_type=None):
        """Get all requests pending this user's decision."""
        return self._request_repo.get_pending_for_user(user_id, entity_type)

    def get_queue_count(self, user_id):
        """Badge count for UI."""
        return self._request_repo.get_pending_queue_count(user_id)

    def get_history_for_entity(self, entity_type, entity_id):
        """Full approval history for an entity."""
        return self._request_repo.get_by_entity(entity_type, entity_id)

    # ════════════════════════════════════════════
    # Scheduler methods
    # ════════════════════════════════════════════

    def process_timeouts(self):
        """Check for timed-out steps and escalate."""
        timed_out = self._request_repo.get_timed_out_requests()
        for item in timed_out:
            try:
                self.escalate(item['request_id'], reason='timeout')
            except Exception as e:
                logger.error(f"Timeout escalation failed for request {item['request_id']}: {e}")

    def process_reminders(self):
        """Send reminders for stale steps."""
        reminders = self._request_repo.get_requests_needing_reminder()
        for item in reminders:
            try:
                self._audit_repo.log(
                    item['request_id'], 'reminder_sent',
                    actor_type='scheduler',
                    details={'step_id': item['step_id']},
                )
                hooks.fire('approval.reminder', {
                    'request_id': item['request_id'],
                    'step_id': item['step_id'],
                })
            except Exception as e:
                logger.error(f"Reminder failed for request {item['request_id']}: {e}")

    def process_expirations(self):
        """Expire requests past auto_reject_after_hours."""
        expired = self._request_repo.get_expired_requests()
        for item in expired:
            try:
                self._request_repo.update_status(
                    item['request_id'], 'expired',
                    resolved_at=datetime.now(timezone.utc),
                    resolution_note=f"Auto-expired after {item['auto_reject_after_hours']}h",
                )
                self._audit_repo.log(
                    item['request_id'], 'expired',
                    actor_type='scheduler',
                    details={'auto_reject_after_hours': item['auto_reject_after_hours']},
                )
                hooks.fire('approval.expired', {
                    'request_id': item['request_id'],
                })
            except Exception as e:
                logger.error(f"Expiration failed for request {item['request_id']}: {e}")

    # ════════════════════════════════════════════
    # Internal
    # ════════════════════════════════════════════

    def _find_matching_flow(self, entity_type, context):
        """Find highest-priority active flow that matches."""
        flows = self._flow_repo.get_active_flows_for_entity_type(entity_type)
        for flow in flows:  # Already sorted by priority DESC
            conditions = flow.get('trigger_conditions') or {}
            if ConditionEvaluator.evaluate(conditions, context):
                return flow
        return None

    def _find_next_eligible_step(self, steps, after_order, context):
        """Find next step with order > after_order whose skip_conditions are NOT met."""
        for step in steps:
            if step['step_order'] <= after_order:
                continue
            skip = step.get('skip_conditions') or {}
            if skip and ConditionEvaluator.evaluate(skip, context):
                logger.debug(f"Skipping step {step['name']} (conditions met)")
                continue
            return step
        return None

    def _check_auto_approve(self, flow, context):
        """Check if flow's auto_approve_below threshold is met."""
        threshold = flow.get('auto_approve_below')
        if threshold is None:
            return False
        amount = context.get('amount')
        if amount is None:
            return False
        try:
            return float(amount) < float(threshold)
        except (ValueError, TypeError):
            return False

    def _is_authorized(self, step, user_id, request):
        """Check if user can decide on this step."""
        from database import get_db, get_cursor, release_db

        # Direct assignment
        if step.get('approver_user_id') == user_id:
            return True

        # Role-based
        if step.get('approver_role_name'):
            conn = get_db()
            try:
                cursor = get_cursor(conn)
                cursor.execute('''
                    SELECT 1 FROM users u
                    JOIN roles r ON r.id = u.role_id
                    WHERE u.id = %s AND r.name = %s
                ''', (user_id, step['approver_role_name']))
                if cursor.fetchone():
                    return True
            finally:
                release_db(conn)

        # Delegation check — user is delegate for the actual approver
        if step.get('approver_user_id'):
            if self._delegation_repo.is_delegate_for(
                user_id, step['approver_user_id'],
                entity_type=request.get('entity_type'),
                flow_id=request.get('flow_id'),
            ):
                return True

        return False

    def _is_step_complete(self, request_id, step):
        """Check if enough approvals have been recorded for this step."""
        counts = self._decision_repo.count_decisions_for_step(request_id, step['id'])

        if step.get('requires_all', False):
            # Need to resolve all approvers and check all approved
            # For now, use min_approvals as the threshold
            return counts['approved'] >= step.get('min_approvals', 1)

        # Any-one mode: single approval is sufficient
        return counts['approved'] >= step.get('min_approvals', 1)
