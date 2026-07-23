"""Tests for CycleService — transition guards, dry-run (A6/A7), progress."""
from unittest.mock import MagicMock

import pytest

from hr.evaluation360.services.cycle_service import CycleService, CycleError
from hr.evaluation360.domain.state_machine import InvalidTransition


def _service(cycle=None, participants=None, peer_pool=0, loads=None, counts=None):
    cr, ar, ev = MagicMock(), MagicMock(), MagicMock()
    cr.get.return_value = cycle
    cr.list_participants.return_value = participants or []
    cr.eligible_peer_count.return_value = peer_pool
    ar.reviewer_load.return_value = loads or []
    ar.status_counts.return_value = counts or {}
    ar.completion_by_department.return_value = []
    return CycleService(cr, ar, ev), cr, ar, ev


def test_valid_transition_sets_status_and_emits():
    svc, cr, ar, ev = _service(cycle={'id': 1, 'status': 'active'})
    svc.transition(1, 'released', actor_id=9)
    cr.set_status.assert_called_once_with(1, 'released')
    ev.emit.assert_called_once()
    assert ev.emit.call_args[0][0] == 'cycle.released'


def test_illegal_transition_raises_and_does_not_write():
    svc, cr, ar, ev = _service(cycle={'id': 1, 'status': 'draft'})
    with pytest.raises(InvalidTransition):
        svc.transition(1, 'active', actor_id=9)  # must go through nomination
    cr.set_status.assert_not_called()


def test_draft_to_nomination_blocked_by_missing_peers():
    svc, cr, ar, ev = _service(
        cycle={'id': 1, 'status': 'draft'},
        participants=[{'employee_id': 10}], peer_pool=2)  # < 3 eligible peers
    with pytest.raises(CycleError):
        svc.transition(1, 'nomination', actor_id=9)
    cr.set_status.assert_not_called()


def test_draft_to_nomination_waived_proceeds():
    svc, cr, ar, ev = _service(
        cycle={'id': 1, 'status': 'draft'},
        participants=[{'employee_id': 10}], peer_pool=2)
    svc.transition(1, 'nomination', actor_id=9, waive_blocking=True)
    cr.set_status.assert_called_once_with(1, 'nomination')


def test_draft_to_nomination_clean_proceeds():
    svc, cr, ar, ev = _service(
        cycle={'id': 1, 'status': 'draft'},
        participants=[{'employee_id': 10}], peer_pool=5)  # healthy pool
    svc.transition(1, 'nomination', actor_id=9)
    cr.set_status.assert_called_once_with(1, 'nomination')


def test_dry_run_flags_overload_and_missing_peers():
    svc, cr, ar, ev = _service(
        participants=[{'employee_id': 10}], peer_pool=1,
        loads=[{'reviewer_id': 7, 'load': 9}, {'reviewer_id': 8, 'load': 4}])
    report = svc.dry_run(1)
    assert report['overloaded_reviewers'] == [{'reviewer_id': 7, 'load': 9}]
    assert report['participants_missing_peers'] == [{'employee_id': 10, 'eligible_peers': 1}]
    assert report['blocking'] is True


def test_progress_excludes_dropped_from_denominator():
    svc, cr, ar, ev = _service(counts={'submitted': 8, 'invited': 2, 'declined': 1})
    p = svc.progress(1)
    assert p['total'] == 10          # declined excluded
    assert p['submitted'] == 8
    assert p['completion_pct'] == 80.0
    assert p['declines_pending'] == 1


def test_transition_unknown_cycle_raises():
    svc, cr, ar, ev = _service(cycle=None)
    with pytest.raises(CycleError):
        svc.transition(999, 'nomination', actor_id=9)
