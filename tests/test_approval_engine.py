"""Unit tests for the Universal Approval Engine.

Tests:
- ConditionEvaluator: all operators, edge cases
- ApprovalEngine: submit, decide, cancel, resubmit, escalate
- Full flow: submit → approve step 1 → approve step 2 → approved
"""

import sys
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from core.approvals.condition_eval import ConditionEvaluator
from core.approvals import hooks


# ═══════════════════════════════════════════════
# ConditionEvaluator Tests
# ═══════════════════════════════════════════════

class TestConditionEvaluator:

    def test_empty_conditions_match_everything(self):
        assert ConditionEvaluator.evaluate({}, {'anything': 123}) is True

    def test_none_conditions_match_everything(self):
        assert ConditionEvaluator.evaluate(None, {'anything': 123}) is True

    def test_exact_equality(self):
        assert ConditionEvaluator.evaluate(
            {'type': 'campaign'}, {'type': 'campaign'}) is True
        assert ConditionEvaluator.evaluate(
            {'type': 'campaign'}, {'type': 'organic'}) is False

    def test_exact_equality_missing_key(self):
        assert ConditionEvaluator.evaluate(
            {'type': 'campaign'}, {'other': 'val'}) is False

    def test_gte(self):
        assert ConditionEvaluator.evaluate(
            {'budget_gte': 5000}, {'budget': 5000}) is True
        assert ConditionEvaluator.evaluate(
            {'budget_gte': 5000}, {'budget': 10000}) is True
        assert ConditionEvaluator.evaluate(
            {'budget_gte': 5000}, {'budget': 4999}) is False

    def test_gt(self):
        assert ConditionEvaluator.evaluate(
            {'budget_gt': 5000}, {'budget': 5001}) is True
        assert ConditionEvaluator.evaluate(
            {'budget_gt': 5000}, {'budget': 5000}) is False

    def test_lte(self):
        assert ConditionEvaluator.evaluate(
            {'budget_lte': 5000}, {'budget': 5000}) is True
        assert ConditionEvaluator.evaluate(
            {'budget_lte': 5000}, {'budget': 3000}) is True
        assert ConditionEvaluator.evaluate(
            {'budget_lte': 5000}, {'budget': 5001}) is False

    def test_lt(self):
        assert ConditionEvaluator.evaluate(
            {'budget_lt': 5000}, {'budget': 4999}) is True
        assert ConditionEvaluator.evaluate(
            {'budget_lt': 5000}, {'budget': 5000}) is False

    def test_eq(self):
        assert ConditionEvaluator.evaluate(
            {'status_eq': 'active'}, {'status': 'active'}) is True
        assert ConditionEvaluator.evaluate(
            {'status_eq': 'active'}, {'status': 'draft'}) is False

    def test_neq(self):
        assert ConditionEvaluator.evaluate(
            {'status_neq': 'draft'}, {'status': 'active'}) is True
        assert ConditionEvaluator.evaluate(
            {'status_neq': 'draft'}, {'status': 'draft'}) is False

    def test_in(self):
        assert ConditionEvaluator.evaluate(
            {'channel_in': ['meta', 'google']}, {'channel': 'meta'}) is True
        assert ConditionEvaluator.evaluate(
            {'channel_in': ['meta', 'google']}, {'channel': 'tiktok'}) is False

    def test_not_in(self):
        assert ConditionEvaluator.evaluate(
            {'channel_not_in': ['meta', 'google']}, {'channel': 'tiktok'}) is True
        assert ConditionEvaluator.evaluate(
            {'channel_not_in': ['meta', 'google']}, {'channel': 'meta'}) is False

    def test_exists_true(self):
        assert ConditionEvaluator.evaluate(
            {'external_agency_exists': True}, {'external_agency': 'MediaCom'}) is True
        assert ConditionEvaluator.evaluate(
            {'external_agency_exists': True}, {'other': 'val'}) is False

    def test_exists_false(self):
        assert ConditionEvaluator.evaluate(
            {'external_agency_exists': False}, {'other': 'val'}) is True
        assert ConditionEvaluator.evaluate(
            {'external_agency_exists': False}, {'external_agency': 'X'}) is False

    def test_contains(self):
        assert ConditionEvaluator.evaluate(
            {'description_contains': 'urgent'}, {'description': 'This is urgent!'}) is True
        assert ConditionEvaluator.evaluate(
            {'description_contains': 'urgent'}, {'description': 'Normal request'}) is False

    def test_multiple_conditions_and(self):
        conditions = {'budget_gte': 5000, 'type': 'campaign', 'channel_in': ['meta', 'google']}
        ctx_match = {'budget': 10000, 'type': 'campaign', 'channel': 'meta'}
        ctx_no_match = {'budget': 10000, 'type': 'campaign', 'channel': 'tiktok'}
        assert ConditionEvaluator.evaluate(conditions, ctx_match) is True
        assert ConditionEvaluator.evaluate(conditions, ctx_no_match) is False

    def test_numeric_comparison_with_strings(self):
        # Should handle string numbers
        assert ConditionEvaluator.evaluate(
            {'amount_gte': 100}, {'amount': '200'}) is True

    def test_numeric_comparison_with_none(self):
        assert ConditionEvaluator.evaluate(
            {'amount_gte': 100}, {'amount': None}) is False

    def test_numeric_comparison_missing_key(self):
        assert ConditionEvaluator.evaluate(
            {'amount_gte': 100}, {}) is False

    def test_in_with_non_list_value(self):
        assert ConditionEvaluator.evaluate(
            {'channel_in': 'not-a-list'}, {'channel': 'meta'}) is False

    def test_contains_with_none_actual(self):
        assert ConditionEvaluator.evaluate(
            {'desc_contains': 'test'}, {'desc': None}) is False

    def test_range_conditions(self):
        """Test budget_gte + budget_lt together (range)."""
        conditions = {'budget_gte': 1000, 'budget_lt': 10000}
        assert ConditionEvaluator.evaluate(conditions, {'budget': 5000}) is True
        assert ConditionEvaluator.evaluate(conditions, {'budget': 500}) is False
        assert ConditionEvaluator.evaluate(conditions, {'budget': 10000}) is False
        assert ConditionEvaluator.evaluate(conditions, {'budget': 1000}) is True


