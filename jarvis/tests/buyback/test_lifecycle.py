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
    assert L.is_valid_transition('CANCELLED', 'PENDING_EVALUATION')  # reopen


def test_illegal_transitions_rejected():
    assert not L.is_valid_transition('PENDING_EVALUATION', 'BOUGHT')
    assert not L.is_valid_transition('BOUGHT', 'LOST')
    assert not L.is_valid_transition('CANCELLED', 'INITIAL_OFFER')
    # BOUGHT stays fully terminal — only an admin force-override can leave it.
    assert not L.is_valid_transition('BOUGHT', 'PENDING_EVALUATION')


def test_every_status_has_label():
    for s in ['PENDING_EVALUATION', 'INITIAL_OFFER', 'INSPECTION', 'FINAL_OFFER', 'BOUGHT', 'LOST', 'CANCELLED']:
        assert s in L.STATUS_LABELS and L.STATUS_LABELS[s]


# ── Consignment proposal lifecycle (Propune consignație) ──────────────────

def test_consignment_offer_proposed_from_pending():
    """A consignment proposal opens from PENDING_EVALUATION (same pre-offer
    status as an initial buy offer), moving the record to CONSIGNMENT_OFFER."""
    assert L.is_valid_transition('PENDING_EVALUATION', 'CONSIGNMENT_OFFER')


def test_consignment_offer_accept_goes_consignat():
    assert L.is_valid_transition('CONSIGNMENT_OFFER', 'CONSIGNAT')


def test_consignment_offer_decline_goes_lost():
    assert L.is_valid_transition('CONSIGNMENT_OFFER', 'LOST')


def test_consignment_offer_can_be_cancelled():
    assert L.is_valid_transition('CONSIGNMENT_OFFER', 'CANCELLED')


def test_consignat_is_terminal():
    """CONSIGNAT is terminal like BOUGHT — the car now lives in CarPark on
    consignment; only an admin force-override can leave it."""
    assert not L.is_valid_transition('CONSIGNAT', 'PENDING_EVALUATION')
    assert not L.is_valid_transition('CONSIGNAT', 'LOST')
    assert L.TRANSITIONS['CONSIGNAT'] == set()


def test_consignment_illegal_transitions_rejected():
    # Can't jump straight from PENDING_EVALUATION to the accepted state.
    assert not L.is_valid_transition('PENDING_EVALUATION', 'CONSIGNAT')
    # A posted buy offer can't morph into a consignment proposal.
    assert not L.is_valid_transition('INITIAL_OFFER', 'CONSIGNMENT_OFFER')


def test_new_consignment_statuses_have_labels():
    assert L.STATUS_LABELS['CONSIGNMENT_OFFER'] == 'Ofertă consignație'
    assert L.STATUS_LABELS['CONSIGNAT'] == 'Consignat'
