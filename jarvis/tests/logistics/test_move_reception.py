"""Real-DB integration test for the Kanban move engine's Recepție ->
Finalizat gate ("Confirmă recepția") -- Task 9 of the spine plan.

Three scenarios:
  1. A full reception ctx (vin/location_id/position_id/keys/condition) moves
     the task to Finalizat AND confirms vin/location_id/position_id onto the
     vehicle (set + marked `true` in confirmed_fields), flips etapa_parc out
     of 'În tranzit', and writes a dedicated `reception_confirmed` history
     row (alongside the generic `task_moved` one every move writes).
  2. Any missing/empty reception field -> MoveError('reception_incomplete'),
     raised BEFORE any write -- neither the task nor the vehicle changes.
  3. END-TO-END regression tying this into Task 4's stale-event guard: once
     reception has confirmed a bay, a later-arriving but chronologically
     OLDER intake event must not be able to clobber it -- proving Task 9's
     vehicle write doesn't disturb `last_event_ts`, so the existing ordering
     guard in `logistics.services.intake.apply_event` still protects the
     confirmed position.

Runs against localhost/defaultdb via the probe in conftest.py; seeds under
the sentinel `company_id=990002`. `logistics_cleanup` cascade-deletes
logistics_vehicles (-> tasks/history); the location/position row this file
needs (to satisfy location_id/position_id's FKs) is created/deleted by the
local `bay` fixture below, mirroring test_intake_stale.py's pattern.

Invocation:
    DATABASE_URL=postgresql://localhost/defaultdb \
        venv/bin/python -m pytest jarvis/tests/logistics/test_move_reception.py -v
"""
import uuid

import pytest

from database import get_cursor, get_db, release_db
from logistics.repositories.history_repository import HistoryRepository
from logistics.repositories.location_repository import LocationRepository, PositionRepository
from logistics.repositories.task_repository import TaskRepository
from logistics.repositories.vehicle_repository import LogisticsVehicleRepository
from logistics.services.intake import apply_event
from logistics.services.moves import MoveError, move_task

from .conftest import TEST_COMPANY_ID


@pytest.fixture
def bay(require_real_db):
    """One real logistics_locations + logistics_positions row -- the FK
    targets logistics_vehicles.location_id/position_id need (reception
    always sets both). Deleted after the test: `logistics_cleanup` only
    cascades from logistics_vehicles, which never reaches
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


def _create_vehicle_and_reception_task(order_ref, event_ts=1000):
    """Stand up a vehicle + its open Recepție task through the real intake
    pipeline (`apply_event`), not a direct repo insert -- mirrors how a card
    actually lands on the board, and gives the vehicle a real
    `last_event_ts` for scenario 3's stale-guard check."""
    created = apply_event({
        'order_ref': order_ref,
        'code': 'Transport in derulare',
        'event_ts': event_ts,
        'payload': {'company_id': TEST_COMPANY_ID, 'destinatie': 'Intern'},
    })
    assert created['result'] == 'created'
    task = TaskRepository().get_open_reception_task(created['vehicle_id'])
    return created['vehicle_id'], task


def _reception_ctx(position):
    return {
        'reception': {
            'vin': 'WVWZZZ1KZAW000001',
            'location_id': position['location_id'],
            'position_id': position['id'],
            'keys': 2,
            'condition': 'Bună',
        },
    }


def test_confirm_reception_sets_and_confirms_vehicle_fields(require_real_db, bay, logistics_cleanup):
    vehicle_id, task = _create_vehicle_and_reception_task('AW-RECEP-01')
    history_repo = HistoryRepository()

    result = move_task(task['id'], 'Finalizat', _reception_ctx(bay))

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
    ctx = _reception_ctx(bay)
    del ctx['reception']['condition']  # one field missing

    with pytest.raises(MoveError) as excinfo:
        move_task(task['id'], 'Finalizat', ctx)
    assert excinfo.value.code == 'reception_incomplete'

    unchanged_task = TaskRepository().get_task_by_id(task['id'])
    assert unchanged_task['status'] == 'De făcut'

    unchanged_vehicle = LogisticsVehicleRepository().get_vehicle_by_id(vehicle_id)
    assert unchanged_vehicle['vin'] is None
    assert unchanged_vehicle['position_id'] is None
    assert unchanged_vehicle['confirmed_fields'] == {}
    assert unchanged_vehicle['etapa_parc'] == 'În tranzit'


def test_older_intake_event_after_confirm_preserves_bay(require_real_db, bay, logistics_cleanup):
    order_ref = 'AW-RECEP-03'
    vehicle_id, task = _create_vehicle_and_reception_task(order_ref, event_ts=1000)

    move_task(task['id'], 'Finalizat', _reception_ctx(bay))

    confirmed_vehicle = LogisticsVehicleRepository().get_vehicle_by_id(vehicle_id)
    assert confirmed_vehicle['position_id'] == bay['id']

    stale_result = apply_event({
        'order_ref': order_ref,
        'code': 'Transport in derulare',
        'event_ts': 500,  # older than last_event_ts=1000 stamped at creation
        'payload': {
            'company_id': TEST_COMPANY_ID,
            'destinatie': 'Extern',
            # A different bay -- never applied, since the stale guard must
            # stop this event before anything downstream touches the row.
            'position_id': bay['id'] + 999999,
        },
    })
    assert stale_result['result'] == 'ignored'

    final_vehicle = LogisticsVehicleRepository().get_vehicle_by_id(vehicle_id)
    assert final_vehicle['position_id'] == bay['id']  # unchanged
