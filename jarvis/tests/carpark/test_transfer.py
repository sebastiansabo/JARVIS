"""Real-DB integration tests for inter-company vehicle transfer:
TransferRepository (AutoWorld group lookups + the carpark_transfers log)
and DispoService.transfer (the move + log + validation guards).

Runs against localhost/defaultdb via the REAL_DB_AVAILABLE probe already
set up in conftest.py. Seeds a standalone sentinel AutoWorld-shaped group
(a parent company + two children sharing it as parent_company_id, plus an
unrelated third company as its own group) rather than touching the real
AutoWorld group (id=16 + subsidiaries) or reusing the single-company
TEST_COMPANY_ID sentinel from conftest.dispo_seed — a transfer test needs
TWO sibling companies plus a vehicle, which doesn't fit that fixture.

Invocation:
    DATABASE_URL=postgresql://localhost/defaultdb \
        venv/bin/python -m pytest jarvis/tests/carpark/test_transfer.py -v
"""
from datetime import date

import pytest

from carpark.repositories.reservation_repository import ReservationRepository
from carpark.repositories.transfer_repository import TransferRepository
from carpark.services.dispo_service import DispoService

from database import get_db, get_cursor, release_db
from .conftest import REAL_DB_AVAILABLE

# Sentinel AutoWorld-shaped group — ids far outside the live range so they
# can never collide with real companies (16 + subsidiaries 9-15).
PARENT_ID = 990100
COMPANY_A = 990101       # transfer source
COMPANY_B = 990102       # transfer destination (sibling of A under PARENT_ID)
OUTSIDE_COMPANY = 990103  # its own separate group root — NOT a valid target from A/B

USER = {'id': 1, 'name': 'Test User'}