# ═══════════════════════════════════════════════
# Hooks Tests
# ═══════════════════════════════════════════════

class TestHooks:

    def setup_method(self):
        hooks.clear()

    def test_on_and_fire(self):
        called = []
        hooks.on('test.event', lambda p: called.append(p))
        hooks.fire('test.event', {'key': 'val'})
        assert len(called) == 1
        assert called[0] == {'key': 'val'}

    def test_multiple_handlers(self):
        called = []
        hooks.on('test.event', lambda p: called.append('a'))
        hooks.on('test.event', lambda p: called.append('b'))
        hooks.fire('test.event', {})
        assert called == ['a', 'b']

    def test_fire_unknown_event(self):
        # Should not raise
        hooks.fire('unknown.event', {'data': 1})

    def test_handler_error_doesnt_stop_others(self):
        called = []
        hooks.on('test.event', lambda p: (_ for _ in ()).throw(ValueError("oops")))
        hooks.on('test.event', lambda p: called.append('ok'))
        hooks.fire('test.event', {})
        # Second handler should still be called despite first raising
        # (the error is in a generator, so it won't actually raise here)
        # Let's use a more direct approach:
        hooks.clear()
        def bad_handler(p):
            raise RuntimeError("boom")
        called2 = []
        hooks.on('test.event', bad_handler)
        hooks.on('test.event', lambda p: called2.append('ok'))
        hooks.fire('test.event', {})
        assert called2 == ['ok']

    def test_clear_specific(self):
        hooks.on('a', lambda p: None)
        hooks.on('b', lambda p: None)
        hooks.clear('a')
        assert 'a' not in hooks._registry
        assert 'b' in hooks._registry

    def test_clear_all(self):
        hooks.on('a', lambda p: None)
        hooks.on('b', lambda p: None)
        hooks.clear()
        assert len(hooks._registry) == 0


# ═══════════════════════════════════════════════
# ApprovalEngine Tests
# ═══════════════════════════════════════════════

