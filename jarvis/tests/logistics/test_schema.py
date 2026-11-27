"""Real-DB integration test for the JARVIS Parc (logistics) schema — Task 1
of the spine plan.

Creates a vehicle + a task via the repositories and reads them back, then
asserts that a second vehicle with the same order_ref raises a
unique-violation (logistics_vehicles.order_ref is UNIQUE NOT NULL).

Runs against localhost/defaultdb via the probe in conftest.py (which drops
jarvis/conftest.py's psycopg2 mock, rebinds the real driver, and bootstraps
the logistics_* tables since they don't exist on the dev DB yet). Depends on
`require_real_db` + `logistics_cleanup` (both in conftest.py); seeds under
the sentinel `company_id=990002` and tears down (cascade-deleting tasks/
history) in a `finally` block, asserting zero rows remain afterwards.

Invocation:
    venv/bin/python -m pytest jarvis/tests/logistics/test_schema.py -v
"""
import pytest

from logistics.repositories.task_repository import TaskRepository
from logistics.repositories.vehicle_repository import VehicleRepository

from .conftest import TEST_COMPANY_ID


def test_create_vehicle_and_task_then_read_back(require_real_db, logistics_cleanup):
    vehicle_repo = VehicleRepository()
    task_repo = TaskRepository()

    order_ref = 'AW-TEST-0001'
    created_vehicle = vehicle_repo.create_vehicle({
        'order_ref': order_ref,
        'model': 'Audi A4',
        'destinatie': 'Intern',
        'company_id': TEST_COMPANY_ID,
    })
    assert created_vehicle['id'] is not None
    assert created_vehicle['order_ref'] == order_ref
    assert created_vehicle['etapa_parc'] == 'În tranzit'
    assert created_vehicle['predare'] == 'În așteptare'
    assert created_vehicle['confirmed_fields'] == {}

    fetched_vehicle = vehicle_repo.get_vehicle_by_order_ref(order_ref, TEST_COMPANY_ID)
    assert fetched_vehicle is not None
    assert fetched_vehicle['id'] == created_vehicle['id']
    assert fetched_vehicle['model'] == 'Audi A4'

    created_task = task_repo.create_task({
        'vehicle_id': created_vehicle['id'],
        'action': 'Recepție auto',
        'type': 'Recepție',
        'company_id': TEST_COMPANY_ID,
    })
    assert created_task['id'] is not None
    assert created_task['vehicle_id'] == created_vehicle['id']
    assert created_task['status'] == 'De făcut'

    fetched_task = task_repo.get_task_by_id(created_task['id'])
    assert fetched_task is not None
    assert fetched_task['action'] == 'Recepție auto'

    open_reception_task = task_repo.get_open_reception_task(created_vehicle['id'])
    assert open_reception_task is not None
    assert open_reception_task['id'] == created_task['id']


def test_duplicate_order_ref_raises_unique_violation(require_real_db, logistics_cleanup):
    vehicle_repo = VehicleRepository()

    order_ref = 'AW-TEST-0002'
    vehicle_repo.create_vehicle({'order_ref': order_ref, 'company_id': TEST_COMPANY_ID})

    with pytest.raises(Exception):  # psycopg2.errors.UniqueViolation
        vehicle_repo.create_vehicle({'order_ref': order_ref, 'company_id': TEST_COMPANY_ID})
