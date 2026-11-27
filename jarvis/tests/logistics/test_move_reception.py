"""Real-DB integration test for the Kanban move engine's Recepție ->
Finalizat gate ("Confirmă recepția") -- Task 9 of the spine plan.

Scenarios:
  1. A full reception ctx (vin/location_id/position_id/keys/condition) moves
     the task to Finalizat AND confirms vin/location_id/position_id onto the
     vehicle (set + marked `true` in confirmed_fields), flips etapa_parc out
     of 'În tranzit', and writes a dedicated `reception_confirmed` history
     row (alongside the generic `task_moved` one every move writes).
  2. Any missing/empty reception field -> MoveError('reception_incomplete'),
     raised BEFORE any write -- neither the task nor the vehicle changes.
  3. IDOR / integrity guard (FIX A): a location or position belonging to
     another company, a position that doesn't belong to the given location,
     or a non-positive id -> MoveError('reception_invalid_bay'), raised
     BEFORE any write -- task AND vehicle both untouched. (The "both
     untouched" assertion is also the regression lock for FIX B: the
     reception success path is one atomic transaction, so a rejected move
     can never half-apply.)
  4. Ordering-guard regression (ties to Task 4, NOT confirmed_fields): once a
     bay is confirmed, a later-arriving but chronologically OLDER intake
     event is dropped by `apply_event`'s `event_ts` ordering guard
     (`_is_stale_event`) before any handler runs, so the confirmed
     position_id survives. This is what actually protects the bay in the
     current spine -- `confirmed_fields` is defensive for a future handler
     that updates an existing vehicle (its filter is unit-proven separately
     by test_intake_stale.py::test_apply_confirmed_guard_strips_only_
     confirmed_fields); no intake handler in the current spine updates an
     existing vehicle's columns.

Runs against localhost/defaultdb via the probe in conftest.py; seeds under
the sentinel `company_id=990002`. `logistics_cleanup` cascade-deletes
logistics_vehicles (-> tasks/history); the location/position rows this file
needs (to satisfy location_id/position_id's FKs, and across two companies
for the IDOR tests) are created/deleted by the local `bay`/`yard` fixtures
below, mirroring test_intake_stale.py's pattern.

Invocation:
    DATABASE_URL=postgresql://localhost/defaultdb \
        venv/bin/python -m pytest jarvis/tests/logistics/test_move_reception.py -v
"""
import uuid
from types import SimpleNamespace

import pytest

from database import get_cursor, get_db, release_db
from logistics.repositories.history_repository import HistoryRepository
from logistics.repositories.location_repository import LocationRepository, PositionRepository
from logistics.repositories.task_repository import TaskRepository
from logistics.repositories.vehicle_repository import LogisticsVehicleRepository
from logistics.services.intake import apply_event
from logistics.services.moves import MoveError, move_task

from .conftest import TEST_COMPANY_ID

# A second sentinel company for the cross-tenant IDOR tests -- a location/bay
# owned by THIS company must never be accepted for a TEST_COMPANY_ID task.
_OTHER_COMPANY_ID = 990003


@pytest.fixture
def bay(require_real_db):
    """One real logistics_locations + logistics_positions row under
    TEST_COMPANY_ID -- the valid-bay FK targets the happy-path and
    ordering-guard tests need. Deleted after the test: `logistics_cleanup`
    only cascades from logistics_vehicles, which never reaches
    logistics_locations/logistics_positions.

    `code` is globally UNIQUE on both tables, and the sentinel company_id is
    shared across worktrees against the same localhost DB (per repo
    convention), so a fixed literal could collide with a concurrent run --
    suffix with a fresh uuid to make this fixture self-isolating.
    """
    location_repo = LocationRepository()
    position_repo = PositionRepository()

    suffix = uuid.uuid4().hex[:8]
    location = location_repo.create_location({
        'name': 'Test Yard (reception)',
        'code': f'TST-RECEP-{suffix}',
        'company_id': TEST_COMPANY_ID,
    })
    position = position_repo.create_position({
        'location_id': location['id'],
        'code': f'A-RECEP-{suffix}',
        'company_id': TEST_COMPANY_ID,
    })
    try:
        yield position
    finally:
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute('DELETE FROM logistics_positions WHERE id = %s', (position['id'],))
            cur.execute('DELETE FROM logistics_locations WHERE id = %s', (location['id'],))
            conn.commit()
        finally:
            release_db(conn)


