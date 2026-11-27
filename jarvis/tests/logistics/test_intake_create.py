"""Real-DB integration test for the intake service's idempotent create —
Task 2 of the spine plan.

Feeds the same `Transport in derulare` jarvis-alpha event for order AW-2418
through `apply_event()` twice and asserts the second call is a no-op: one
vehicle, one Recepție task, second result == 'duplicate'.

Runs against localhost/defaultdb via the probe in conftest.py; seeds under
the sentinel `company_id=990002` and tears down (cascade-deleting the task)
via the `logistics_cleanup` fixture.

Invocation:
    venv/bin/python -m pytest jarvis/tests/logistics/test_intake_create.py -v
"""
from logistics.repositories.task_repository import TaskRepository
from logistics.repositories.vehicle_repository import LogisticsVehicleRepository
from logistics.services.intake import apply_event

from .conftest import TEST_COMPANY_ID


def test_double_transport_event_creates_one_vehicle_one_reception(require_real_db, logistics_cleanup):
    vehicle_repo = LogisticsVehicleRepository()
    task_repo = TaskRepository()

    order_ref = 'AW-2418'
    event = {
        'order_ref': order_ref,
        'code': 'Transport in derulare',
        'event_ts': 1732600000,
        'payload': {
            'company_id': TEST_COMPANY_ID,
            'destinatie': 'Intern',
            'eta': '2026-12-01T10:00:00',
        },
    }

    first = apply_event(event)
    assert first['result'] == 'created'
    assert first.get('vehicle_id') is not None
    assert first.get('task_id') is not None

    second = apply_event(event)
    assert second['result'] == 'duplicate'

    vehicle = vehicle_repo.get_vehicle_by_order_ref(order_ref, TEST_COMPANY_ID)
    assert vehicle is not None
    assert vehicle['id'] == first['vehicle_id']
    assert vehicle['etapa_parc'] == 'În tranzit'
    assert vehicle['destinatie'] == 'Intern'

    tasks = task_repo.list_tasks({'vehicle_id': vehicle['id'], 'type': 'Recepție'})
    assert len(tasks) == 1
    assert tasks[0]['action'] == 'Recepționează mașina'
    assert tasks[0]['status'] == 'De făcut'
    assert tasks[0]['id'] == first['task_id']
