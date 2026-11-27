"""Kanban board API — Task 7 of the spine plan (Panou de lucru).

Tests `TaskRepository.get_board(filters)` DIRECTLY against the real DB (same
pattern as test_vehicle_query.py) — the route in
jarvis/logistics/routes/tasks.py is a thin `@login_required` wrapper with no
SQL of its own; this suite is the actual query-logic coverage.

Runs against localhost/defaultdb via the probe in conftest.py; seeds under
the sentinel `company_id=990002` (TEST_COMPANY_ID) and relies on
`logistics_cleanup` to delete those rows before/after each test.

Invocation:
    DATABASE_URL=postgresql://localhost/defaultdb venv/bin/python -m pytest jarvis/tests/logistics/test_board.py -v
"""
from logistics.repositories.task_repository import TaskRepository
from logistics.repositories.vehicle_repository import LogisticsVehicleRepository

from .conftest import TEST_COMPANY_ID

# Fixed column order per the design spec §4.2 — get_board must return
# exactly these four keys, in exactly this order, every time (even when a
# column has no cards).
_BOARD_COLUMNS = ['De făcut', 'În lucru', 'Blocat', 'Finalizat']


def test_groups_tasks_into_four_columns_with_counts(require_real_db, logistics_cleanup):
    vrepo = LogisticsVehicleRepository()
    trepo = TaskRepository()

    vehicle = vrepo.create_vehicle({
        'order_ref': 'AW-TEST-7001', 'model': 'Audi A4',
        'company_id': TEST_COMPANY_ID,
    })

    trepo.create_task({
        'vehicle_id': vehicle['id'], 'action': 'Recepție programată',
        'type': 'Recepție', 'status': 'De făcut', 'assignee': 'Logistică',
        'company_id': TEST_COMPANY_ID,
    })
    trepo.create_task({
        'vehicle_id': vehicle['id'], 'action': 'Verificare baterie 12V',
        'type': 'Îngrijire', 'status': 'În lucru', 'assignee': 'Service',
        'company_id': TEST_COMPANY_ID,
    })
    trepo.create_task({
        'vehicle_id': vehicle['id'], 'action': 'Solicită certificatul de conformitate',
        'type': 'Documente', 'status': 'Blocat', 'assignee': 'Vânzări',
        'company_id': TEST_COMPANY_ID,
    })
    trepo.create_task({
        'vehicle_id': vehicle['id'], 'action': 'Predare client',
        'type': 'Predare', 'status': 'Finalizat', 'assignee': 'Vânzări',
        'company_id': TEST_COMPANY_ID,
    })

    board = trepo.get_board({'company_id': TEST_COMPANY_ID})

    # All 4 keys present, in the exact fixed order -- not just "some dict
    # with these keys" (dict equality doesn't check order; list(keys()) does).
    assert list(board.keys()) == _BOARD_COLUMNS
    assert [len(board[col]) for col in _BOARD_COLUMNS] == [1, 1, 1, 1]

    card = board['De făcut'][0]
    assert card['title'] == 'Recepție programată'
    assert card['type'] == 'Recepție'
    assert card['vehicle_model'] == 'Audi A4'
    assert card['order_ref'] == 'AW-TEST-7001'
    assert card['assignee'] == 'Logistică'
    # Card shape is exactly these 9 keys (Task 8's move handler relies on
    # `id` -- and on no extra/missing keys shifting the contract).
    assert set(card.keys()) == {
        'id', 'title', 'type', 'vehicle_model', 'order_ref',
        'location_name', 'position_code', 'assignee', 'due_at',
    }

    blocat_card = board['Blocat'][0]
    assert blocat_card['title'] == 'Solicită certificatul de conformitate'
    assert blocat_card['type'] == 'Documente'


def test_filter_by_assignee_and_search(require_real_db, logistics_cleanup):
    vrepo = LogisticsVehicleRepository()
    trepo = TaskRepository()

    v1 = vrepo.create_vehicle({
        'order_ref': 'AW-TEST-7101', 'model': 'Audi Q5', 'company_id': TEST_COMPANY_ID,
    })
    v2 = vrepo.create_vehicle({
        'order_ref': 'AW-TEST-7102', 'model': 'Audi A3', 'company_id': TEST_COMPANY_ID,
    })

    trepo.create_task({
        'vehicle_id': v1['id'], 'action': 'Pregătire', 'type': 'Îngrijire',
        'status': 'În lucru', 'assignee': 'Ana Pop', 'company_id': TEST_COMPANY_ID,
    })
    trepo.create_task({
        'vehicle_id': v2['id'], 'action': 'Pregătire', 'type': 'Îngrijire',
        'status': 'În lucru', 'assignee': 'Ion Ionescu', 'company_id': TEST_COMPANY_ID,
    })

    by_assignee = trepo.get_board({'company_id': TEST_COMPANY_ID, 'assignee': 'Ana Pop'})
    assert [c['order_ref'] for c in by_assignee['În lucru']] == ['AW-TEST-7101']
    # Empty columns stay present (as []) even when a filter narrows everything
    # out of them -- never dropped from the dict.
    assert by_assignee['De făcut'] == []
    assert by_assignee['Blocat'] == []
    assert by_assignee['Finalizat'] == []

    # q matches vehicle model / order_ref (not assignee).
    by_search_order = trepo.get_board({'company_id': TEST_COMPANY_ID, 'q': 'TEST-7102'})
    assert [c['order_ref'] for c in by_search_order['În lucru']] == ['AW-TEST-7102']

    by_search_model = trepo.get_board({'company_id': TEST_COMPANY_ID, 'q': 'Q5'})
    assert [c['order_ref'] for c in by_search_model['În lucru']] == ['AW-TEST-7101']