@pytest.fixture
def yard(require_real_db):
    """Factory for ad-hoc locations/positions (any company) used by the IDOR
    tests, with bookkeeping teardown. `make_location`/`make_position` register
    every row they create; teardown deletes positions first, then locations
    (FK order). Listed BEFORE `logistics_cleanup` in a test signature so it
    tears down AFTER it -- though the IDOR tests never attach a vehicle to
    these rows (reception is rejected), so there's no FK dependency to honour.
    """
    created_positions: list[int] = []
    created_locations: list[int] = []
    location_repo = LocationRepository()
    position_repo = PositionRepository()

    def make_location(company_id=TEST_COMPANY_ID):
        suffix = uuid.uuid4().hex[:8]
        location = location_repo.create_location({
            'name': f'Yard {suffix}',
            'code': f'TST-YARD-{suffix}',
            'company_id': company_id,
        })
        created_locations.append(location['id'])
        return location

    def make_position(location_id, company_id=TEST_COMPANY_ID):
        suffix = uuid.uuid4().hex[:8]
        position = position_repo.create_position({
            'location_id': location_id,
            'code': f'A-YARD-{suffix}',
            'company_id': company_id,
        })
        created_positions.append(position['id'])
        return position

    try:
        yield SimpleNamespace(make_location=make_location, make_position=make_position)
    finally:
        conn = get_db()
        try:
            cur = get_cursor(conn)
            for pid in created_positions:
                cur.execute('DELETE FROM logistics_positions WHERE id = %s', (pid,))
            for lid in created_locations:
                cur.execute('DELETE FROM logistics_locations WHERE id = %s', (lid,))
            conn.commit()
        finally:
            release_db(conn)


def _create_vehicle_and_reception_task(order_ref, event_ts=1000):
    """Stand up a vehicle + its open Recepție task through the real intake
    pipeline (`apply_event`), not a direct repo insert -- mirrors how a card
    actually lands on the board, and gives the vehicle a real
    `last_event_ts` for the ordering-guard scenario."""
    created = apply_event({
        'order_ref': order_ref,
        'code': 'Transport in derulare',
        'event_ts': event_ts,
        'payload': {'company_id': TEST_COMPANY_ID, 'destinatie': 'Intern'},
    })
    assert created['result'] == 'created'
    task = TaskRepository().get_open_reception_task(created['vehicle_id'])
    return created['vehicle_id'], task


def _reception_ctx(location_id, position_id):
    return {
        'reception': {
            'vin': 'WVWZZZ1KZAW000001',
            'location_id': location_id,
            'position_id': position_id,
            'keys': 2,
            'condition': 'Bună',
        },
    }


def _assert_untouched(task_id, vehicle_id):
    """The whole-move rollback invariant for every rejection case: the task
    stays in its starting column AND the vehicle keeps its pre-reception
    state (no bay, nothing confirmed, still in transit)."""
    assert TaskRepository().get_task_by_id(task_id)['status'] == 'De făcut'
    vehicle = LogisticsVehicleRepository().get_vehicle_by_id(vehicle_id)
    assert vehicle['vin'] is None
    assert vehicle['location_id'] is None
    assert vehicle['position_id'] is None
    assert vehicle['confirmed_fields'] == {}
    assert vehicle['etapa_parc'] == 'În tranzit'


def test_confirm_reception_sets_and_confirms_vehicle_fields(require_real_db, bay, logistics_cleanup):
    vehicle_id, task = _create_vehicle_and_reception_task('AW-RECEP-01')
    history_repo = HistoryRepository()

    result = move_task(task['id'], 'Finalizat', _reception_ctx(bay['location_id'], bay['id']))

    assert result['status'] == 'Finalizat'

    # Persisted, not just the returned task dict.
    persisted_task = TaskRepository().get_task_by_id(task['id'])
    assert persisted_task['status'] == 'Finalizat'

    vehicle = LogisticsVehicleRepository().get_vehicle_by_id(vehicle_id)
    assert vehicle['vin'] == 'WVWZZZ1KZAW000001'
    assert vehicle['location_id'] == bay['location_id']
    assert vehicle['position_id'] == bay['id']
    assert vehicle['confirmed_fields']['vin'] is True
    assert vehicle['confirmed_fields']['location_id'] is True
    assert vehicle['confirmed_fields']['position_id'] is True
    assert vehicle['etapa_parc'] != 'În tranzit'

    history_rows = history_repo.list_history_for_vehicle(vehicle_id)
    reception_rows = [h for h in history_rows if h['event_type'] == 'reception_confirmed']
    assert len(reception_rows) == 1
    assert reception_rows[0]['new_value']['vin'] == 'WVWZZZ1KZAW000001'
    assert reception_rows[0]['new_value']['location_id'] == bay['location_id']
    assert reception_rows[0]['new_value']['position_id'] == bay['id']
    assert reception_rows[0]['new_value']['keys'] == 2
    assert reception_rows[0]['new_value']['condition'] == 'Bună'

    # The generic task_moved row is still written -- Task 9 adds a history
    # entry, it doesn't replace the one every move already writes.
    moved_rows = [h for h in history_rows if h['event_type'] == 'task_moved']
    assert len(moved_rows) == 1


