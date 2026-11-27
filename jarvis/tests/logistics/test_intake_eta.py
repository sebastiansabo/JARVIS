"""Real-DB integration test for the intake service's `ETA actualizat` rule —
Task 3 of the spine plan.

Two scenarios:
  1. An ETA update for an order that already has an open Recepție card
     (created earlier by `Transport in derulare`) must update that same
     card's due_at in place — never create a second Recepție task.
  2. An ETA update for an order jarvis-alpha hasn't mentioned before (no
     vehicle row yet) is a first-seen upsert: create the vehicle + its
     Recepție task, same as `Transport in derulare` would, just with the
     ETA already attached.

Also covers the atomic-update fix (final review): the update branch's task
due_at update, optional vehicle last_event_ts stamp, and `eta_updated`
history row run inside one transaction, so a failure partway through must
roll back the task's due_at change too — otherwise a card could show a new
ETA with no audit row proving it (or vice versa).

Runs against localhost/defaultdb via the probe in conftest.py; seeds under
the sentinel `company_id=990002` and tears down via the `logistics_cleanup`
fixture (cascade-deletes tasks/history).

Invocation:
    DATABASE_URL=postgresql://localhost/defaultdb \
        venv/bin/python -m pytest jarvis/tests/logistics/test_intake_eta.py -v
"""
import pytest

from logistics.repositories.history_repository import HistoryRepository
from logistics.repositories.task_repository import TaskRepository
from logistics.repositories.vehicle_repository import LogisticsVehicleRepository
from logistics.services.intake import apply_event

from .conftest import TEST_COMPANY_ID


def test_eta_updates_same_card(require_real_db, logistics_cleanup):
    vehicle_repo = LogisticsVehicleRepository()
    task_repo = TaskRepository()

    order_ref = 'AW-2419'
    created_event = {
        'order_ref': order_ref,
        'code': 'Transport in derulare',
        'event_ts': 1732600000,
        'payload': {
            'company_id': TEST_COMPANY_ID,
            'destinatie': 'Intern',
            'eta': '2026-12-01T10:00:00',
        },
    }
    created = apply_event(created_event)
    assert created['result'] == 'created'

    eta_event = {
        'order_ref': order_ref,
        'code': 'ETA actualizat',
        'event_ts': 1732600500,
        'payload': {
            'company_id': TEST_COMPANY_ID,
            'eta': '2026-12-03T15:30:00',
        },
    }
    updated = apply_event(eta_event)
    assert updated['result'] == 'updated'
    assert updated['vehicle_id'] == created['vehicle_id']
    assert updated['task_id'] == created['task_id']

    vehicle = vehicle_repo.get_vehicle_by_order_ref(order_ref, TEST_COMPANY_ID)
    tasks = task_repo.list_tasks({'vehicle_id': vehicle['id'], 'type': 'Recepție'})
    assert len(tasks) == 1
    assert tasks[0]['id'] == created['task_id']
    assert tasks[0]['due_at'] == '2026-12-03T15:30:00'


def test_eta_for_unknown_order_upserts(require_real_db, logistics_cleanup):
    vehicle_repo = LogisticsVehicleRepository()
    task_repo = TaskRepository()

    order_ref = 'AW-2420'
    eta_event = {
        'order_ref': order_ref,
        'code': 'ETA actualizat',
        'event_ts': 1732600000,
        'payload': {
            'company_id': TEST_COMPANY_ID,
            'destinatie': 'Extern',
            'eta': '2026-12-05T09:00:00',
        },
    }

    result = apply_event(eta_event)
    assert result['result'] == 'created'
    assert result.get('vehicle_id') is not None
    assert result.get('task_id') is not None

    vehicle = vehicle_repo.get_vehicle_by_order_ref(order_ref, TEST_COMPANY_ID)
    assert vehicle is not None
    assert vehicle['id'] == result['vehicle_id']
    assert vehicle['etapa_parc'] == 'În tranzit'
    assert vehicle['destinatie'] == 'Extern'

    tasks = task_repo.list_tasks({'vehicle_id': vehicle['id'], 'type': 'Recepție'})
    assert len(tasks) == 1
    assert tasks[0]['id'] == result['task_id']
    assert tasks[0]['due_at'] == '2026-12-05T09:00:00'


