"""Test suite for the buyback status lifecycle state machine (Task 2).

Validates status transitions, labels, and the transition validator.
"""
from buyback import lifecycle as L


def test_valid_transitions():
    assert L.is_valid_transition('PENDING_EVALUATION', 'INITIAL_OFFER')
    assert L.is_valid_transition('INITIAL_OFFER', 'INSPECTION')
    assert L.is_valid_transition('INITIAL_OFFER', 'LOST')
    assert L.is_valid_transition('INSPECTION', 'FINAL_OFFER')
    assert L.is_valid_transition('FINAL_OFFER', 'BOUGHT')
    assert L.is_valid_transition('LOST', 'PENDING_EVALUATION')  # reopen


def test_illegal_transitions_rejected():
    assert not L.is_valid_transition('PENDING_EVALUATION', 'BOUGHT')
    assert not L.is_valid_transition('BOUGHT', 'LOST')
    assert not L.is_valid_transition('CANCELLED', 'INITIAL_OFFER')


def test_every_status_has_label():
    for s in ['PENDING_EVALUATION', 'INITIAL_OFFER', 'INSPECTION', 'FINAL_OFFER', 'BOUGHT', 'LOST', 'CANCELLED']:
        assert s in L.STATUS_LABELS and L.STATUS_LABELS[s]
