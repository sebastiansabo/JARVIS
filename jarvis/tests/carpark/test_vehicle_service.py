"""Tests for VehicleService.update_vehicle's IMPUS/SCOS mutual-exclusivity
guard.

INVARIANT: NOT (is_impus AND stock_removed) — a vehicle can be flagged
IMPUS or SCOS din evidență, never both at once. missing_civ is independent
and untouched by this guard.

Real VehicleService() with `_repo` swapped for a MagicMock — no DB access,
mirrors the mocked-`_repo` style used in test_transitions.py (VehicleService
takes no constructor args, so there's no DI seam to inject a fake repo
through).
"""
from unittest.mock import MagicMock

import pytest

from carpark.services.vehicle_service import VehicleService


def _svc(vehicle):
    """A real VehicleService with `_repo` swapped for a MagicMock whose
    `update()` mimics VehicleRepository.update()'s real contract: merge the
    incoming (already-normalized) data onto the stored row and return the
    merged record."""
    svc = VehicleService()
    svc._repo = MagicMock()
    svc._repo.get_by_id.return_value = dict(vehicle)

    def _update(vehicle_id, data, updated_by=None):
        merged = dict(vehicle)
        merged.update(data)
        return merged

    svc._repo.update.side_effect = _update
    return svc


# ── explicit conflict in a single payload ───────────────────────────────

def test_update_vehicle_rejects_both_flags_truthy_in_same_payload():
    svc = _svc({'id': 1, 'is_impus': False, 'stock_removed': False, 'missing_civ': False})
    with pytest.raises(ValueError, match='IMPUS'):
        svc.update_vehicle(1, {'is_impus': True, 'stock_removed': True})
    svc._repo.update.assert_not_called()


def test_conflict_raised_before_any_write():
    """The guard fires before _repo.update — a rejected payload must never
    reach the DB layer."""
    svc = _svc({'id': 1, 'is_impus': False, 'stock_removed': False})
    with pytest.raises(ValueError):
        svc.update_vehicle(1, {'is_impus': True, 'stock_removed': True})
    svc._repo.log_modification.assert_not_called()


# ── turning one flag on auto-clears the other ───────────────────────────

def test_setting_impus_clears_existing_stock_removed():
    svc = _svc({'id': 1, 'is_impus': False, 'stock_removed': True, 'missing_civ': False})
    result = svc.update_vehicle(1, {'is_impus': True}, updated_by=1)

    assert result['is_impus'] is True
    assert result['stock_removed'] is False

    sent = svc._repo.update.call_args[0][1]
    assert sent['is_impus'] is True
    assert sent['stock_removed'] is False


def test_setting_stock_removed_clears_existing_impus():
    svc = _svc({'id': 1, 'is_impus': True, 'stock_removed': False, 'missing_civ': False})
    result = svc.update_vehicle(1, {'stock_removed': True}, updated_by=1)

    assert result['stock_removed'] is True
    assert result['is_impus'] is False

    sent = svc._repo.update.call_args[0][1]
    assert sent['stock_removed'] is True
    assert sent['is_impus'] is False


def test_setting_impus_true_when_stock_removed_already_false_is_a_noop_clear():
    """Forcing stock_removed=False when it's already False must not error —
    just a redundant (no-op) write of the same value."""
    svc = _svc({'id': 1, 'is_impus': False, 'stock_removed': False})
    result = svc.update_vehicle(1, {'is_impus': True}, updated_by=1)
    assert result['is_impus'] is True
    assert result['stock_removed'] is False


def test_turning_impus_off_does_not_touch_stock_removed():
    svc = _svc({'id': 1, 'is_impus': True, 'stock_removed': False})
    result = svc.update_vehicle(1, {'is_impus': False}, updated_by=1)
    assert result['is_impus'] is False
    sent = svc._repo.update.call_args[0][1]
    assert 'stock_removed' not in sent


def test_turning_stock_removed_off_does_not_touch_impus():
    svc = _svc({'id': 1, 'is_impus': False, 'stock_removed': True})
    result = svc.update_vehicle(1, {'stock_removed': False}, updated_by=1)
    assert result['stock_removed'] is False
    sent = svc._repo.update.call_args[0][1]
    assert 'is_impus' not in sent


# ── missing_civ is independent ───────────────────────────────────────────

def test_missing_civ_toggle_untouched_by_the_guard():
    svc = _svc({'id': 1, 'is_impus': True, 'stock_removed': False, 'missing_civ': False})
    result = svc.update_vehicle(1, {'missing_civ': True}, updated_by=1)

    assert result['missing_civ'] is True
    # is_impus was never in this payload — the guard must not touch it.
    sent = svc._repo.update.call_args[0][1]
    assert 'is_impus' not in sent
    assert 'stock_removed' not in sent


# ── audit trail: both changed fields must be logged ─────────────────────

def test_auto_clear_logs_both_changed_fields():
    svc = _svc({'id': 1, 'is_impus': False, 'stock_removed': True, 'missing_civ': False})
    svc.update_vehicle(1, {'is_impus': True}, updated_by=1, updated_by_name='Ana Pop')

    logged_fields = {call.args[1] for call in svc._repo.log_modification.call_args_list}
    assert logged_fields == {'is_impus', 'stock_removed'}

    for call in svc._repo.log_modification.call_args_list:
        vehicle_id, field, old_val, new_val = call.args[:4]
        if field == 'is_impus':
            assert old_val is False and new_val is True
        elif field == 'stock_removed':
            assert old_val is True and new_val is False