def test_reception_incomplete_rejected(require_real_db, bay, logistics_cleanup):
    vehicle_id, task = _create_vehicle_and_reception_task('AW-RECEP-02')
    ctx = _reception_ctx(bay['location_id'], bay['id'])
    del ctx['reception']['condition']  # one field missing

    with pytest.raises(MoveError) as excinfo:
        move_task(task['id'], 'Finalizat', ctx)
    assert excinfo.value.code == 'reception_incomplete'

    _assert_untouched(task['id'], vehicle_id)


def test_reception_cross_company_location_rejected(require_real_db, yard, logistics_cleanup):
    """FIX A — a location (and its bay) owned by ANOTHER company must not be
    writable onto a TEST_COMPANY_ID vehicle (cross-tenant IDOR)."""
    vehicle_id, task = _create_vehicle_and_reception_task('AW-RECEP-10')
    other_location = yard.make_location(company_id=_OTHER_COMPANY_ID)
    other_position = yard.make_position(other_location['id'], company_id=_OTHER_COMPANY_ID)

    with pytest.raises(MoveError) as excinfo:
        move_task(task['id'], 'Finalizat', _reception_ctx(other_location['id'], other_position['id']))
    assert excinfo.value.code == 'reception_invalid_bay'

    _assert_untouched(task['id'], vehicle_id)


def test_reception_cross_company_position_rejected(require_real_db, yard, logistics_cleanup):
    """FIX A — even when the location is the caller's own, a position row
    owned by another company must be rejected."""
    vehicle_id, task = _create_vehicle_and_reception_task('AW-RECEP-11')
    location = yard.make_location(company_id=TEST_COMPANY_ID)
    foreign_position = yard.make_position(location['id'], company_id=_OTHER_COMPANY_ID)

    with pytest.raises(MoveError) as excinfo:
        move_task(task['id'], 'Finalizat', _reception_ctx(location['id'], foreign_position['id']))
    assert excinfo.value.code == 'reception_invalid_bay'

    _assert_untouched(task['id'], vehicle_id)


def test_reception_position_not_in_location_rejected(require_real_db, yard, logistics_cleanup):
    """FIX A — a position that belongs to a DIFFERENT location than the one
    supplied is an integrity mismatch, rejected even when both are the
    caller's own company."""
    vehicle_id, task = _create_vehicle_and_reception_task('AW-RECEP-12')
    location_a = yard.make_location(company_id=TEST_COMPANY_ID)
    location_b = yard.make_location(company_id=TEST_COMPANY_ID)
    position_b = yard.make_position(location_b['id'], company_id=TEST_COMPANY_ID)

    with pytest.raises(MoveError) as excinfo:
        move_task(task['id'], 'Finalizat', _reception_ctx(location_a['id'], position_b['id']))
    assert excinfo.value.code == 'reception_invalid_bay'

    _assert_untouched(task['id'], vehicle_id)


def test_reception_non_positive_bay_rejected(require_real_db, logistics_cleanup):
    """FIX A — 0 / negative ids are rejected before any DB lookup (also
    closes the old `0`-accepted gap `_require_reception_fields` had)."""
    vehicle_id, task = _create_vehicle_and_reception_task('AW-RECEP-13')

    for location_id, position_id in [(0, 5), (-1, 5), (5, 0), (5, -3)]:
        with pytest.raises(MoveError) as excinfo:
            move_task(task['id'], 'Finalizat', _reception_ctx(location_id, position_id))
        assert excinfo.value.code == 'reception_invalid_bay'

    _assert_untouched(task['id'], vehicle_id)


def test_older_intake_event_after_confirm_preserves_bay(require_real_db, bay, logistics_cleanup):
    """Ordering-guard regression (NOT a confirmed_fields test). After the bay
    is confirmed, an older-than-last intake event for the same order is
    dropped by `apply_event`'s `event_ts` guard before any handler runs, so
    the confirmed position_id survives. (`confirmed_fields` is proven
    separately as a pure filter in test_intake_stale.py; no handler in the
    current spine updates an existing vehicle for it to protect against.)"""
    order_ref = 'AW-RECEP-03'
    vehicle_id, task = _create_vehicle_and_reception_task(order_ref, event_ts=1000)

    move_task(task['id'], 'Finalizat', _reception_ctx(bay['location_id'], bay['id']))

    confirmed_vehicle = LogisticsVehicleRepository().get_vehicle_by_id(vehicle_id)
    assert confirmed_vehicle['position_id'] == bay['id']

    stale_result = apply_event({
        'order_ref': order_ref,
        'code': 'Transport in derulare',
        'event_ts': 500,  # older than last_event_ts=1000 stamped at creation
        'payload': {
            'company_id': TEST_COMPANY_ID,
            'destinatie': 'Extern',
            # A different bay -- never applied, since the ordering guard must
            # stop this event before anything downstream touches the row.
            'position_id': bay['id'] + 999999,
        },
    })
    assert stale_result['result'] == 'ignored'

    final_vehicle = LogisticsVehicleRepository().get_vehicle_by_id(vehicle_id)
    assert final_vehicle['position_id'] == bay['id']  # unchanged
