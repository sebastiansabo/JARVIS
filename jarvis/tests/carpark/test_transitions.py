"""Pure-function tests for the CarPark status-transition matrix, plus
VehicleService.change_status's RESERVED-exit guard.

No DB access — TRANSITIONS and is_valid_transition are plain module-level
data/logic, so these run fine under the psycopg2 mock installed by
jarvis/conftest.py. The change_status tests instantiate a real
VehicleService() (its constructor only builds repository objects, no
connection is opened) and swap its private `_repo` for a MagicMock, mirroring
the DI-via-injected-mock style used in test_dispo_service.py.
"""
from unittest.mock import MagicMock

import pytest

from carpark.services.vehicle_service import TRANSITIONS, VehicleService, is_valid_transition

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


# ── change_status RESERVED-exit guard ───────────────────────────────────
#
# A RESERVED vehicle carries an active carpark_reservations row that only
# DispoService.cancel_reservation()/sell() know how to close. A plain status
# flip (e.g. via PUT /vehicles/:id/status) that moves a vehicle OUT of
# RESERVED without going through one of those two paths would orphan that
# row. change_status() blocks that by default; allow_reserved_exit=True is
# the opt-in reserved for the two guarded paths.

def _svc_with_status(status):
    """A real VehicleService with `_repo` swapped for a MagicMock — no DB
    access, mirrors the mocked-collaborator style in test_dispo_service.py."""
    svc = VehicleService()
    svc._repo = MagicMock()
    svc._repo.get_by_id.return_value = {'id': 1, 'status': status}
    svc._repo.change_status.return_value = {'id': 1, 'status': 'CHANGED'}
    return svc


def test_change_status_blocks_reserved_exit_by_default():
    svc = _svc_with_status('RESERVED')
    with pytest.raises(ValueError, match='Ieșirea din REZERVAT'):
        svc.change_status(1, 'LISTED')
    svc._repo.change_status.assert_not_called()


def test_change_status_allows_reserved_exit_with_flag():
    svc = _svc_with_status('RESERVED')
    result = svc.change_status(1, 'LISTED', allow_reserved_exit=True)
    svc._repo.change_status.assert_called_once_with(1, 'LISTED', changed_by=None, notes=None)
    assert result == {'id': 1, 'status': 'CHANGED'}


def test_change_status_illegal_transition_raises_before_reserved_guard():
    """RESERVED -> AUCTION_CANDIDATE isn't in TRANSITIONS['RESERVED'] at all
    — the transition-matrix error must fire, not the RESERVED-exit message,
    even with allow_reserved_exit=True."""
    svc = _svc_with_status('RESERVED')
    with pytest.raises(ValueError, match='Tranziție interzisă'):
        svc.change_status(1, 'AUCTION_CANDIDATE', allow_reserved_exit=True)
    svc._repo.change_status.assert_not_called()


def test_change_status_normal_transition_unaffected():
    """A non-RESERVED transition is untouched by the new guard."""
    svc = _svc_with_status('LISTED')
    result = svc.change_status(1, 'PRICE_REDUCED')
    svc._repo.change_status.assert_called_once_with(1, 'PRICE_REDUCED', changed_by=None, notes=None)
    assert result == {'id': 1, 'status': 'CHANGED'}
