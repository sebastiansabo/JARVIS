"""Real-DB integration test for the Kanban move engine's Îngrijire ->
Finalizat gate (measured-result requirement) -- Task 10 of the spine plan.

Scenarios:
  1. Finalizing an Îngrijire task (e.g. a 12V battery check) with no
     ctx['measured'] -> MoveError('measured_result_required'), raised
     BEFORE any write -- the task stays exactly where it was.
  2. A valid {value, unit} measurement -> status flips to Finalizat,
     measured_result is persisted on the task, and a dedicated
     `care_measured` history row is written.
  3. (edge) a non-numeric/boolean value, or an empty/missing unit, is
     rejected the same way as a missing ctx['measured'] entirely.

Runs against localhost/defaultdb via the probe in conftest.py; seeds under
the sentinel `company_id=990002`. `logistics_cleanup` cascade-deletes
logistics_vehicles (-> tasks/history).

Invocation:
    DATABASE_URL=postgresql://localhost/defaultdb \
        venv/bin/python -m pytest jarvis/tests/logistics/test_move_measured.py -v
"""
import pytest

from logistics.repositories.history_repository import HistoryRepository
from logistics.repositories.task_repository import TaskRepository
from logistics.repositories.vehicle_repository import LogisticsVehicleRepository
from logistics.services.moves import MoveError, move_task

from .conftest import TEST_COMPANY_ID


@pytest.fixture
def vehicle_and_care_task(require_real_db, logistics_cleanup):
    """One real vehicle + its Îngrijire task, under the sentinel company --
    the minimum fixture every measured-result test needs. Mirrors
    test_move_blocat.py's vehicle_and_task fixture (direct repo creation,
    no need to go through the intake pipeline for a care task)."""
    vehicle_repo = LogisticsVehicleRepository()
    task_repo = TaskRepository()

    vehicle = vehicle_repo.create_vehicle({
        'order_ref': 'AW-CARE-01',
        'destinatie': 'Intern',
        'etapa_parc': 'În pregătire',
        'company_id': TEST_COMPANY_ID,
    })
    task = task_repo.create_task({
        'vehicle_id': vehicle['id'],
        'action': 'Verifică baterie 12V',
        'type': 'Îngrijire',
        'status': 'În lucru',
        'company_id': TEST_COMPANY_ID,
    })
    return vehicle, task


def test_finalize_battery_without_measurement_rejected(vehicle_and_care_task):
    _vehicle, task = vehicle_and_care_task
    task_repo = TaskRepository()

    with pytest.raises(MoveError) as excinfo:
        move_task(task['id'], 'Finalizat', {})
    assert excinfo.value.code == 'measured_result_required'

    unchanged = task_repo.get_task_by_id(task['id'])
    assert unchanged['status'] == 'În lucru'
    assert unchanged['measured_result'] is None


def test_finalize_battery_with_12v_reading_stores_measurement(vehicle_and_care_task):
    vehicle, task = vehicle_and_care_task
    history_repo = HistoryRepository()

    result = move_task(task['id'], 'Finalizat', {'measured': {'value': 12.4, 'unit': 'V'}})

    assert result['status'] == 'Finalizat'
    assert result['measured_result'] == {'value': 12.4, 'unit': 'V'}

    # Persisted, not just the returned task dict.
    persisted = TaskRepository().get_task_by_id(task['id'])
    assert persisted['status'] == 'Finalizat'
    assert persisted['measured_result'] == {'value': 12.4, 'unit': 'V'}

    history_rows = history_repo.list_history_for_vehicle(vehicle['id'])
    care_rows = [h for h in history_rows if h['event_type'] == 'care_measured']
    assert len(care_rows) == 1
    assert care_rows[0]['new_value']['value'] == 12.4
    assert care_rows[0]['new_value']['unit'] == 'V'
    assert care_rows[0]['new_value']['status'] == 'Finalizat'

    # Unlike the reception gate, there is no separate generic task_moved
    # row for this path -- care_measured IS the move's one history entry.
    moved_rows = [h for h in history_rows if h['event_type'] == 'task_moved']
    assert len(moved_rows) == 0


@pytest.mark.parametrize('measured', [
    {'value': 'twelve', 'unit': 'V'},  # non-numeric value
    {'value': True, 'unit': 'V'},      # bool -- not a real number
    {'value': 12.4, 'unit': ''},       # empty unit
    {'value': 12.4, 'unit': '   '},    # whitespace-only unit
    {'value': 12.4},                   # missing unit
    {'unit': 'V'},                     # missing value
])
def test_finalize_battery_with_invalid_measurement_rejected(vehicle_and_care_task, measured):
    _vehicle, task = vehicle_and_care_task
    task_repo = TaskRepository()

    with pytest.raises(MoveError) as excinfo:
        move_task(task['id'], 'Finalizat', {'measured': measured})
    assert excinfo.value.code == 'measured_result_required'

    unchanged = task_repo.get_task_by_id(task['id'])
    assert unchanged['status'] == 'În lucru'
    assert unchanged['measured_result'] is None


def test_non_care_task_unaffected_by_measured_gate(vehicle_and_care_task):
    """Regression guard: a Recepție-type task moving to Finalizat (Task 9's
    own gate) must not be rerouted through the measured-result gate just
    because it's also heading to Finalizat -- the gate is keyed off
    task['type'], not to_status alone."""
    vehicle, _care_task = vehicle_and_care_task
    task_repo = TaskRepository()
    other_task = task_repo.create_task({
        'vehicle_id': vehicle['id'],
        'action': 'Altă sarcină',
        'type': 'Transport',
        'status': 'În lucru',
        'company_id': TEST_COMPANY_ID,
    })

    result = move_task(other_task['id'], 'Finalizat', {})
    assert result['status'] == 'Finalizat'
    assert result['measured_result'] is None