def _make_engine():
    """Create an engine with mocked repositories."""
    from core.approvals.engine import ApprovalEngine
    engine = ApprovalEngine()
    engine._flow_repo = MagicMock()
    engine._request_repo = MagicMock()
    engine._decision_repo = MagicMock()
    engine._audit_repo = MagicMock()
    engine._delegation_repo = MagicMock()
    return engine


class TestEngineSubmit:

    def setup_method(self):
        hooks.clear()

    def test_submit_creates_request_and_advances(self):
        engine = _make_engine()
        flow = {'id': 1, 'name': 'Test Flow', 'auto_approve_below': None,
                'trigger_conditions': {}}
        steps = [
            {'id': 10, 'name': 'Step 1', 'step_order': 1, 'skip_conditions': {}},
        ]
        engine._request_repo.get_pending_for_entity.return_value = None
        engine._flow_repo.get_active_flows_for_entity_type.return_value = [flow]
        engine._request_repo.create.return_value = 100
        engine._flow_repo.get_steps_for_flow.return_value = steps
        engine._request_repo.get_by_id.return_value = {
            'id': 100, 'entity_type': 'invoice', 'entity_id': 1,
            'flow_id': 1, 'status': 'pending', 'current_step_id': 10,
        }

        result = engine.submit('invoice', 1, {'amount': 5000}, requested_by=1)

        engine._request_repo.create.assert_called_once()
        engine._request_repo.update_status.assert_called()
        engine._audit_repo.log.assert_called()
        assert result['id'] == 100

    def test_submit_already_pending_raises(self):
        engine = _make_engine()
        engine._request_repo.get_pending_for_entity.return_value = 99

        from core.approvals.engine import AlreadyPendingError
        with pytest.raises(AlreadyPendingError):
            engine.submit('invoice', 1, {}, requested_by=1)

    def test_submit_no_matching_flow_raises(self):
        engine = _make_engine()
        engine._request_repo.get_pending_for_entity.return_value = None
        engine._flow_repo.get_active_flows_for_entity_type.return_value = []

        from core.approvals.engine import NoMatchingFlowError
        with pytest.raises(NoMatchingFlowError):
            engine.submit('invoice', 1, {}, requested_by=1)

    def test_submit_auto_approve(self):
        engine = _make_engine()
        flow = {'id': 1, 'name': 'Quick', 'auto_approve_below': 500,
                'trigger_conditions': {}}
        engine._request_repo.get_pending_for_entity.return_value = None
        engine._flow_repo.get_active_flows_for_entity_type.return_value = [flow]
        engine._request_repo.create.return_value = 100
        engine._request_repo.get_by_id.return_value = {
            'id': 100, 'status': 'approved', 'entity_type': 'invoice', 'entity_id': 1,
        }

        fired = []
        hooks.on('approval.approved', lambda p: fired.append(p))

        result = engine.submit('invoice', 1, {'amount': 200}, requested_by=1)

        # Should auto-approve (200 < 500)
        # Verify update_status was called with 'approved' and a resolved_at datetime
        calls = engine._request_repo.update_status.call_args_list
        approved_call = [c for c in calls if c[0][1] == 'approved']
        assert len(approved_call) == 1
        assert 'resolved_at' in approved_call[0][1] if len(approved_call[0][0]) <= 2 else True
        assert len(fired) == 1
        assert fired[0]['auto_approved'] is True

    def test_submit_flow_matching_uses_conditions(self):
        engine = _make_engine()
        flow_high = {'id': 1, 'name': 'High Budget', 'auto_approve_below': None,
                     'trigger_conditions': {'amount_gte': 10000}}
        flow_low = {'id': 2, 'name': 'Low Budget', 'auto_approve_below': None,
                    'trigger_conditions': {}}
        engine._request_repo.get_pending_for_entity.return_value = None
        engine._flow_repo.get_active_flows_for_entity_type.return_value = [flow_high, flow_low]
        engine._request_repo.create.return_value = 100
        engine._flow_repo.get_steps_for_flow.return_value = [
            {'id': 10, 'name': 'S1', 'step_order': 1, 'skip_conditions': {}},
        ]
        engine._request_repo.get_by_id.return_value = {'id': 100, 'status': 'pending'}

        # amount=5000 doesn't match flow_high (gte 10000), should fall to flow_low
        engine.submit('invoice', 1, {'amount': 5000}, requested_by=1)
        engine._request_repo.create.assert_called_once()
        # Verify flow_id=2 was used (flow_low)
        args = engine._request_repo.create.call_args
        assert args[0][2] == 2  # flow_id parameter

    def test_submit_skips_steps_with_met_conditions(self):
        engine = _make_engine()
        flow = {'id': 1, 'name': 'Test', 'auto_approve_below': None,
                'trigger_conditions': {}}
        steps = [
            {'id': 10, 'name': 'CEO Override', 'step_order': 1,
             'skip_conditions': {'amount_lt': 10000}},
            {'id': 11, 'name': 'Finance', 'step_order': 2, 'skip_conditions': {}},
        ]
        engine._request_repo.get_pending_for_entity.return_value = None
        engine._flow_repo.get_active_flows_for_entity_type.return_value = [flow]
        engine._request_repo.create.return_value = 100
        engine._flow_repo.get_steps_for_flow.return_value = steps
        engine._request_repo.get_by_id.return_value = {'id': 100, 'status': 'pending'}

        engine.submit('invoice', 1, {'amount': 5000}, requested_by=1)

        # Step 1 should be skipped (5000 < 10000), should advance to step 2
        update_calls = engine._request_repo.update_status.call_args_list
        # Find the call that sets current_step_id
        step_ids_set = [c.kwargs.get('current_step_id') for c in update_calls if 'current_step_id' in c.kwargs]
        assert 11 in step_ids_set  # Should be on step 2 (Finance)


