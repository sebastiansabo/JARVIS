"""Unit tests for the CarPark Dispo scheduler task functions
(expire_reservations, carpark_aging_alerts) in tasks/carpark.py.

Mirrors jarvis/tests/tasks/test_foi_parcurs_sessions.py: no DB access, every
collaborator repo/notify_user is mocked. tasks/carpark.py imports its
collaborators *inside* each function body (matching the existing
cleanup_vin_cache task), so — unlike test_foi_parcurs_sessions.py, whose
target module does its imports at module scope and can be patched via
patch.object(job, 'Name', ...) — these tests patch the classes/functions at
their *defining* module path (e.g.
'carpark.repositories.reservation_repository.ReservationRepository'). Because
the `from module import Name` inside each task function only resolves at
call time, patching the name on its defining module is picked up correctly
regardless of where the import happens to live.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from unittest.mock import MagicMock, patch

import tasks.carpark as job


# ─────────────────────────────────────────────────────────────────────────
# expire_reservations
# ─────────────────────────────────────────────────────────────────────────

def _patched_expire(reservation_repo, vehicle_repo, vehicle_service, notify_fn):
    return (
        patch('carpark.repositories.reservation_repository.ReservationRepository',
              return_value=reservation_repo),
        patch('carpark.repositories.vehicle_repository.VehicleRepository',
              return_value=vehicle_repo),
        patch('carpark.services.vehicle_service.VehicleService',
              return_value=vehicle_service),
        patch('core.notifications.notify.notify_user', notify_fn),
    )


def test_expire_reservations_no_expired_is_a_noop():
    reservation_repo = MagicMock()
    reservation_repo.expired.return_value = []
    vehicle_repo = MagicMock()
    vehicle_service = MagicMock()
    notify_fn = MagicMock()

    p1, p2, p3, p4 = _patched_expire(reservation_repo, vehicle_repo, vehicle_service, notify_fn)
    with p1, p2, p3, p4:
        job.expire_reservations()

    reservation_repo.set_status.assert_not_called()
    vehicle_service.change_status.assert_not_called()
    notify_fn.assert_not_called()


def test_expire_reservations_marks_expired_moves_vehicle_and_notifies():
    reservation_repo = MagicMock()
    reservation_repo.expired.return_value = [
        {'id': 101, 'vehicle_id': 1, 'user_id': 42},
    ]
    vehicle_repo = MagicMock()
    vehicle_repo.get_by_id.return_value = {
        'id': 1, 'status': 'RESERVED', 'brand': 'TestBrand', 'model': 'TestModel', 'vin': 'V1',
    }
    vehicle_service = MagicMock()
    notify_fn = MagicMock()

    p1, p2, p3, p4 = _patched_expire(reservation_repo, vehicle_repo, vehicle_service, notify_fn)
    with p1, p2, p3, p4:
        job.expire_reservations()

    reservation_repo.set_status.assert_called_once_with(101, 'expired')
    vehicle_service.change_status.assert_called_once_with(
        1, 'LISTED', changed_by=None, notes='Reservation expired')
    notify_fn.assert_called_once()
    assert notify_fn.call_args[0][0] == 42


def test_expire_reservations_skips_vehicle_move_when_no_longer_reserved():
    """A vehicle sold/delivered out from under an overdue reservation must
    not be yanked back to LISTED — the reservation is still marked expired,
    but change_status/notify are skipped."""
    reservation_repo = MagicMock()
    reservation_repo.expired.return_value = [
        {'id': 101, 'vehicle_id': 1, 'user_id': 42},
    ]
    vehicle_repo = MagicMock()
    vehicle_repo.get_by_id.return_value = {'id': 1, 'status': 'SOLD'}
    vehicle_service = MagicMock()
    notify_fn = MagicMock()

    p1, p2, p3, p4 = _patched_expire(reservation_repo, vehicle_repo, vehicle_service, notify_fn)
    with p1, p2, p3, p4:
        job.expire_reservations()

    reservation_repo.set_status.assert_called_once_with(101, 'expired')
    vehicle_service.change_status.assert_not_called()
    notify_fn.assert_not_called()


def test_expire_reservations_without_user_id_skips_notify_but_still_moves_vehicle():
    reservation_repo = MagicMock()
    reservation_repo.expired.return_value = [
        {'id': 101, 'vehicle_id': 1, 'user_id': None},
    ]
    vehicle_repo = MagicMock()
    vehicle_repo.get_by_id.return_value = {'id': 1, 'status': 'RESERVED', 'brand': 'B', 'model': 'M'}
    vehicle_service = MagicMock()
    notify_fn = MagicMock()

    p1, p2, p3, p4 = _patched_expire(reservation_repo, vehicle_repo, vehicle_service, notify_fn)
    with p1, p2, p3, p4:
        job.expire_reservations()

    vehicle_service.change_status.assert_called_once()
    notify_fn.assert_not_called()


def test_expire_reservations_one_bad_row_does_not_abort_batch():
    reservation_repo = MagicMock()
    reservation_repo.expired.return_value = [
        {'id': 101, 'vehicle_id': 1, 'user_id': 42},
        {'id': 102, 'vehicle_id': 2, 'user_id': 43},
    ]
    vehicle_repo = MagicMock()

    def _get_by_id(vid):
        if vid == 1:
            raise RuntimeError('boom')
        return {'id': 2, 'status': 'RESERVED', 'brand': 'B', 'model': 'M'}
    vehicle_repo.get_by_id.side_effect = _get_by_id

    vehicle_service = MagicMock()
    notify_fn = MagicMock()

    p1, p2, p3, p4 = _patched_expire(reservation_repo, vehicle_repo, vehicle_service, notify_fn)
    with p1, p2, p3, p4:
        job.expire_reservations()

    # Both reservations get marked expired (that call happens before the
    # per-vehicle lookup that blows up for id=1)...
    assert reservation_repo.set_status.call_count == 2
    # ...but only the second (surviving) row reaches change_status/notify.
    vehicle_service.change_status.assert_called_once_with(
        2, 'LISTED', changed_by=None, notes='Reservation expired')
    notify_fn.assert_called_once()
    assert notify_fn.call_args[0][0] == 43


# ─────────────────────────────────────────────────────────────────────────
# carpark_aging_alerts
# ─────────────────────────────────────────────────────────────────────────

def _patched_aging(dispo_repo, notify_fn):
    return (
        patch('carpark.repositories.dispo_repository.DispoRepository',
              return_value=dispo_repo),
        patch('core.notifications.notify.notify_user', notify_fn),
    )


def test_carpark_aging_alerts_no_aged_vehicles_is_a_noop():
    dispo_repo = MagicMock()
    dispo_repo.aged_unsold.return_value = []
    notify_fn = MagicMock()

    p1, p2 = _patched_aging(dispo_repo, notify_fn)
    with p1, p2:
        job.carpark_aging_alerts()

    dispo_repo.aged_unsold.assert_called_once_with(60)
    notify_fn.assert_not_called()


def test_carpark_aging_alerts_notifies_salesperson():
    dispo_repo = MagicMock()
    dispo_repo.aged_unsold.return_value = [
        {'id': 1, 'vin': 'V1', 'brand': 'B', 'model': 'M', 'days_in_stock': 75,
         'salesperson_user_id': 55, 'acquisition_manager_id': 77, 'company_id': 10},
    ]
    notify_fn = MagicMock()

    p1, p2 = _patched_aging(dispo_repo, notify_fn)
    with p1, p2:
        job.carpark_aging_alerts()

    notify_fn.assert_called_once()
    assert notify_fn.call_args[0][0] == 55  # salesperson wins over acquisition_manager


def test_carpark_aging_alerts_falls_back_to_acquisition_manager():
    dispo_repo = MagicMock()
    dispo_repo.aged_unsold.return_value = [
        {'id': 1, 'vin': 'V1', 'brand': 'B', 'model': 'M', 'days_in_stock': 75,
         'salesperson_user_id': None, 'acquisition_manager_id': 77, 'company_id': 10},
    ]
    notify_fn = MagicMock()

    p1, p2 = _patched_aging(dispo_repo, notify_fn)
    with p1, p2:
        job.carpark_aging_alerts()

    notify_fn.assert_called_once()
    assert notify_fn.call_args[0][0] == 77


def test_carpark_aging_alerts_skips_vehicle_with_no_target_user():
    dispo_repo = MagicMock()
    dispo_repo.aged_unsold.return_value = [
        {'id': 1, 'vin': 'V1', 'brand': 'B', 'model': 'M', 'days_in_stock': 75,
         'salesperson_user_id': None, 'acquisition_manager_id': None, 'company_id': 10},
    ]
    notify_fn = MagicMock()

    p1, p2 = _patched_aging(dispo_repo, notify_fn)
    with p1, p2:
        job.carpark_aging_alerts()

    notify_fn.assert_not_called()


def test_carpark_aging_alerts_one_bad_vehicle_does_not_abort_batch():
    dispo_repo = MagicMock()
    dispo_repo.aged_unsold.return_value = [
        {'id': 1, 'vin': 'V1', 'brand': 'B', 'model': 'M', 'days_in_stock': 90,
         'salesperson_user_id': 55, 'acquisition_manager_id': None, 'company_id': 10},
        {'id': 2, 'vin': 'V2', 'brand': 'B', 'model': 'M', 'days_in_stock': 61,
         'salesperson_user_id': 56, 'acquisition_manager_id': None, 'company_id': 10},
    ]
    notify_fn = MagicMock()
    notify_fn.side_effect = [RuntimeError('boom'), None]

    p1, p2 = _patched_aging(dispo_repo, notify_fn)
    with p1, p2:
        job.carpark_aging_alerts()

    assert notify_fn.call_count == 2