def test_eta_for_known_order_without_open_task_is_ignored(require_real_db, logistics_cleanup):
    task_repo = TaskRepository()
    history_repo = HistoryRepository()

    order_ref = 'AW-2421'
    created = apply_event({
        'order_ref': order_ref,
        'code': 'Transport in derulare',
        'event_ts': 1732600000,
        'payload': {
            'company_id': TEST_COMPANY_ID,
            'destinatie': 'Intern',
            'eta': '2026-12-01T10:00:00',
        },
    })
    assert created['result'] == 'created'

    # Close the Recepție card so the order has no open task left.
    task_repo.update_task(created['task_id'], {'status': 'Finalizat'})

    result = apply_event({
        'order_ref': order_ref,
        'code': 'ETA actualizat',
        'event_ts': 1732600500,
        'payload': {
            'company_id': TEST_COMPANY_ID,
            'eta': '2026-12-04T12:00:00',
        },
    })
    assert result['result'] == 'ignored'
    assert result['vehicle_id'] == created['vehicle_id']
    assert result['task_id'] is None

    # No second Recepție card was created.
    tasks = task_repo.list_tasks({'vehicle_id': created['vehicle_id'], 'type': 'Recepție'})
    assert len(tasks) == 1
    assert tasks[0]['id'] == created['task_id']

    # The late ETA push is still captured in the audit trail.
    history = history_repo.list_history_for_vehicle(created['vehicle_id'])
    no_task_rows = [h for h in history if h['event_type'] == 'eta_no_open_task']
    assert len(no_task_rows) == 1
    assert no_task_rows[0]['new_value'] == {'eta': '2026-12-04T12:00:00'}


def test_eta_update_atomic_on_vehicle_write_failure(require_real_db, monkeypatch, logistics_cleanup):
    """Force the vehicle-update step (last_event_ts stamp) to fail
    mid-transaction during `handle_eta_actualizat`'s update branch — the
    task due_at write that already ran on the SAME shared cursor must be
    rolled back too (fix for the non-atomic ETA-update finding): due_at
    stays at the old value, last_event_ts stays at the old value, and no
    `eta_updated` history row is written."""
    task_repo = TaskRepository()
    vehicle_repo = LogisticsVehicleRepository()
    history_repo = HistoryRepository()

    order_ref = 'AW-ATOMIC-02'
    created = apply_event({
        'order_ref': order_ref,
        'code': 'Transport in derulare',
        'event_ts': 1000,
        'payload': {
            'company_id': TEST_COMPANY_ID,
            'destinatie': 'Intern',
            'eta': '2026-12-01T10:00:00',
        },
    })
    assert created['result'] == 'created'

    def _boom(self, *args, **kwargs):
        raise RuntimeError('forced update_vehicle failure')

    monkeypatch.setattr(LogisticsVehicleRepository, 'update_vehicle', _boom)

    with pytest.raises(RuntimeError):
        apply_event({
            'order_ref': order_ref,
            'code': 'ETA actualizat',
            # Newer than 1000 (not stale) so the last_event_ts stamp is
            # actually attempted -- that's the write forced to fail here.
            'event_ts': 2000,
            'payload': {
                'company_id': TEST_COMPANY_ID,
                'eta': '2026-12-05T09:00:00',
            },
        })

    # Rollback: the task's due_at was never committed to the new ETA.
    task = task_repo.get_task_by_id(created['task_id'])
    assert task['due_at'] == '2026-12-01T10:00:00'

    # Rollback: the vehicle's last_event_ts was never committed either.
    vehicle = vehicle_repo.get_vehicle_by_id(created['vehicle_id'])
    assert vehicle['last_event_ts'] == 1000

    # No partial `eta_updated` history row leaked.
    history = history_repo.list_history_for_vehicle(created['vehicle_id'])
    eta_updated_rows = [h for h in history if h['event_type'] == 'eta_updated']
    assert len(eta_updated_rows) == 0
