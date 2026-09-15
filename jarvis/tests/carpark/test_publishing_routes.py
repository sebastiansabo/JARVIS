"""Tests for the listing-schedule config routes
(carpark/routes/publishing.py: get_listing_schedule / put_listing_schedule).

Combines two existing test idioms in this package:
  - the Flask-app/current_user-patching scaffolding from
    test_documents_routes.py (LOGIN_DISABLED + patched current_user in
    carpark.routes.vehicles's namespace, since carpark_required/
    carpark_edit_required read it from there — publishing.py itself also
    imports `current_user` from flask_login, so it's patched too for
    consistency even though these two routes don't reference it directly).
  - the seeded-vehicle real-DB probe idiom from conftest.py's dispo_seed /
    test_phase2_e2e.py's e2e_vehicle — the PUT round-trips through the real
    ListingScheduleRepository, and carpark_listing_schedules.vehicle_id has
    an FK to carpark_vehicles(id), so these tests need a real vehicle row.

Invocation:
    DATABASE_URL=postgresql://localhost/defaultdb \
        venv/bin/python -m pytest jarvis/tests/carpark/test_publishing_routes.py -v
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

from database import get_db, get_cursor, release_db

from carpark import carpark_bp
import carpark.routes.vehicles as vehicles_mod
import carpark.routes.publishing as publishing_mod

from .conftest import REAL_DB_AVAILABLE, TEST_COMPANY_ID


class FakeUser:
    def __init__(self, id=1, company_id=TEST_COMPANY_ID,
                 can_access_carpark=True, can_edit_carpark=True):
        self.id = id
        self.company_id = company_id
        self.is_authenticated = True
        self.can_access_carpark = can_access_carpark
        self.can_edit_carpark = can_edit_carpark


def _set_user(monkeypatch, user):
    """current_user is read from two module namespaces (see module
    docstring) — both must be patched together."""
    monkeypatch.setattr(vehicles_mod, 'current_user', user)
    monkeypatch.setattr(publishing_mod, 'current_user', user)


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(carpark_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def default_user(monkeypatch):
    """Every test gets an authenticated, fully-permissioned user by
    default; tests that need a different shape override via
    _set_user(monkeypatch, FakeUser(...))."""
    _set_user(monkeypatch, FakeUser())


@pytest.fixture
def seeded_vehicle():
    """Seed one minimal carpark_vehicles row under the shared
    TEST_COMPANY_ID sentinel (see conftest.py's dispo_seed). Teardown
    deletes it (and cascades to any carpark_listing_schedules rows created
    mid-test, since that FK is ON DELETE CASCADE)."""
    if not REAL_DB_AVAILABLE:
        pytest.skip(
            'Real Postgres not available (DATABASE_URL unreachable or psycopg2 '
            'mocked) — skipping carpark DB-backed test'
        )

    conn = get_db()
    conn.autocommit = False
    cur = get_cursor(conn)
    try:
        cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (TEST_COMPANY_ID,))

        cur.execute('''
            INSERT INTO carpark_vehicles (vin, brand, model, status, company_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', ('TESTPUBSCHED00001', 'TestBrand', 'TestModel', 'READY_FOR_SALE', TEST_COMPANY_ID))
        vehicle_id = cur.fetchone()['id']
        conn.commit()
        yield {'id': vehicle_id}
    finally:
        try:
            cur.execute('DELETE FROM carpark_vehicles WHERE company_id = %s', (TEST_COMPANY_ID,))
            conn.commit()
            cur.execute('SELECT COUNT(*) AS cnt FROM carpark_vehicles WHERE company_id = %s',
                        (TEST_COMPANY_ID,))
            remaining = cur.fetchone()['cnt']
        finally:
            release_db(conn)
        assert remaining == 0, (
            f'teardown left {remaining} orphan carpark_vehicles row(s) for '
            f'company_id={TEST_COMPANY_ID}'
        )


def test_put_then_get_schedule(client, seeded_vehicle):
    vid = seeded_vehicle['id']
    put = client.put(f'/api/carpark/vehicles/{vid}/listing-schedule',
                      json={'platform': 'shopify', 'cadence': 'daily', 'enabled': True})
    assert put.status_code == 200
    assert put.get_json()['schedule']['cadence'] == 'daily'

    got = client.get(f'/api/carpark/vehicles/{vid}/listing-schedule?platform=shopify')
    assert got.status_code == 200
    assert got.get_json()['schedule']['cadence'] == 'daily'


def test_put_computes_next_run_at_for_interval_cadence(client, seeded_vehicle):
    vid = seeded_vehicle['id']
    resp = client.put(f'/api/carpark/vehicles/{vid}/listing-schedule',
                       json={'platform': 'shopify', 'cadence': '2h', 'enabled': True})
    assert resp.status_code == 200
    assert resp.get_json()['schedule']['next_run_at'] is not None


def test_put_manual_cadence_leaves_next_run_at_null(client, seeded_vehicle):
    vid = seeded_vehicle['id']
    resp = client.put(f'/api/carpark/vehicles/{vid}/listing-schedule',
                       json={'platform': 'shopify', 'cadence': 'manual', 'enabled': True})
    assert resp.status_code == 200
    assert resp.get_json()['schedule']['next_run_at'] is None


def test_put_invalid_cadence_returns_400(client, seeded_vehicle):
    vid = seeded_vehicle['id']
    resp = client.put(f'/api/carpark/vehicles/{vid}/listing-schedule',
                       json={'platform': 'shopify', 'cadence': 'weekly', 'enabled': True})
    assert resp.status_code == 400
    assert 'invalid cadence' in resp.get_json()['error'].lower()


def test_get_no_schedule_returns_null(client, seeded_vehicle):
    vid = seeded_vehicle['id']
    resp = client.get(f'/api/carpark/vehicles/{vid}/listing-schedule?platform=shopify')
    assert resp.status_code == 200
    assert resp.get_json()['schedule'] is None


def test_put_requires_edit_permission(client, monkeypatch, seeded_vehicle):
    _set_user(monkeypatch, FakeUser(can_edit_carpark=False))
    vid = seeded_vehicle['id']
    resp = client.put(f'/api/carpark/vehicles/{vid}/listing-schedule',
                       json={'platform': 'shopify', 'cadence': 'daily', 'enabled': True})
    assert resp.status_code == 403


def test_get_requires_carpark_access(client, monkeypatch, seeded_vehicle):
    _set_user(monkeypatch, FakeUser(can_access_carpark=False))
    vid = seeded_vehicle['id']
    resp = client.get(f'/api/carpark/vehicles/{vid}/listing-schedule?platform=shopify')
    assert resp.status_code == 403
