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

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

import tasks.carpark as job

from database import get_db, get_cursor, release_db

from .conftest import REAL_DB_AVAILABLE

# Sentinel company_id for THIS file's real-DB test — distinct from
# TEST_COMPANY_ID=990001 (test_dispo_repository_sql.py) and 990002
# (test_phase2_e2e.py) so the three DB-backed suites can never collide.
SCHED_COMPANY_ID = 990003


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
        1, 'LISTED', changed_by=None, notes='Reservation expired', via_dispo_action=True)
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
        2, 'LISTED', changed_by=None, notes='Reservation expired', via_dispo_action=True)
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


# ─────────────────────────────────────────────────────────────────────────
# expire_reservations — REAL-DB integration (proves the via_dispo_action fix)
# ─────────────────────────────────────────────────────────────────────────
#
# The mocked expire_reservations tests above swap VehicleService for a
# MagicMock, so change_status never runs the real via_dispo_action guard —
# which is exactly how the INLINE-4 regression (a RESERVED-exit blocked by
# the guard, then swallowed by the job's per-row try/except, leaving the
# vehicle stuck in RESERVED) slipped through. This test runs the REAL
# VehicleService/VehicleRepository/ReservationRepository against
# localhost/defaultdb so the fix (expire_reservations passing
# via_dispo_action=True) is exercised end-to-end: it fails on the pre-fix
# code because the vehicle never leaves RESERVED.
#
# Only ReservationRepository.expired() is patched — to scope the job to our
# single seeded reservation. expire_reservations() otherwise queries EVERY
# active-but-past reservation in the DB (it's not company-scoped), so an
# unpatched run against a shared dev DB could destructively expire/relist
# unrelated real vehicles. set_status() and change_status() (through the real
# guard and real carpark_status_history write) stay 100% real DB.


@pytest.fixture
def reserved_expired_seed():
    """Seed one RESERVED vehicle under SCHED_COMPANY_ID with an ACTIVE
    reservation whose reservation_end is in the past. user_id is NULL so the
    job skips notify_user (no notifications row to clean up). Yields
    {'vehicle_id': ..., 'reservation_id': ...}.

    Teardown deletes every carpark_vehicles row for SCHED_COMPANY_ID (the
    carpark_reservations + carpark_status_history rows cascade via
    vehicle_id ... ON DELETE CASCADE) and asserts zero remain.
    """
    if not REAL_DB_AVAILABLE:
        pytest.skip(
            'Real Postgres not available (DATABASE_URL unreachable or psycopg2 '
            'mocked) — skipping carpark scheduler DB-backed test'
        )

    conn = get_db()
    conn.autocommit = False
    cur = get_cursor(conn)
    today = date.today()
    ids = {}
    try:
        # Defensive: clear any leftover rows from a previously crashed run.
        cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (SCHED_COMPANY_ID,))

        cur.execute('''
            INSERT INTO carpark_vehicles
                (vin, brand, model, status, company_id, acquisition_date, acquisition_price)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', ('TESTSCHED0000001', 'TestBrand', 'TestModelSched', 'RESERVED',
              SCHED_COMPANY_ID, today - timedelta(days=30), 10000))
        ids['vehicle_id'] = cur.fetchone()['id']

        # Active reservation, already past its end date → the job must expire
        # it and relist the (still-RESERVED) vehicle.
        cur.execute('''
            INSERT INTO carpark_reservations
                (vehicle_id, client_name, reservation_start, reservation_end, status, user_id)
            VALUES (%s, %s, %s, %s, 'active', NULL)
            RETURNING id
        ''', (ids['vehicle_id'], 'Overdue Client',
              today - timedelta(days=10), today - timedelta(days=1)))
        ids['reservation_id'] = cur.fetchone()['id']

        conn.commit()
        yield ids
    finally:
        try:
            cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (SCHED_COMPANY_ID,))
            conn.commit()
            cur.execute('SELECT COUNT(*) AS cnt FROM carpark_vehicles WHERE company_id = %s',
                        (SCHED_COMPANY_ID,))
            remaining = cur.fetchone()['cnt']
        finally:
            release_db(conn)
        assert remaining == 0, (
            f'teardown left {remaining} orphan carpark_vehicles row(s) for '
            f'company_id={SCHED_COMPANY_ID}'
        )


def test_expire_reservations_real_db_unsticks_reserved_vehicle(reserved_expired_seed):
    """End-to-end: expire_reservations() marks the reservation 'expired' AND
    actually moves the vehicle RESERVED -> LISTED through the real
    via_dispo_action guard. Pre-fix this asserts-fail: the guard raised, the
    job swallowed it, and the vehicle stayed RESERVED."""
    from core.base_repository import BaseRepository

    vehicle_id = reserved_expired_seed['vehicle_id']
    reservation_id = reserved_expired_seed['reservation_id']

    # Scope the (globally-querying) job to just our seeded reservation.
    with patch(
        'carpark.repositories.reservation_repository.ReservationRepository.expired',
        return_value=[{'id': reservation_id, 'vehicle_id': vehicle_id, 'user_id': None}],
    ):
        job.expire_reservations()

    raw = BaseRepository()
    reservation_row = raw.query_one(
        'SELECT status FROM carpark_reservations WHERE id = %s', (reservation_id,))
    vehicle_row = raw.query_one(
        'SELECT status FROM carpark_vehicles WHERE id = %s', (vehicle_id,))

    # (a) reservation closed out...
    assert reservation_row['status'] == 'expired'
    # (b) ...AND the vehicle is really LISTED, not stuck at RESERVED (the fix).
    assert vehicle_row['status'] == 'LISTED'