@pytest.fixture
def transfer_seed():
    """Seeds PARENT_ID (root) + COMPANY_A/COMPANY_B (children, same group)
    + OUTSIDE_COMPANY (its own group), one vehicle under COMPANY_A, and one
    carpark_vehicle_documents row on that vehicle (document_type=
    'factura_transfer') to use as the transfer's document_id.

    Yields {'vehicle_id': ..., 'document_id': ...}.

    Teardown deletes the vehicle (cascades to carpark_vehicle_documents,
    carpark_transfers, carpark_reservations — all
    `... REFERENCES carpark_vehicles(id) ON DELETE CASCADE`) across every
    sentinel company_id (the vehicle may have moved from A to B mid-test),
    then the four sentinel companies, and asserts zero rows remain.
    """
    if not REAL_DB_AVAILABLE:
        pytest.skip(
            'Real Postgres not available (DATABASE_URL unreachable or psycopg2 '
            'mocked) — skipping carpark transfer DB-backed test'
        )

    conn = get_db()
    conn.autocommit = False
    cur = get_cursor(conn)
    company_ids = (COMPANY_A, COMPANY_B, OUTSIDE_COMPANY)
    all_ids = company_ids + (PARENT_ID,)
    try:
        # Defensive: clean up any leftover rows from a previously crashed run.
        cur.execute('DELETE FROM carpark_vehicles WHERE company_id = ANY(%s)', (list(company_ids),))
        cur.execute('DELETE FROM companies WHERE id = ANY(%s)', (list(all_ids),))

        cur.execute('INSERT INTO companies (id, company) VALUES (%s, %s)',
                    (PARENT_ID, 'TEST TRANSFER PARENT SRL'))
        cur.execute('INSERT INTO companies (id, company, parent_company_id) VALUES (%s, %s, %s)',
                    (COMPANY_A, 'TEST TRANSFER COMPANY A SRL', PARENT_ID))
        cur.execute('INSERT INTO companies (id, company, parent_company_id) VALUES (%s, %s, %s)',
                    (COMPANY_B, 'TEST TRANSFER COMPANY B SRL', PARENT_ID))
        cur.execute('INSERT INTO companies (id, company) VALUES (%s, %s)',
                    (OUTSIDE_COMPANY, 'TEST TRANSFER OUTSIDE GROUP SRL'))

        cur.execute('''
            INSERT INTO carpark_vehicles (vin, brand, model, status, company_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', ('TESTTRANSFER00001', 'TestBrand', 'TestModel', 'READY_FOR_SALE', COMPANY_A))
        vehicle_id = cur.fetchone()['id']

        cur.execute('''
            INSERT INTO carpark_vehicle_documents (vehicle_id, document_type, file_url, uploaded_by)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        ''', (vehicle_id, 'factura_transfer', 'https://example.com/transfer-doc.pdf', 1))
        document_id = cur.fetchone()['id']

        conn.commit()
        yield {'vehicle_id': vehicle_id, 'document_id': document_id}
    finally:
        try:
            # company_id may now be A or B depending on how far the test got.
            cur.execute('DELETE FROM carpark_vehicles WHERE company_id = ANY(%s)', (list(company_ids),))
            cur.execute('DELETE FROM companies WHERE id = ANY(%s)', (list(all_ids),))
            conn.commit()

            cur.execute('SELECT COUNT(*) AS cnt FROM companies WHERE id = ANY(%s)', (list(all_ids),))
            remaining_companies = cur.fetchone()['cnt']
            cur.execute('SELECT COUNT(*) AS cnt FROM carpark_vehicles WHERE company_id = ANY(%s)',
                        (list(company_ids),))
            remaining_vehicles = cur.fetchone()['cnt']
            cur.execute('''
                SELECT COUNT(*) AS cnt FROM carpark_transfers
                WHERE from_company_id = ANY(%s) OR to_company_id = ANY(%s)
            ''', (list(company_ids), list(company_ids)))
            remaining_transfers = cur.fetchone()['cnt']
        finally:
            release_db(conn)
        assert remaining_companies == 0, (
            f'teardown left {remaining_companies} orphan sentinel companies')
        assert remaining_vehicles == 0, (
            f'teardown left {remaining_vehicles} orphan sentinel carpark_vehicles row(s)')
        assert remaining_transfers == 0, (
            f'teardown left {remaining_transfers} orphan carpark_transfers row(s)')


# ── AUTOWORLD GROUP LOOKUPS ─────────────────────────────────────────────

def test_group_company_ids_includes_self_and_siblings(transfer_seed):
    ids = set(TransferRepository().group_company_ids(COMPANY_A))
    assert {PARENT_ID, COMPANY_A, COMPANY_B}.issubset(ids)
    assert OUTSIDE_COMPANY not in ids


def test_group_companies_excludes_self(transfer_seed):
    companies = TransferRepository().group_companies(COMPANY_A)
    ids = {c['id'] for c in companies}
    assert COMPANY_A not in ids
    assert COMPANY_B in ids
    assert PARENT_ID in ids
    assert OUTSIDE_COMPANY not in ids


def test_group_companies_for_outside_company_is_its_own_group(transfer_seed):
    """A company with no parent and no children (OUTSIDE_COMPANY) is its
    own single-member group — group_companies (which excludes self) returns
    nothing, and it never appears as a sibling of A/B."""
    companies = TransferRepository().group_companies(OUTSIDE_COMPANY)
    assert companies == []


# ── DispoService.transfer — THE MOVE ─────────────────────────────────────

def test_transfer_moves_vehicle_sets_fields_and_logs(transfer_seed):
    vehicle_id = transfer_seed['vehicle_id']
    document_id = transfer_seed['document_id']

    result = DispoService().transfer(vehicle_id, COMPANY_A, USER, {
        'to_company_id': COMPANY_B,
        'transfer_price': 10000,
        'document_id': document_id,
    })

    vehicle = result['vehicle']
    assert vehicle['company_id'] == COMPANY_B
    assert vehicle['status'] == 'ACQUIRED'
    assert vehicle['transferred_from_company_id'] == COMPANY_A
    assert vehicle['source'] == 'TRANSFER'
    assert float(vehicle['acquisition_price']) == 10000
    assert str(vehicle['acquisition_date']) == str(date.today())
    assert vehicle['sale_price'] is None
    assert vehicle['sale_date'] is None
    assert vehicle['sale_type'] is None
    assert vehicle['buyer_client_id'] is None
    assert vehicle['buyer_name'] is None

    transfer = result['transfer']
    assert transfer['vehicle_id'] == vehicle_id
    assert transfer['from_company_id'] == COMPANY_A
    assert transfer['to_company_id'] == COMPANY_B
    assert float(transfer['transfer_price']) == 10000
    assert transfer['transfer_currency'] == 'EUR'
    assert transfer['document_id'] == document_id

    # Independently verify the log row + the moved vehicle straight from the DB.
    outbound = TransferRepository().list_outbound(COMPANY_A)
    assert len(outbound) == 1
    assert outbound[0]['vehicle_id'] == vehicle_id
    assert outbound[0]['to_company_id'] == COMPANY_B
    assert float(outbound[0]['transfer_price']) == 10000

    from carpark.repositories.vehicle_repository import VehicleRepository
    persisted = VehicleRepository().get_by_id(vehicle_id)
    assert persisted['company_id'] == COMPANY_B
    assert persisted['status'] == 'ACQUIRED'


def test_transfer_cancels_active_reservation(transfer_seed):
    vehicle_id = transfer_seed['vehicle_id']
    res_repo = ReservationRepository()
    reservation = res_repo.create(vehicle_id, {
        'client_name': 'Test Client', 'reservation_end': date.today(),
        'status': 'active', 'user_id': 1, 'created_by': 1,
    })

    DispoService().transfer(vehicle_id, COMPANY_A, USER, {
        'to_company_id': COMPANY_B, 'transfer_price': 7000,
        'document_id': transfer_seed['document_id'],
    })

    refreshed = res_repo.query_one(
        'SELECT status FROM carpark_reservations WHERE id = %s', (reservation['id'],))
    assert refreshed['status'] == 'cancelled'


def test_list_outbound_scoped_to_from_company(transfer_seed):
    DispoService().transfer(transfer_seed['vehicle_id'], COMPANY_A, USER, {
        'to_company_id': COMPANY_B, 'transfer_price': 4200,
        'document_id': transfer_seed['document_id'],
    })
    repo = TransferRepository()
    assert len(repo.list_outbound(COMPANY_A)) == 1
    assert repo.list_outbound(COMPANY_B) == []  # nothing yet originates FROM B


# ── DispoService.transfer — VALIDATION GUARDS ────────────────────────────

def test_transfer_rejects_destination_outside_autoworld_group(transfer_seed):
    with pytest.raises(ValueError, match='AutoWorld'):
        DispoService().transfer(transfer_seed['vehicle_id'], COMPANY_A, USER, {
            'to_company_id': OUTSIDE_COMPANY,
            'transfer_price': 5000,
            'document_id': transfer_seed['document_id'],
        })


def test_transfer_rejects_destination_equal_to_source(transfer_seed):
    with pytest.raises(ValueError, match='AutoWorld'):
        DispoService().transfer(transfer_seed['vehicle_id'], COMPANY_A, USER, {
            'to_company_id': COMPANY_A,
            'transfer_price': 5000,
            'document_id': transfer_seed['document_id'],
        })


def test_transfer_requires_to_company_id(transfer_seed):
    with pytest.raises(ValueError):
        DispoService().transfer(transfer_seed['vehicle_id'], COMPANY_A, USER, {
            'transfer_price': 5000,
            'document_id': transfer_seed['document_id'],
        })


def test_transfer_requires_transfer_price(transfer_seed):
    with pytest.raises(ValueError):
        DispoService().transfer(transfer_seed['vehicle_id'], COMPANY_A, USER, {
            'to_company_id': COMPANY_B,
            'document_id': transfer_seed['document_id'],
        })


def test_transfer_rejects_zero_or_negative_transfer_price(transfer_seed):
    with pytest.raises(ValueError):
        DispoService().transfer(transfer_seed['vehicle_id'], COMPANY_A, USER, {
            'to_company_id': COMPANY_B,
            'transfer_price': 0,
            'document_id': transfer_seed['document_id'],
        })


def test_transfer_requires_document_id(transfer_seed):
    with pytest.raises(ValueError, match='obligatoriu'):
        DispoService().transfer(transfer_seed['vehicle_id'], COMPANY_A, USER, {
            'to_company_id': COMPANY_B,
            'transfer_price': 5000,
        })


def test_transfer_cross_tenant_raises_permission_error(transfer_seed):
    """The vehicle belongs to COMPANY_A — calling transfer() with COMPANY_B
    as the acting company (i.e. someone from B trying to transfer A's car)
    must 403 (PermissionError), not silently operate on it."""
    with pytest.raises(PermissionError):
        DispoService().transfer(transfer_seed['vehicle_id'], COMPANY_B, USER, {
            'to_company_id': COMPANY_A,
            'transfer_price': 5000,
            'document_id': transfer_seed['document_id'],
        })


def test_transfer_unknown_vehicle_raises_value_error(transfer_seed):
    with pytest.raises(ValueError):
        DispoService().transfer(999999999, COMPANY_A, USER, {
            'to_company_id': COMPANY_B,
            'transfer_price': 5000,
            'document_id': transfer_seed['document_id'],
        })


# ── Failed validation must not write anything ────────────────────────────

def test_rejected_transfer_leaves_no_transfer_row_and_vehicle_unmoved(transfer_seed):
    vehicle_id = transfer_seed['vehicle_id']
    with pytest.raises(ValueError):
        DispoService().transfer(vehicle_id, COMPANY_A, USER, {
            'to_company_id': OUTSIDE_COMPANY,
            'transfer_price': 5000,
            'document_id': transfer_seed['document_id'],
        })

    assert TransferRepository().list_outbound(COMPANY_A) == []

    from carpark.repositories.vehicle_repository import VehicleRepository
    persisted = VehicleRepository().get_by_id(vehicle_id)
    assert persisted['company_id'] == COMPANY_A
    assert persisted['status'] == 'READY_FOR_SALE'
