"""Phase 2 end-to-end integration test — the full DispoService lifecycle
against a REAL local Postgres DB (localhost/defaultdb), with REAL
repositories (no mocks anywhere in the call chain).

Where test_dispo_service.py proves DispoService's business rules in
isolation (every collaborator mocked) and test_dispo_repository_sql.py
proves DispoRepository's SQL in isolation, this file proves the whole stack
actually wires together end-to-end: VehicleService's TRANSITIONS matrix,
ReservationRepository, DocumentRepository, VehicleRepository's
VEHICLE_UPDATABLE_FIELDS whitelist (sale_price/sale_type/buyer_name/
delivery_date/stock_removed* must actually persist — this is the one thing
mocks in test_dispo_service.py structurally cannot catch), and
PublishingService's real DB query on sell().

Runs against the real DB via the probe in conftest.py (REAL_DB_AVAILABLE).
Sentinel company_id=990002 — deliberately distinct from
TEST_COMPANY_ID=990001 (test_dispo_repository_sql.py's dispo_seed fixture)
so the two test files can never collide.

Invocation:
    DATABASE_URL=postgresql://localhost/defaultdb \
        venv/bin/python -m pytest jarvis/tests/carpark/test_phase2_e2e.py -v
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from datetime import date, timedelta

import pytest

from database import get_db, get_cursor, release_db
from core.base_repository import BaseRepository
from carpark.services.dispo_service import DispoService
from carpark.repositories.vehicle_repository import VehicleRepository
from carpark.repositories.reservation_repository import ReservationRepository
from carpark.repositories.document_repository import DocumentRepository

from .conftest import REAL_DB_AVAILABLE

E2E_COMPANY_ID = 990002
TEST_VIN = 'TESTE2E000000001'
# Real local user (id=1, 'Sebastian Sabo') — salesperson_user_id has no FK
# constraint, but using a real id lets notify_user()'s real INSERT INTO
# notifications (user_id ...) succeed like it would in production.
TEST_USER = {'id': 1, 'name': 'Sebastian Sabo'}


@pytest.fixture
def e2e_vehicle():
    """Seed one fresh READY_FOR_SALE vehicle under company_id=990002 with a
    cost row, via direct SQL (mirrors the dispo_seed fixture in conftest.py).

    Teardown deletes every carpark_vehicles row for company_id=990002 (every
    carpark_vehicle_costs/_reservations/_vehicle_documents/_status_history
    row cascades via `vehicle_id ... ON DELETE CASCADE`), plus any
    `notifications` rows the lifecycle calls fired for this vehicle
    (notifications has no company_id column of its own, so it isn't covered
    by the company_id delete and needs its own cleanup), and asserts zero
    carpark_vehicles rows remain for the sentinel company afterwards.
    """
    if not REAL_DB_AVAILABLE:
        pytest.skip(
            'Real Postgres not available (DATABASE_URL unreachable or psycopg2 '
            'mocked) — skipping carpark Dispo Phase 2 E2E test'
        )

    conn = get_db()
    conn.autocommit = False
    cur = get_cursor(conn)
    today = date.today()
    try:
        # Defensive: clean up any leftover rows from a previously crashed run.
        cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (E2E_COMPANY_ID,))

        cur.execute('''
            INSERT INTO carpark_vehicles
                (vin, brand, model, status, company_id, acquisition_date,
                 acquisition_price, minimum_price, salesperson_user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (TEST_VIN, 'TestBrandE2E', 'TestModelE2E', 'READY_FOR_SALE',
              E2E_COMPANY_ID, today - timedelta(days=5), 10000, 12000, TEST_USER['id']))
        vehicle_id = cur.fetchone()['id']

        cur.execute('''
            INSERT INTO carpark_vehicle_costs (vehicle_id, cost_type, amount)
            VALUES (%s, %s, %s)
        ''', (vehicle_id, 'reconditionare', 1000))

        conn.commit()
        yield vehicle_id
    finally:
        try:
            cur.execute(
                'DELETE FROM notifications WHERE entity_type = %s AND entity_id = %s',
                ('carpark_vehicle', vehicle_id))
            cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (E2E_COMPANY_ID,))
            conn.commit()
            cur.execute('SELECT COUNT(*) AS cnt FROM carpark_vehicles WHERE company_id = %s',
                        (E2E_COMPANY_ID,))
            remaining = cur.fetchone()['cnt']
        finally:
            release_db(conn)
        assert remaining == 0, (
            f'teardown left {remaining} orphan carpark_vehicles row(s) for '
            f'company_id={E2E_COMPANY_ID}'
        )


def test_full_dispo_lifecycle_reserve_deliver_guard_sell_deliver_remove(e2e_vehicle):
    vehicle_id = e2e_vehicle
    svc = DispoService()  # REAL repos — nothing injected, nothing mocked
    today = date.today()

    vehicle_repo = VehicleRepository()
    reservation_repo = ReservationRepository()
    document_repo = DocumentRepository()
    raw = BaseRepository()  # ad-hoc SQL for assertions outside any repo's API

    # ── 1. reserve → vehicle RESERVED, active reservation row exists ──
    reserve_result = svc.reserve(vehicle_id, E2E_COMPANY_ID, TEST_USER, {
        'client_name': 'Test Client',
        'reservation_end': today + timedelta(days=3),
    })
    assert reserve_result['vehicle']['status'] == 'RESERVED'
    reservation_id = reserve_result['reservation']['id']
    assert reserve_result['reservation']['status'] == 'active'

    active = reservation_repo.active_for_vehicle(vehicle_id)
    assert active is not None
    assert active['id'] == reservation_id

    persisted_vehicle = vehicle_repo.get_by_id(vehicle_id)
    assert persisted_vehicle['status'] == 'RESERVED'

    # ── 2. deliver BEFORE any pv_livrare doc → hard-blocked ──
    with pytest.raises(ValueError) as exc_info:
        svc.deliver(vehicle_id, E2E_COMPANY_ID, TEST_USER, {'delivery_date': today})
    assert 'MISSING_PV_LIVRARE' in str(exc_info.value)

    # the blocked deliver() must not have mutated anything
    still_reserved = vehicle_repo.get_by_id(vehicle_id)
    assert still_reserved['status'] == 'RESERVED'
    assert still_reserved['delivery_date'] is None

    # ── 3. sell → SOLD, reservation closed, sale fields persisted ──
    sell_result = svc.sell(vehicle_id, E2E_COMPANY_ID, TEST_USER, {
        'sale_price': 15000,
        'sale_type': 'CASH',
        'buyer_name': 'Cumparator Test',
        'sale_date': today,
        'confirm_low_margin': True,
    })
    assert sell_result['vehicle']['status'] == 'SOLD'

    sold_vehicle = vehicle_repo.get_by_id(vehicle_id)
    assert sold_vehicle['status'] == 'SOLD'
    # Proves the VEHICLE_UPDATABLE_FIELDS whitelist covers the sale fields —
    # a mock-based test structurally cannot catch a regression here, since
    # the mocked VehicleRepository.update() would happily "succeed" either way.
    assert float(sold_vehicle['sale_price']) == 15000
    assert sold_vehicle['sale_type'] == 'CASH'
    assert sold_vehicle['buyer_name'] == 'Cumparator Test'

    # the reservation opened in step 1 is closed (converted, no longer active)
    assert reservation_repo.active_for_vehicle(vehicle_id) is None
    reservation_row = raw.query_one(
        'SELECT status FROM carpark_reservations WHERE id = %s', (reservation_id,))
    assert reservation_row['status'] == 'converted'

    # listings deactivation ran without error; no active listings remain
    # (there were none to begin with — this vehicle was never published).
    active_listings = raw.query_all(
        "SELECT id FROM carpark_vehicle_listings WHERE vehicle_id = %s AND status = 'active'",
        (vehicle_id,))
    assert active_listings == []

    # ── 4. insert pv_livrare doc, then deliver → DELIVERED ──
    document_repo.create(vehicle_id, {
        'document_type': 'pv_livrare',
        'file_url': 'http://x',
    })
    assert document_repo.has_type(vehicle_id, 'pv_livrare') is True

    deliver_result = svc.deliver(vehicle_id, E2E_COMPANY_ID, TEST_USER, {'delivery_date': today})
    assert deliver_result['vehicle']['status'] == 'DELIVERED'

    delivered_vehicle = vehicle_repo.get_by_id(vehicle_id)
    assert delivered_vehicle['status'] == 'DELIVERED'
    # BaseRepository.query_one/execute route through database.dict_from_row,
    # which isoformat()s every date/datetime value for JSON-safety — so a
    # real DB round-trip returns a string, not a date object.
    assert delivered_vehicle['delivery_date'] == today.isoformat()

    # ── 5. remove_from_stock → stock_removed persisted ──
    remove_result = svc.remove_from_stock(vehicle_id, E2E_COMPANY_ID, TEST_USER)
    assert remove_result['vehicle']['stock_removed'] is True
    assert remove_result['vehicle']['stock_removed_date'] == today.isoformat()

    final_vehicle = vehicle_repo.get_by_id(vehicle_id)
    assert final_vehicle['stock_removed'] is True
    assert final_vehicle['stock_removed_date'] == today.isoformat()