class TestEngineDecide:

    def setup_method(self):
        hooks.clear()

    def _make_req(self, status='pending', step_id=10, flow_id=1):
        return {
            'id': 100, 'entity_type': 'invoice', 'entity_id': 1,
            'flow_id': flow_id, 'current_step_id': step_id,
            'status': status, 'context_snapshot': {'amount': 5000},
            'requested_by': 2,
        }

    def _make_step(self, step_id=10, requires_all=False, min_approvals=1):
        return {
            'id': step_id, 'name': 'Test Step', 'step_order': 1,
            'approver_type': 'specific_user', 'approver_user_id': 1,
            'approver_role_name': None, 'requires_all': requires_all,
            'min_approvals': min_approvals,
        }

    def test_approve_single_step_flow(self):
        engine = _make_engine()
        req = self._make_req()
        step = self._make_step()
        engine._request_repo.get_by_id.return_value = req
        engine._flow_repo.get_step_by_id.return_value = step
        engine._decision_repo.has_user_decided_on_step.return_value = False
        engine._decision_repo.count_decisions_for_step.return_value = {
            'total': 1, 'approved': 1, 'rejected': 0, 'returned': 0, 'abstained': 0,
        }
        engine._flow_repo.get_steps_for_flow.return_value = [step]  # Only 1 step
        engine._delegation_repo.is_delegate_for.return_value = False

        # After approval, return approved request
        engine._request_repo.get_by_id.side_effect = [
            req,  # First call in decide()
            {**req, 'status': 'approved'},  # Return after update
        ]

        fired = []
        hooks.on('approval.approved', lambda p: fired.append(p))

        result = engine.decide(100, 'approved', decided_by=1)

        engine._decision_repo.create.assert_called_once()
        assert len(fired) == 1

    def test_reject_stops_flow(self):
        engine = _make_engine()
        req = self._make_req()
        step = self._make_step()
        engine._request_repo.get_by_id.return_value = req
        engine._flow_repo.get_step_by_id.return_value = step
        engine._decision_repo.has_user_decided_on_step.return_value = False
        engine._delegation_repo.is_delegate_for.return_value = False

        fired = []
        hooks.on('approval.rejected', lambda p: fired.append(p))

        engine.decide(100, 'rejected', decided_by=1, comment='Budget too high')

        # Verify rejected status was set
        calls = engine._request_repo.update_status.call_args_list
        rejected_call = [c for c in calls if len(c[0]) >= 2 and c[0][1] == 'rejected']
        assert len(rejected_call) == 1
        assert rejected_call[0][1]['resolution_note'] == 'Budget too high'
        assert len(fired) == 1

    def test_return_puts_on_hold(self):
        engine = _make_engine()
        req = self._make_req()
        step = self._make_step()
        engine._request_repo.get_by_id.return_value = req
        engine._flow_repo.get_step_by_id.return_value = step
        engine._decision_repo.has_user_decided_on_step.return_value = False
        engine._delegation_repo.is_delegate_for.return_value = False

        engine.decide(100, 'returned', decided_by=1, comment='Need more info')

        engine._request_repo.update_status.assert_any_call(
            100, 'on_hold', resolution_note='Need more info')

    def test_unauthorized_user_raises(self):
        engine = _make_engine()
        req = self._make_req()
        step = self._make_step(step_id=10)
        step['approver_user_id'] = 99  # Different user
        step['approver_role_name'] = None
        engine._request_repo.get_by_id.return_value = req
        engine._flow_repo.get_step_by_id.return_value = step
        engine._delegation_repo.is_delegate_for.return_value = False

        # Mock the role check to return no match
        with patch('database.get_db') as mock_gdb, \
             patch('database.get_cursor') as mock_gc, \
             patch('database.release_db'):
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_gdb.return_value = mock_conn
            mock_gc.return_value = mock_cursor
            mock_cursor.fetchone.return_value = None

            from core.approvals.engine import NotAuthorizedError
            with pytest.raises(NotAuthorizedError):
                engine.decide(100, 'approved', decided_by=1)

    def test_already_decided_raises(self):
        engine = _make_engine()
        req = self._make_req()
        step = self._make_step()
        engine._request_repo.get_by_id.return_value = req
        engine._flow_repo.get_step_by_id.return_value = step
        engine._decision_repo.has_user_decided_on_step.return_value = True

        from core.approvals.engine import AlreadyDecidedError
        with pytest.raises(AlreadyDecidedError):
            engine.decide(100, 'approved', decided_by=1)

    def test_decide_on_wrong_status_raises(self):
        engine = _make_engine()
        req = self._make_req(status='approved')
        engine._request_repo.get_by_id.return_value = req

        from core.approvals.engine import InvalidStateError
        with pytest.raises(InvalidStateError):
            engine.decide(100, 'approved', decided_by=1)

    def test_advance_to_next_step(self):
        engine = _make_engine()
        req = self._make_req(step_id=10)
        step1 = self._make_step(step_id=10)
        step2 = {'id': 11, 'name': 'Step 2', 'step_order': 2, 'skip_conditions': {},
                 'approver_type': 'role', 'approver_role_name': 'Manager'}
        engine._request_repo.get_by_id.return_value = req
        engine._flow_repo.get_step_by_id.return_value = step1
        engine._decision_repo.has_user_decided_on_step.return_value = False
        engine._decision_repo.count_decisions_for_step.return_value = {
            'total': 1, 'approved': 1, 'rejected': 0, 'returned': 0, 'abstained': 0,
        }
        engine._flow_repo.get_steps_for_flow.return_value = [step1, step2]
        engine._delegation_repo.is_delegate_for.return_value = False

        fired = []
        hooks.on('approval.step_advanced', lambda p: fired.append(p))

        engine.decide(100, 'approved', decided_by=1)

        # Should advance to step 2
        update_calls = engine._request_repo.update_status.call_args_list
        step_ids = [c.kwargs.get('current_step_id') for c in update_calls if 'current_step_id' in c.kwargs]
        assert 11 in step_ids
        assert len(fired) == 1


