"""Pure-function tests for the CarPark status-transition matrix.

No DB access — TRANSITIONS and is_valid_transition are plain module-level
data/logic, so these run fine under the psycopg2 mock installed by
jarvis/conftest.py.
"""
from carpark.services.vehicle_service import TRANSITIONS, is_valid_transition

VALID_STATUSES = {
    'ACQUIRED', 'INSPECTION', 'RECONDITIONING', 'READY_FOR_SALE',
    'LISTED', 'RESERVED', 'SOLD', 'DELIVERED',
    'PRICE_REDUCED', 'AUCTION_CANDIDATE',
    'IN_TRANSIT', 'AT_BODYSHOP', 'INSURANCE_CLAIM',
    'RETURNED', 'SCRAPPED', 'TRANSFERRED',
}


def test_ready_for_sale_to_sold_allowed():
    assert is_valid_transition('READY_FOR_SALE', 'SOLD') is True


def test_sold_to_acquired_forbidden():
    assert is_valid_transition('SOLD', 'ACQUIRED') is False


def test_delivered_to_returned_allowed():
    assert is_valid_transition('DELIVERED', 'RETURNED') is True


def test_scrapped_to_listed_forbidden():
    assert is_valid_transition('SCRAPPED', 'LISTED') is False


def test_same_status_noop_allowed():
    assert is_valid_transition('LISTED', 'LISTED') is True


def test_transitions_dict_integrity():
    """Every key and every element of every value set must be one of the
    16 valid statuses — guards against typos in the matrix."""
    assert set(TRANSITIONS.keys()) == VALID_STATUSES
    for old_status, targets in TRANSITIONS.items():
        assert isinstance(targets, set), f'{old_status} targets must be a set'
        for target in targets:
            assert target in VALID_STATUSES, (
                f'{old_status} -> {target}: {target!r} is not a valid status'
            )
