"""Real-DB integration test for the intake service's idempotent create —
Task 2 of the spine plan.

Feeds the same `Transport in derulare` jarvis-alpha event for order AW-2418
through `apply_event()` twice and asserts the second call is a no-op: one
vehicle, one Recepție task, second result == 'duplicate'.

Also covers the atomic-create fix (final review): the vehicle insert, task
insert, and `created` history row run inside one transaction, so a failure
on the second or third write must roll back the first too — otherwise a
vehicle with NO Recepție card is stranded (a retry hits
`handle_transport_in_derulare`'s `if existing: return 'duplicate'` guard,
which then permanently blocks the missing card from ever being created).

Runs against localhost/defaultdb via the probe in conftest.py; seeds under
the sentinel `company_id=990002` and tears down (cascade-deleting the task)
via the `logistics_cleanup` fixture.

Invocation:
    venv/bin/python -m pytest jarvis/tests/logistics/test_intake_create.py -v
"""
import pytest

from database import get_cursor, get_db, release_db
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


def _count_history_rows(company_id: int) -> int:
    """Raw count of logistics_vehicle_history rows for this sentinel
    company — used to prove NO partial history row survives a rolled-back
    create (there's no vehicle_id to look it up by once the vehicle insert
    itself has been rolled back)."""
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute(
            'SELECT COUNT(*) AS cnt FROM logistics_vehicle_history WHERE company_id = %s',
            (company_id,),
        )
        return cur.fetchone()['cnt']
    finally:
        release_db(conn)


def test_create_vehicle_task_history_atomic_on_failure(require_real_db, monkeypatch, logistics_cleanup):
    """Force the second write (task insert) to fail mid-transaction during a
    `Transport in derulare` apply_event — the vehicle insert that already
    ran on the SAME shared cursor must be rolled back too (fix for the
    non-atomic intake-create finding): no vehicle row, no history row."""
    order_ref = 'AW-ATOMIC-01'
    before_history_count = _count_history_rows(TEST_COMPANY_ID)

    def _boom(self, *args, **kwargs):
        raise RuntimeError('forced create_task failure')

    monkeypatch.setattr(TaskRepository, 'create_task', _boom)

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

    with pytest.raises(RuntimeError):
        apply_event(event)

    # Full rollback: no stranded vehicle with a missing Recepție card.
    vehicle = LogisticsVehicleRepository().get_vehicle_by_order_ref(order_ref, TEST_COMPANY_ID)
    assert vehicle is None

    # No partial `created` history row leaked either.
    assert _count_history_rows(TEST_COMPANY_ID) == before_history_count
