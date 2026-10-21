"""Tests for the auto status<->listing sync: a car flips to LISTED the moment
it goes live on its first marketplace channel (Autovit or Autoworld), and back
to READY_FOR_SALE when it comes off the last one — while NEVER touching a car
that's reserved/sold/delivered or sitting in a manual promo/prep status.

No DB access. `next_status_for_listings` is pure module-level logic;
`sync_listing_status` runs on a real VehicleService() with `_repo` swapped for a
MagicMock, mirroring test_transitions.py's mocked-collaborator style.
"""
from unittest.mock import MagicMock

import pytest

from carpark.services.vehicle_service import (
    LISTED_ON_PUBLISH_NOTE,
    UNLISTED_NOTE,
    VehicleService,
    next_status_for_listings,
)


# ── pure decision: next_status_for_listings(current_status, live_count) ──

def test_ready_for_sale_advances_to_listed_on_first_channel():
    assert next_status_for_listings('READY_FOR_SALE', 1) == 'LISTED'


def test_ready_for_sale_advances_to_listed_on_both_channels():
    assert next_status_for_listings('READY_FOR_SALE', 2) == 'LISTED'


def test_listed_reverts_to_ready_when_no_channels_left():
    assert next_status_for_listings('LISTED', 0) == 'READY_FOR_SALE'


def test_listed_with_live_channels_is_noop():
    assert next_status_for_listings('LISTED', 1) is None
    assert next_status_for_listings('LISTED', 2) is None


def test_ready_for_sale_with_no_channels_is_noop():
    assert next_status_for_listings('READY_FOR_SALE', 0) is None


@pytest.mark.parametrize('status', ['RESERVED', 'SOLD', 'DELIVERED'])
def test_committed_statuses_never_change(status):
    """A car that's reserved/sold/delivered keeps its status even if a listing
    is still live (seller forgot to retract) or all got pulled."""
    assert next_status_for_listings(status, 2) is None
    assert next_status_for_listings(status, 0) is None


@pytest.mark.parametrize('status', ['PRICE_REDUCED', 'AUCTION_CANDIDATE'])
def test_manual_promo_statuses_not_reverted(status):
    """A manually-promoted listing dropping to 0 channels keeps the operator's
    status — we only auto-manage the READY_FOR_SALE<->LISTED pair."""
    assert next_status_for_listings(status, 0) is None


@pytest.mark.parametrize('status', ['ACQUIRED', 'INSPECTION', 'RECONDITIONING'])
def test_prep_statuses_not_force_listed(status):
    """Publishing a not-yet-ready car (still in prep) must not force it to
    LISTED — only READY_FOR_SALE advances."""
    assert next_status_for_listings(status, 1) is None


# ── orchestration: VehicleService.sync_listing_status(vehicle_id) ──

def _svc(status, live_count):
    svc = VehicleService()
    svc._repo = MagicMock()
    svc._repo.get_by_id.return_value = {'id': 7, 'status': status}
    svc._repo.count_live_listings.return_value = live_count
    svc._repo.change_status.return_value = {'id': 7, 'status': 'CHANGED'}
    return svc


def test_sync_advances_to_listed_on_publish():
    svc = _svc('READY_FOR_SALE', 1)
    result = svc.sync_listing_status(7)
    svc._repo.change_status.assert_called_once_with(
        7, 'LISTED', changed_by=None, notes=LISTED_ON_PUBLISH_NOTE)
    assert result == {'id': 7, 'status': 'CHANGED'}


def test_sync_reverts_to_ready_on_last_unpublish():
    svc = _svc('LISTED', 0)
    svc.sync_listing_status(7)
    svc._repo.change_status.assert_called_once_with(
        7, 'READY_FOR_SALE', changed_by=None, notes=UNLISTED_NOTE)


def test_sync_is_noop_when_already_consistent():
    svc = _svc('LISTED', 2)
    result = svc.sync_listing_status(7)
    svc._repo.change_status.assert_not_called()
    assert result is None


def test_sync_passes_changed_by_through():
    svc = _svc('READY_FOR_SALE', 2)
    svc.sync_listing_status(7, changed_by=42)
    svc._repo.change_status.assert_called_once_with(
        7, 'LISTED', changed_by=42, notes=LISTED_ON_PUBLISH_NOTE)


def test_sync_unknown_vehicle_is_noop():
    svc = VehicleService()
    svc._repo = MagicMock()
    svc._repo.get_by_id.return_value = None
    result = svc.sync_listing_status(999)
    assert result is None
    svc._repo.change_status.assert_not_called()
