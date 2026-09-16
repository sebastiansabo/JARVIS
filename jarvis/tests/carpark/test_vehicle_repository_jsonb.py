"""Real-DB regression test for JSONB column adaptation in VehicleRepository.

Guards against "can't adapt type 'dict'": psycopg2 cannot bind a raw Python
dict/list to a JSONB column, so VehicleRepository.create()/update() must wrap
values bound for the JSONB columns (equipment, optional_packages) in
psycopg2.extras.Json(). The Autovit importer
(carpark/connectors/autovit/taxonomy.advert_to_vehicle) is the first caller to
write `equipment` as a real dict, which is what surfaced the bug.

Runs against localhost/defaultdb via the probe in conftest.py; skips when no
real DB is available (e.g. CI without Postgres).

Invocation:
    DATABASE_URL=postgresql://localhost/defaultdb \
        venv/bin/python -m pytest jarvis/tests/carpark/test_vehicle_repository_jsonb.py -v
"""
import pytest

from carpark.repositories.vehicle_repository import VehicleRepository

from .conftest import REAL_DB_AVAILABLE, TEST_COMPANY_ID

_VIN = 'ABCDEFGH12345678J'  # 17 chars, no I/O/Q per ISO 3779


@pytest.fixture
def _cleanup():
    """Delete the sentinel VIN before and after so the test is self-contained."""
    if not REAL_DB_AVAILABLE:
        pytest.skip('requires localhost/defaultdb')
    from database import get_db, release_db
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM carpark_vehicles WHERE vin = %s', (_VIN,))
        conn.commit()
    finally:
        release_db(conn)
    yield
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM carpark_vehicles WHERE vin = %s', (_VIN,))
        conn.commit()
    finally:
        release_db(conn)


def test_create_persists_equipment_jsonb_dict(_cleanup):
    """create() must accept a dict for the JSONB `equipment` column (was
    raising ProgrammingError: can't adapt type 'dict')."""
    equip = {'abs': True, 'esp': True, 'navigation': True}
    created = VehicleRepository().create({
        'vin': _VIN, 'brand': 'Audi', 'model': 'A8',
        'company_id': TEST_COMPANY_ID, 'equipment': equip,
    })
    assert created['equipment'] == equip


def test_update_persists_equipment_jsonb_dict(_cleanup):
    """update() must accept a dict for the JSONB `equipment` column — mirrors
    the Autovit 'wins' MERGE path (import_advert on an existing VIN)."""
    repo = VehicleRepository()
    created = repo.create({
        'vin': _VIN, 'brand': 'Audi', 'model': 'A8',
        'company_id': TEST_COMPANY_ID,
    })
    equip = {'heated_seats': True, 'led_lights': True}
    updated = repo.update(created['id'], {'equipment': equip})
    assert updated['equipment'] == equip
