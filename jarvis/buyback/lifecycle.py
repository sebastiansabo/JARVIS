"""Status lifecycle state machine for the buyback module.

Defines valid status values, legal transitions, and human-readable labels.
"""

PENDING_EVALUATION = 'PENDING_EVALUATION'
INITIAL_OFFER = 'INITIAL_OFFER'
INSPECTION = 'INSPECTION'
FINAL_OFFER = 'FINAL_OFFER'
BOUGHT = 'BOUGHT'
LOST = 'LOST'
CANCELLED = 'CANCELLED'
ON_HOLD = 'ON_HOLD'
# Consignment proposal flow (Propune consignație): a seller-accepted
# consignment instead of a purchase. CONSIGNMENT_OFFER is the awaiting-decision
# state (parallel to INITIAL_OFFER/FINAL_OFFER); CONSIGNAT is the accepted
# terminal state where the car has been handed off to CarPark on consignment
# (parallel to BOUGHT — the car now lives in CarPark, so no reopen).
CONSIGNMENT_OFFER = 'CONSIGNMENT_OFFER'
CONSIGNAT = 'CONSIGNAT'

TRANSITIONS = {
    PENDING_EVALUATION: {INITIAL_OFFER, CONSIGNMENT_OFFER, CANCELLED, ON_HOLD},
    INITIAL_OFFER: {INSPECTION, LOST, CANCELLED, ON_HOLD},
    INSPECTION: {FINAL_OFFER, CANCELLED, ON_HOLD},
    FINAL_OFFER: {BOUGHT, LOST, CANCELLED, ON_HOLD},
    # Consignment proposal: accept → CONSIGNAT (hand-off), decline → LOST,
    # manager abort → CANCELLED.
    CONSIGNMENT_OFFER: {CONSIGNAT, LOST, CANCELLED},
    BOUGHT: set(),
    CONSIGNAT: set(),                  # terminal — car handed off to CarPark
    LOST: {PENDING_EVALUATION},        # manager reopen
    CANCELLED: {PENDING_EVALUATION},   # manager reopen (same as LOST)
    ON_HOLD: {PENDING_EVALUATION, INITIAL_OFFER, INSPECTION, FINAL_OFFER, CANCELLED},
}

STATUS_LABELS = {
    PENDING_EVALUATION: 'În evaluare',
    INITIAL_OFFER: 'Ofertă inițială',
    INSPECTION: 'În inspecție',
    FINAL_OFFER: 'Ofertă finală',
    CONSIGNMENT_OFFER: 'Ofertă consignație',
    BOUGHT: 'Achiziționat',
    CONSIGNAT: 'Consignat',
    LOST: 'Pierdut',
    CANCELLED: 'Anulat',
    ON_HOLD: 'Suspendat',
}


def is_valid_transition(old: str, new: str) -> bool:
    """Check if a transition from old status to new status is allowed.

    Args:
        old: The current status (e.g., 'PENDING_EVALUATION')
        new: The proposed new status (e.g., 'INITIAL_OFFER')

    Returns:
        True if the transition is valid, False otherwise.
    """
    return new in TRANSITIONS.get(old, set())
