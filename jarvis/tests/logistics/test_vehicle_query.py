"""Vehicle query API — Task 6 of the spine plan (Parc register).

Tests `LogisticsVehicleRepository.list_vehicles(filters)` DIRECTLY against
the real DB (no HTTP/login — the route in
jarvis/logistics/routes/vehicles.py is a thin `@login_required` wrapper with
no SQL of its own; this suite is the actual query-logic coverage).

Runs against localhost/defaultdb via the probe in conftest.py; seeds under
the sentinel `company_id=990002` (TEST_COMPANY_ID) and relies on
`logistics_cleanup` to delete those rows before/after each test.

Invocation:
    DATABASE_URL=postgresql://localhost/defaultdb venv/bin/python -m pytest jarvis/tests/logistics/test_vehicle_query.py -v
"""
from logistics.repositories.vehicle_repository import LogisticsVehicleRepository

from .conftest import TEST_COMPANY_ID


def test_filter_by_etapa_and_search_by_order(require_real_db, logistics_cleanup):
    repo = LogisticsVehicleRepository()
    repo.create_vehicle({
        'order_ref': 'AW-TEST-1001', 'model': 'Audi A4', 'vin': 'VIN1001XXXXXXXXXX',
        'etapa_parc': 'În stoc', 'company_id': TEST_COMPANY_ID,
    })
    repo.create_vehicle({
        'order_ref': 'AW-TEST-1002', 'model': 'Audi Q5', 'vin': 'VIN1002XXXXXXXXXX',
        'etapa_parc': 'În tranzit', 'company_id': TEST_COMPANY_ID,
    })

    by_etapa = repo.list_vehicles({'company_id': TEST_COMPANY_ID, 'etapa': 'În stoc'})
    assert [v['comanda'] for v in by_etapa] == ['AW-TEST-1001']

    by_search = repo.list_vehicles({'company_id': TEST_COMPANY_ID, 'q': 'TEST-1002'})
    assert [v['comanda'] for v in by_search] == ['AW-TEST-1002']


def test_null_vin_vehicle_matched_by_order_no_crash(require_real_db, logistics_cleanup):
    repo = LogisticsVehicleRepository()
    # vin intentionally omitted -> NULL. Searching by order_ref must not
    # crash on COALESCE(vin, '') ILIKE ... even though vin is NULL.
    repo.create_vehicle({
        'order_ref': 'AW-TEST-2001', 'model': 'Audi A3',
        'company_id': TEST_COMPANY_ID,
    })

    rows = repo.list_vehicles({'company_id': TEST_COMPANY_ID, 'q': 'AW-TEST-2001'})
    assert len(rows) == 1
    assert rows[0]['vin'] is None
    assert rows[0]['comanda'] == 'AW-TEST-2001'


def test_sort_by_etapa_stable(require_real_db, logistics_cleanup):
    repo = LogisticsVehicleRepository()
    repo.create_vehicle({
        'order_ref': 'AW-TEST-3001', 'model': 'Audi A1',
        'etapa_parc': 'În stoc', 'company_id': TEST_COMPANY_ID,
    })
    repo.create_vehicle({
        'order_ref': 'AW-TEST-3002', 'model': 'Audi A1',
        'etapa_parc': 'În stoc', 'company_id': TEST_COMPANY_ID,
    })
    repo.create_vehicle({
        'order_ref': 'AW-TEST-3003', 'model': 'Audi A1',
        'etapa_parc': 'În tranzit', 'company_id': TEST_COMPANY_ID,
    })

    rows = repo.list_vehicles({'company_id': TEST_COMPANY_ID, 'sort': 'etapa_parc', 'dir': 'asc'})
    # 'În stoc' < 'În tranzit' lexically -> both În stoc rows first, tie-broken
    # by insertion (id) order -- that tie-break is the "stable" part under test.
    assert [r['comanda'] for r in rows] == ['AW-TEST-3001', 'AW-TEST-3002', 'AW-TEST-3003']

    # Re-run to prove the tie-break order isn't accidental/flaky.
    rows_again = repo.list_vehicles({'company_id': TEST_COMPANY_ID, 'sort': 'etapa_parc', 'dir': 'asc'})
    assert [r['comanda'] for r in rows_again] == [r['comanda'] for r in rows]