class TestEngineCancel:

    def test_cancel_pending(self):
        engine = _make_engine()
        req = {'id': 100, 'entity_type': 'invoice', 'entity_id': 1,
               'status': 'pending', 'requested_by': 1}
        engine._request_repo.get_by_id.return_value = req

        engine.cancel(100, cancelled_by=1, reason='Changed my mind')

        engine._request_repo.update_status.assert_called_once()
        args = engine._request_repo.update_status.call_args
        assert args[0][1] == 'cancelled'

    def test_cancel_already_approved_raises(self):
        engine = _make_engine()
        req = {'id': 100, 'status': 'approved'}
        engine._request_repo.get_by_id.return_value = req

        from core.approvals.engine import InvalidStateError
        with pytest.raises(InvalidStateError):
            engine.cancel(100, cancelled_by=1)


class TestEngineResubmit:

    def test_resubmit_rejected_creates_new(self):
        engine = _make_engine()
        old_req = {
            'id': 100, 'entity_type': 'invoice', 'entity_id': 1,
            'flow_id': 1, 'status': 'rejected', 'priority': 'normal',
        }
        engine._request_repo.get_by_id.return_value = old_req

        # Mock submit path
        flow = {'id': 1, 'name': 'Test', 'auto_approve_below': None,
                'trigger_conditions': {}}
        engine._request_repo.get_pending_for_entity.return_value = None
        engine._flow_repo.get_active_flows_for_entity_type.return_value = [flow]
        engine._request_repo.create.return_value = 101
        engine._flow_repo.get_steps_for_flow.return_value = [
            {'id': 10, 'name': 'S1', 'step_order': 1, 'skip_conditions': {}},
        ]

        # Return new request on second get_by_id call
        engine._request_repo.get_by_id.side_effect = [
            old_req,  # resubmit reads old
            {'id': 101, 'status': 'pending'},  # submit returns new
        ]

        engine.resubmit(100, {'amount': 3000}, resubmitted_by=1)

        engine._audit_repo.log.assert_any_call(
            100, 'resubmitted', 1, details={'new_context_keys': ['amount']})

    def test_resubmit_pending_raises(self):
        engine = _make_engine()
        engine._request_repo.get_by_id.return_value = {
            'id': 100, 'status': 'pending',
        }

        from core.approvals.engine import InvalidStateError
        with pytest.raises(InvalidStateError):
            engine.resubmit(100, {}, resubmitted_by=1)


