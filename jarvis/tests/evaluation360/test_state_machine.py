"""Tests for the 360 review-cycle state machine (spec §5)."""
import pytest

from hr.evaluation360.domain import state_machine as sm


def test_happy_path_forward_transitions():
    path = [sm.DRAFT, sm.NOMINATION, sm.ACTIVE, sm.CALIBRATION, sm.RELEASED, sm.CLOSED, sm.ARCHIVED]
    for current, target in zip(path, path[1:]):
        assert sm.can_transition(current, target)
        sm.assert_transition(current, target)  # does not raise


def test_calibration_is_optional_active_to_released():
    assert sm.can_transition(sm.ACTIVE, sm.RELEASED)
    sm.assert_transition(sm.ACTIVE, sm.RELEASED)


def test_cannot_skip_stages():
    assert not sm.can_transition(sm.DRAFT, sm.ACTIVE)
    assert not sm.can_transition(sm.NOMINATION, sm.RELEASED)
    with pytest.raises(sm.InvalidTransition):
        sm.assert_transition(sm.DRAFT, sm.ACTIVE)


def test_no_backward_or_reopen():
    assert not sm.can_transition(sm.ACTIVE, sm.NOMINATION)
    assert not sm.can_transition(sm.RELEASED, sm.ACTIVE)
    assert not sm.can_transition(sm.CLOSED, sm.RELEASED)


def test_archived_is_terminal():
    assert sm.is_terminal(sm.ARCHIVED)
    assert sm.next_states(sm.ARCHIVED) == frozenset()
    with pytest.raises(sm.InvalidTransition):
        sm.assert_transition(sm.ARCHIVED, sm.CLOSED)


def test_unknown_states_raise():
    with pytest.raises(sm.InvalidTransition):
        sm.assert_transition('bogus', sm.NOMINATION)
    with pytest.raises(sm.InvalidTransition):
        sm.assert_transition(sm.DRAFT, 'bogus')


def test_all_states_covered_in_transition_table():
    for state in sm.STATES:
        assert state in sm._TRANSITIONS
