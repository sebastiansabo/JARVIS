"""Tests for NominationService — fan-out, decline/replace, 48h auto-approve."""
from unittest.mock import MagicMock

from hr.evaluation360.services.nomination_service import NominationService


def _repos():
    ar, ev = MagicMock(), MagicMock()
    counter = iter(range(1, 1000))
    ar.create.side_effect = lambda **kw: {'id': next(counter), **kw}
    return ar, ev


def test_fan_out_creates_all_relationships():
    ar, ev = _repos()
    svc = NominationService(assignment_repo=ar, event_repo=ev,
                            manager_resolver=lambda s: 99,
                            reports_resolver=lambda s: [201, 202])
    created = svc.fan_out(cycle_id=5, subject_id=10, peer_reviewer_ids=[301, 302])
    assert [c['relationship'] for c in created] == [
        'self', 'manager', 'direct_report', 'direct_report', 'peer', 'peer']
    assert created[0]['reviewer_id'] == 10   # self reviews self
    assert created[1]['reviewer_id'] == 99   # manager
    statuses = {c['relationship']: c['status'] for c in created}
    assert statuses['self'] == 'invited'
    assert statuses['peer'] == 'pending_approval'   # peers need approval
    assert ev.emit.call_count == 6                  # assignment.created per assignment


def test_fan_out_without_manager_or_reports():
    ar, ev = _repos()
    svc = NominationService(assignment_repo=ar, event_repo=ev,
                            manager_resolver=lambda s: None,
                            reports_resolver=lambda s: [])
    created = svc.fan_out(5, 10, peer_reviewer_ids=[])
    assert [c['relationship'] for c in created] == ['self']


def test_decline_and_replace():
    ar, ev = MagicMock(), MagicMock()
    ar.get.return_value = {'id': 7, 'cycle_id': 5, 'subject_id': 10,
                           'relationship': 'peer', 'due_at': None}
    ar.create.return_value = {'id': 20}
    svc = NominationService(assignment_repo=ar, event_repo=ev)
    replacement = svc.decline_and_replace(7, 'too busy', replacement_reviewer_id=42)
    ar.decline.assert_called_once_with(7, 'too busy')
    ar.mark_replaced.assert_called_once_with(7, 20)
    assert replacement['id'] == 20
    # both a decline and a creation event were emitted
    emitted = [c.args[0] for c in ev.emit.call_args_list]
    assert 'assignment.declined' in emitted
    assert 'assignment.created' in emitted


def test_auto_approve_stale():
    ar, ev = MagicMock(), MagicMock()
    ar.stale_pending.return_value = [{'id': 1}, {'id': 2}]
    svc = NominationService(assignment_repo=ar, event_repo=ev)
    n = svc.auto_approve_stale(5, hours=48)
    assert n == 2
    assert ar.set_status.call_count == 2
    ar.set_status.assert_any_call(1, 'invited')