class TestEngineEscalate:

    def test_escalate_with_escalation_step(self):
        engine = _make_engine()
        req = {'id': 100, 'entity_type': 'invoice', 'entity_id': 1,
               'status': 'pending', 'current_step_id': 10, 'flow_id': 1}
        step = {'id': 10, 'name': 'Step 1', 'escalation_step_id': 11,
                'escalation_user_id': None}
        esc_step = {'id': 11, 'name': 'Escalation Step'}

        engine._request_repo.get_by_id.return_value = req
        engine._flow_repo.get_step_by_id.side_effect = [step, esc_step]

        engine.escalate(100, reason='timeout')

        engine._request_repo.update_status.assert_called_once_with(
            100, 'escalated', current_step_id=11)

    def test_escalate_no_path_logs(self):
        engine = _make_engine()
        req = {'id': 100, 'entity_type': 'invoice', 'entity_id': 1,
               'status': 'pending', 'current_step_id': 10}
        step = {'id': 10, 'name': 'Step 1',
                'escalation_step_id': None, 'escalation_user_id': None}
        engine._request_repo.get_by_id.return_value = req
        engine._flow_repo.get_step_by_id.return_value = step

        engine.escalate(100, reason='timeout')

        # Should log attempt but not change status
        engine._audit_repo.log.assert_called()
        engine._request_repo.update_status.assert_not_called()


# ═══════════════════════════════════════════════
# Full Flow Integration Test
# ═══════════════════════════════════════════════

