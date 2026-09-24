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

TRANSITIONS = {
    PENDING_EVALUATION: {INITIAL_OFFER, CANCELLED},
    INITIAL_OFFER: {INSPECTION, LOST, CANCELLED},
    INSPECTION: {FINAL_OFFER, CANCELLED},
    FINAL_OFFER: {BOUGHT, LOST, CANCELLED},
    BOUGHT: set(),
    LOST: {PENDING_EVALUATION},   # manager reopen
    CANCELLED: set(),
}

STATUS_LABELS = {
    PENDING_EVALUATION: 'În evaluare',
    INITIAL_OFFER: 'Ofertă inițială',
    INSPECTION: 'În inspecție',
    FINAL_OFFER: 'Ofertă finală',
    BOUGHT: 'Achiziționat',
    LOST: 'Pierdut',
    CANCELLED: 'Anulat',
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
