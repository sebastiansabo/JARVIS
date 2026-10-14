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

TRANSITIONS = {
    PENDING_EVALUATION: {INITIAL_OFFER, CANCELLED, ON_HOLD},
    INITIAL_OFFER: {INSPECTION, LOST, CANCELLED, ON_HOLD},
    INSPECTION: {FINAL_OFFER, CANCELLED, ON_HOLD},
    FINAL_OFFER: {BOUGHT, LOST, CANCELLED, ON_HOLD},
    BOUGHT: set(),
    LOST: {PENDING_EVALUATION},        # manager reopen
    CANCELLED: {PENDING_EVALUATION},   # manager reopen (same as LOST)
    ON_HOLD: {PENDING_EVALUATION, INITIAL_OFFER, INSPECTION, FINAL_OFFER},
}

STATUS_LABELS = {
    PENDING_EVALUATION: 'În evaluare',
    INITIAL_OFFER: 'Ofertă inițială',
    INSPECTION: 'În inspecție',
    FINAL_OFFER: 'Ofertă finală',
    BOUGHT: 'Achiziționat',
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