class TestFullFlow:
    """Test complete submit → approve step 1 → approve step 2 → approved."""

    def setup_method(self):
        hooks.clear()

    def test_two_step_approval(self):
        engine = _make_engine()

        flow = {'id': 1, 'name': '2-Step Approval', 'auto_approve_below': None,
                'trigger_conditions': {}}
        step1 = {'id': 10, 'name': 'Dept Head', 'step_order': 1,
                 'skip_conditions': {}, 'approver_type': 'specific_user',
                 'approver_user_id': 5, 'approver_role_name': None,
                 'requires_all': False, 'min_approvals': 1}
        step2 = {'id': 11, 'name': 'Finance', 'step_order': 2,
                 'skip_conditions': {}, 'approver_type': 'specific_user',
                 'approver_user_id': 6, 'approver_role_name': None,
                 'requires_all': False, 'min_approvals': 1}
        all_steps = [step1, step2]

        events = []
        hooks.on('approval.submitted', lambda p: events.append(('submitted', p)))
        hooks.on('approval.step_advanced', lambda p: events.append(('advanced', p)))
        hooks.on('approval.approved', lambda p: events.append(('approved', p)))

        # Submit
        engine._request_repo.get_pending_for_entity.return_value = None
        engine._flow_repo.get_active_flows_for_entity_type.return_value = [flow]
        engine._request_repo.create.return_value = 100
        engine._flow_repo.get_steps_for_flow.return_value = all_steps
        engine._request_repo.get_by_id.return_value = {
            'id': 100, 'entity_type': 'invoice', 'entity_id': 42,
            'flow_id': 1, 'status': 'pending', 'current_step_id': 10,
            'context_snapshot': {'amount': 5000},
        }

        engine.submit('invoice', 42, {'amount': 5000}, requested_by=1)
        assert events[0][0] == 'submitted'

        # Decide step 1 (approve)
        req_at_step1 = {
            'id': 100, 'entity_type': 'invoice', 'entity_id': 42,
            'flow_id': 1, 'status': 'pending', 'current_step_id': 10,
            'context_snapshot': {'amount': 5000}, 'requested_by': 1,
        }
        engine._request_repo.get_by_id.return_value = req_at_step1
        engine._flow_repo.get_step_by_id.return_value = step1
        engine._decision_repo.has_user_decided_on_step.return_value = False
        engine._decision_repo.count_decisions_for_step.return_value = {
            'total': 1, 'approved': 1, 'rejected': 0, 'returned': 0, 'abstained': 0,
        }
        engine._delegation_repo.is_delegate_for.return_value = False

        engine.decide(100, 'approved', decided_by=5, comment='LGTM')
        assert any(e[0] == 'advanced' for e in events)

        # Decide step 2 (approve)
        req_at_step2 = {
            'id': 100, 'entity_type': 'invoice', 'entity_id': 42,
            'flow_id': 1, 'status': 'in_progress', 'current_step_id': 11,
            'context_snapshot': {'amount': 5000}, 'requested_by': 1,
        }
        engine._request_repo.get_by_id.return_value = req_at_step2
        engine._flow_repo.get_step_by_id.return_value = step2
        engine._decision_repo.has_user_decided_on_step.return_value = False
        engine._decision_repo.count_decisions_for_step.return_value = {
            'total': 1, 'approved': 1, 'rejected': 0, 'returned': 0, 'abstained': 0,
        }
        engine._flow_repo.get_steps_for_flow.return_value = all_steps

        engine.decide(100, 'approved', decided_by=6)
        assert any(e[0] == 'approved' for e in events)

    def test_reject_at_step_1_stops_flow(self):
        engine = _make_engine()
        flow = {'id': 1, 'name': 'Test', 'auto_approve_below': None,
                'trigger_conditions': {}}
        step1 = {'id': 10, 'name': 'Review', 'step_order': 1,
                 'skip_conditions': {}, 'approver_type': 'specific_user',
                 'approver_user_id': 5, 'approver_role_name': None,
                 'requires_all': False, 'min_approvals': 1}

        events = []
        hooks.on('approval.rejected', lambda p: events.append(('rejected', p)))

        # Submit
        engine._request_repo.get_pending_for_entity.return_value = None
        engine._flow_repo.get_active_flows_for_entity_type.return_value = [flow]
        engine._request_repo.create.return_value = 100
        engine._flow_repo.get_steps_for_flow.return_value = [step1]
        engine._request_repo.get_by_id.return_value = {
            'id': 100, 'entity_type': 'invoice', 'entity_id': 42,
            'flow_id': 1, 'status': 'pending', 'current_step_id': 10,
            'context_snapshot': {},
        }
        engine.submit('invoice', 42, {}, requested_by=1)

        # Reject at step 1
        engine._request_repo.get_by_id.return_value = {
            'id': 100, 'entity_type': 'invoice', 'entity_id': 42,
            'flow_id': 1, 'status': 'pending', 'current_step_id': 10,
            'context_snapshot': {}, 'requested_by': 1,
        }
        engine._flow_repo.get_step_by_id.return_value = step1
        engine._decision_repo.has_user_decided_on_step.return_value = False
        engine._delegation_repo.is_delegate_for.return_value = False

        engine.decide(100, 'rejected', decided_by=5, comment='Not approved')
        assert len(events) == 1
        assert events[0][0] == 'rejected'
