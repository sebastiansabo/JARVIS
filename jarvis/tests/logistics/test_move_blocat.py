"""Real-DB integration test for the Kanban move engine's Blocat gate —
Task 8 of the spine plan.

Two scenarios:
  1. Moving a task to `Blocat` without both a responsible person AND a next
     action must be rejected with `MoveError` before anything is written —
     the card stays exactly where it was (design spec §4.2 review focus:
     "Blocat without a next action -> move rejected, card stays put").
  2. Moving a task to `Blocat` WITH both fields must set `status`,
     `block_reason`, `block_next_action` on the task AND write one
     `logistics_vehicle_history` `task_moved` row -- the full audit trail
     requirement every successful move must satisfy.

Runs against localhost/defaultdb via the probe in conftest.py; seeds under
the sentinel `company_id=990002`. `logistics_cleanup` cascade-deletes
logistics_vehicles (-> tasks/history).

Invocation:
    DATABASE_URL=postgresql://localhost/defaultdb \
        venv/bin/python -m pytest jarvis/tests/logistics/test_move_blocat.py -v
"""
import pytest

from logistics.repositories.history_repository import HistoryRepository
from logistics.repositories.task_repository import TaskRepository
from logistics.repositories.vehicle_repository import LogisticsVehicleRepository
from logistics.services.moves import MoveError, move_task

from .conftest import TEST_COMPANY_ID


@pytest.fixture
def vehicle_and_task(require_real_db, logistics_cleanup):
    """One real vehicle + its Recepție task, under the sentinel company —
    the minimum fixture every move_task() test needs."""
    vehicle_repo = LogisticsVehicleRepository()
    task_repo = TaskRepository()

    vehicle = vehicle_repo.create_vehicle({
        'order_ref': 'AW-MOVE-01',
        'destinatie': 'Intern',
        'etapa_parc': 'În tranzit',
        'company_id': TEST_COMPANY_ID,
    })
    task = task_repo.create_task({
        'vehicle_id': vehicle['id'],
        'action': 'Recepționează mașina',
        'type': 'Recepție',
        'company_id': TEST_COMPANY_ID,
    })
    return vehicle, task


def test_block_without_next_action_rejected(vehicle_and_task):
    _vehicle, task = vehicle_and_task
    task_repo = TaskRepository()

    with pytest.raises(MoveError) as excinfo:
        move_task(task['id'], 'Blocat', {})
    assert excinfo.value.code == 'block_requires_responsible_and_next_action'

    unchanged = task_repo.get_task_by_id(task['id'])
    assert unchanged['status'] == 'De făcut'
    assert unchanged['block_reason'] is None
    assert unchanged['block_next_action'] is None


def test_block_missing_one_of_the_two_fields_rejected(vehicle_and_task):
    """Both fields are required, not just "truthy ctx['block']" -- an empty
    next_action with a responsible set must still be rejected."""
    _vehicle, task = vehicle_and_task

    with pytest.raises(MoveError) as excinfo:
        move_task(task['id'], 'Blocat', {'block': {'responsible': 'Ion Pop', 'next_action': ''}})
    assert excinfo.value.code == 'block_requires_responsible_and_next_action'


def test_block_with_responsible_and_next_action_succeeds_and_logs_history(vehicle_and_task):
    vehicle, task = vehicle_and_task
    history_repo = HistoryRepository()

    result = move_task(task['id'], 'Blocat', {
        'block': {'responsible': 'Ion Pop', 'next_action': 'Comandă piesă de schimb'},
    })

    assert result['status'] == 'Blocat'
    assert result['block_reason'] == 'Ion Pop'
    assert result['block_next_action'] == 'Comandă piesă de schimb'

    # Persisted, not just the returned dict.
    task_repo = TaskRepository()
    persisted = task_repo.get_task_by_id(task['id'])
    assert persisted['status'] == 'Blocat'
    assert persisted['block_reason'] == 'Ion Pop'
    assert persisted['block_next_action'] == 'Comandă piesă de schimb'

    history_rows = history_repo.list_history_for_vehicle(vehicle['id'])
    moved_rows = [h for h in history_rows if h['event_type'] == 'task_moved']
    assert len(moved_rows) == 1
    assert moved_rows[0]['new_value']['status'] == 'Blocat'


def test_non_blocat_move_updates_status_and_logs_history(vehicle_and_task):
    """A plain status move (no gate) still writes status + history -- proves
    the engine isn't special-cased to only work for Blocat."""
    vehicle, task = vehicle_and_task
    history_repo = HistoryRepository()

    result = move_task(task['id'], 'În lucru', {})

    assert result['status'] == 'În lucru'

    history_rows = history_repo.list_history_for_vehicle(vehicle['id'])
    moved_rows = [h for h in history_rows if h['event_type'] == 'task_moved']
    assert len(moved_rows) == 1
    assert moved_rows[0]['old_value']['status'] == 'De făcut'
    assert moved_rows[0]['new_value']['status'] == 'În lucru'


def test_unknown_task_id_raises_value_error(require_real_db):
    with pytest.raises(ValueError):
        move_task(99999999, 'În lucru', {})
