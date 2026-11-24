"""Real-DB tests: VehicleService.create_cost auto-files a cost under a cost
line (get_or_create_for_type) when the caller sends no cost_line_id, so the
single-step "Adaugă cost" flow never creates orphan (cost_line_id NULL) costs.

Preserves the pre-existing invariant that every cost sits under a line, which
the old two-step Adaugă linie → Înregistrează cost flow guaranteed.
"""
import pytest

from carpark.services.vehicle_service import VehicleService

from .conftest import REAL_DB_AVAILABLE
from database import get_db, get_cursor, release_db

AUTOFILE_COMPANY_ID = 990008


@pytest.fixture
def autofile_seed():
    if not REAL_DB_AVAILABLE:
        pytest.skip('Real Postgres not available — skipping cost-autofile DB test')
    conn = get_db()
    conn.autocommit = False
    cur = get_cursor(conn)
    ids = {}
    try:
        cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (AUTOFILE_COMPANY_ID,))
        cur.execute('''
            INSERT INTO carpark_vehicles (vin, brand, model, status, company_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', ('TESTAUTOFILE00001', 'TestBrand', 'TestModel', 'READY_FOR_SALE', AUTOFILE_COMPANY_ID))
        ids['vehicle_id'] = cur.fetchone()['id']
        conn.commit()
        yield ids
    finally:
        try:
            cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (AUTOFILE_COMPANY_ID,))
            conn.commit()
        finally:
            release_db(conn)


def _achizitie_lines(vehicle_id):
    return [l for l in VehicleService().get_cost_lines(vehicle_id) if l['cost_type'] == 'achizitie']


def test_create_cost_without_line_autofiles_a_line_by_type(autofile_seed):
    vid = autofile_seed['vehicle_id']
    cost = VehicleService().create_cost(vid, {'cost_type': 'achizitie', 'amount': 100, 'currency': 'EUR'})
    assert cost['cost_line_id'] is not None
    lines = _achizitie_lines(vid)
    assert len(lines) == 1
    assert lines[0]['id'] == cost['cost_line_id']


def test_second_cost_same_type_reuses_line_and_recalcs_spent(autofile_seed):
    vid = autofile_seed['vehicle_id']
    c1 = VehicleService().create_cost(vid, {'cost_type': 'achizitie', 'amount': 100, 'currency': 'EUR'})
    c2 = VehicleService().create_cost(vid, {'cost_type': 'achizitie', 'amount': 50, 'currency': 'EUR'})
    assert c2['cost_line_id'] == c1['cost_line_id']
    lines = _achizitie_lines(vid)
    assert len(lines) == 1                       # reused, not duplicated
    assert float(lines[0]['spent_amount']) == 150.0  # recalc ran (stored column, not just live sum)


def test_explicit_cost_line_id_is_respected(autofile_seed):
    vid = autofile_seed['vehicle_id']
    line_id = VehicleService().create_cost_line(vid, 'repair', planned_amount=0, currency='EUR')
    cost = VehicleService().create_cost(vid, {'cost_type': 'repair', 'amount': 10, 'cost_line_id': line_id})
    assert cost['cost_line_id'] == line_id
