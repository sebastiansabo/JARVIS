"""Tests for the Dispo + reservations HTTP routes (dispo.py / reservations.py).

Mock-based, mirroring jarvis/tests/foi_parcurs/test_test_drive_return.py and
jarvis/tests/dept_pulse/test_dept_pulse_routes.py: a minimal Flask app
registers carpark_bp, LOGIN_DISABLED=True makes @login_required a no-op, and
`current_user` is monkeypatched directly onto every module that references it
at call time (carpark.routes.vehicles — where the carpark_required family and
_verify_vehicle_ownership/_user_company_id live — plus dispo.py and
reservations.py themselves, which each do their own `from flask_login import
current_user`).

No real DB access: _vehicle_service (imported into vehicles.py),
_dispo_service, _dispo_repo, and _reservation_repo module-level singletons
are monkeypatched per test, so this file exercises only the route layer
(auth gating, delegation, exception -> status code mapping, finance
gating) — not DispoService/DispoRepository themselves (covered by
test_dispo_service.py / test_dispo_repository_sql.py).
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

from carpark import carpark_bp
import carpark.routes.vehicles as vehicles_mod
import carpark.routes.dispo as dispo_mod
import carpark.routes.reservations as reservations_mod

COMPANY_ID = 10
OTHER_COMPANY_ID = 99


class FakeUser:
    def __init__(self, id=1, company_id=COMPANY_ID, name='Test User',
                 can_access_carpark=True, can_edit_carpark=True,
                 can_delete_carpark=True, can_view_carpark_finance=False):
        self.id = id
        self.company_id = company_id
        self.name = name
        self.is_authenticated = True
        self.can_access_carpark = can_access_carpark
        self.can_edit_carpark = can_edit_carpark
        self.can_delete_carpark = can_delete_carpark
        self.can_view_carpark_finance = can_view_carpark_finance


def _set_user(monkeypatch, user):
    """current_user is read from three different module namespaces at call
    time (see module docstring) — all three must be patched together."""
    monkeypatch.setattr(vehicles_mod, 'current_user', user)
    monkeypatch.setattr(dispo_mod, 'current_user', user)
    monkeypatch.setattr(reservations_mod, 'current_user', user)


def _own_vehicle(vehicle_id=1, company_id=COMPANY_ID, **overrides):
    v = {'id': vehicle_id, 'company_id': company_id, 'status': 'READY_FOR_SALE'}
    v.update(overrides)
    return v


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
    """Every test gets an authenticated, fully-permissioned (non-finance)
    user by default; tests that need a different shape override via
    _set_user(monkeypatch, FakeUser(...))."""
    _set_user(monkeypatch, FakeUser())


# ── ROUTE REGISTRATION ───────────────────────────────────────────────────

def test_dispo_summary_route_registered(client, monkeypatch):
    monkeypatch.setattr(dispo_mod._dispo_repo, 'summary', lambda *a, **k: {
        'rows': [], 'stage_counts': {}, 'totals': {}, 'total': 0, 'page': 1, 'per_page': 25,
    })
    resp = client.get('/api/carpark/dispo/summary')
    assert resp.status_code == 200


def test_dispo_kpis_route_registered(client, monkeypatch):
    monkeypatch.setattr(dispo_mod._dispo_repo, 'kpis', lambda *a, **k: {
        'cars_in_stock': 0, 'reserved': 0, 'sold_this_month': 0,
        'delivered_this_month': 0, 'avg_days_in_stock': 0, 'aged_over_60': 0,
        'gross_margin_mtd': 0,
    })
    resp = client.get('/api/carpark/dispo/kpis')
    assert resp.status_code == 200


# ── EXCEPTION -> STATUS CODE MAPPING ─────────────────────────────────────

def test_deliver_without_pv_livrare_returns_400_with_marker(client, monkeypatch):
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle',
                         lambda vid: _own_vehicle(vid))

    def _raise_missing_doc(*a, **k):
        raise ValueError('MISSING_PV_LIVRARE: proces verbal de livrare document required before delivery')
    monkeypatch.setattr(dispo_mod._dispo_service, 'deliver', _raise_missing_doc)

    resp = client.post('/api/carpark/vehicles/1/deliver', json={'delivery_date': '2026-08-10'})
    assert resp.status_code == 400
    assert 'MISSING_PV_LIVRARE' in resp.get_json()['error']


def test_cross_tenant_permission_error_returns_403(client, monkeypatch):
    # Route-level ownership check passes (vehicle appears same-company);
    # the service layer is the one that raises PermissionError here so this
    # test isolates the route's exception->status mapping.
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle',
                         lambda vid: _own_vehicle(vid))

    def _raise_permission(*a, **k):
        raise PermissionError(f'Vehicle 1 does not belong to company {COMPANY_ID}')
    monkeypatch.setattr(dispo_mod._dispo_service, 'reserve', _raise_permission)

    resp = client.post('/api/carpark/vehicles/1/reserve', json={
        'client_name': 'Ion Pop', 'reservation_end': '2026-09-01'})
    assert resp.status_code == 403


def test_unknown_vehicle_returns_404(client, monkeypatch):
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle', lambda vid: None)
    calls = []
    monkeypatch.setattr(dispo_mod._dispo_service, 'reserve',
                         lambda *a, **k: calls.append(1))

    resp = client.post('/api/carpark/vehicles/999/reserve', json={
        'client_name': 'Ion Pop', 'reservation_end': '2026-09-01'})
    assert resp.status_code == 404
    # DispoService.reserve must never be reached for an unknown vehicle.
    assert calls == []


def test_vehicle_owned_by_other_company_blocked_at_service_403(client, monkeypatch):
    """Permissive tenant switcher: _verify_vehicle_ownership is now exists-only
    (no route-level 404), but the money operations still enforce isolation at
    the SERVICE layer — DispoService.reserve raises PermissionError for a
    cross-company vehicle, mapped to 403. So cross-tenant reserve/sell/deliver
    stay blocked, just as 403 (service) instead of 404 (route)."""
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle',
                         lambda vid: _own_vehicle(vid, company_id=OTHER_COMPANY_ID))

    resp = client.post('/api/carpark/vehicles/1/reserve', json={
        'client_name': 'Ion Pop', 'reservation_end': '2026-09-01'})
    assert resp.status_code == 403

def test_sell_low_margin_validation_error_returns_400(client, monkeypatch):
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle',
                         lambda vid: _own_vehicle(vid))

    def _raise_low_margin(*a, **k):
        raise ValueError('LOW_MARGIN: sale_price 8000 is below minimum_price 9000.0')
    monkeypatch.setattr(dispo_mod._dispo_service, 'sell', _raise_low_margin)

    resp = client.post('/api/carpark/vehicles/1/sell', json={
        'sale_price': 8000, 'sale_type': 'CASH', 'sale_date': '2026-08-10',
        'buyer_name': 'Popescu Vasile'})
    assert resp.status_code == 400
    assert 'LOW_MARGIN' in resp.get_json()['error']


def test_remove_from_stock_requires_delete_permission(client, monkeypatch):
    _set_user(monkeypatch, FakeUser(can_delete_carpark=False))
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle',
                         lambda vid: _own_vehicle(vid))
    resp = client.post('/api/carpark/vehicles/1/remove-from-stock')
    assert resp.status_code == 403


def test_reserve_requires_edit_permission(client, monkeypatch):
    _set_user(monkeypatch, FakeUser(can_edit_carpark=False))
    resp = client.post('/api/carpark/vehicles/1/reserve', json={})
    assert resp.status_code == 403


# ── DELEGATION (happy path) ──────────────────────────────────────────────

def test_reserve_delegates_to_dispo_service_and_returns_result(client, monkeypatch):
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle',
                         lambda vid: _own_vehicle(vid))
    calls = {}

    def _reserve(vehicle_id, company_id, user, data):
        calls['args'] = (vehicle_id, company_id, user, data)
        return {'vehicle': {'id': vehicle_id, 'status': 'RESERVED'},
                'reservation': {'id': 5, 'status': 'active'}}
    monkeypatch.setattr(dispo_mod._dispo_service, 'reserve', _reserve)

    resp = client.post('/api/carpark/vehicles/1/reserve', json={
        'client_name': 'Ion Pop', 'reservation_end': '2026-09-01'})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['vehicle']['status'] == 'RESERVED'
    assert body['reservation']['id'] == 5
    assert calls['args'][0] == 1
    assert calls['args'][1] == COMPANY_ID


def test_cancel_reservation_delegates_and_maps_errors(client, monkeypatch):
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle',
                         lambda vid: _own_vehicle(vid))

    def _cancel(vehicle_id, company_id, user, reason):
        assert reason == 'Client backed out'
        return {'vehicle': {'id': vehicle_id, 'status': 'LISTED'},
                'reservation': {'id': 7, 'status': 'cancelled'}}
    monkeypatch.setattr(reservations_mod._dispo_service, 'cancel_reservation', _cancel)

    resp = client.post('/api/carpark/vehicles/1/cancel-reservation',
                        json={'reason': 'Client backed out'})
    assert resp.status_code == 200
    assert resp.get_json()['vehicle']['status'] == 'LISTED'


def test_cancel_reservation_no_active_reservation_returns_400(client, monkeypatch):
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle',
                         lambda vid: _own_vehicle(vid))

    def _raise(*a, **k):
        raise ValueError('No active reservation to cancel')
    monkeypatch.setattr(reservations_mod._dispo_service, 'cancel_reservation', _raise)

    resp = client.post('/api/carpark/vehicles/1/cancel-reservation', json={'reason': 'x'})
    assert resp.status_code == 400


def test_list_vehicle_reservations_delegates_to_repo(client, monkeypatch):
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle',
                         lambda vid: _own_vehicle(vid))
    monkeypatch.setattr(reservations_mod._reservation_repo, 'list_for_vehicle',
                         lambda vid: [{'id': 1, 'status': 'cancelled'}, {'id': 2, 'status': 'active'}])

    resp = client.get('/api/carpark/vehicles/1/reservations')
    assert resp.status_code == 200
    assert len(resp.get_json()['reservations']) == 2


# ── PUT /vehicles/<id> — company reassignment IDOR guard ─────────────────
# Regression tests for the fix that keeps 'company_id' /
# 'transferred_from_company_id' — added to VEHICLE_UPDATABLE_FIELDS ONLY so
# DispoService.transfer() can persist an inter-company move — from being
# writable via the *generic* PUT /vehicles/<id> route. update_vehicle()
# .pop()s both before handing the body to the service, so a plain PUT can
# never reassign a car's owning company (which would bypass transfer()'s
# AutoWorld-group/price/document guards). These guard the .pop() against a
# future refactor silently removing it.

def _capturing_update_vehicle(monkeypatch, base_vehicle):
    """Patch _vehicle_service.update_vehicle to (a) record the exact data
    dict the route passed it (post-strip) and (b) simulate a real repo
    update: merge that data onto base_vehicle and return the result, so the
    response reflects what the DB *would* persist. Returns the captured
    dict, mutated in place on call."""
    captured = {}

    def _update(vehicle_id, data, updated_by=None, updated_by_name=None):
        captured['data'] = dict(data)
        merged = dict(base_vehicle)
        merged.update(data)  # only keys the route actually forwarded land here
        return merged
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'update_vehicle', _update)
    return captured


def test_put_vehicle_cannot_reassign_company_id(client, monkeypatch):
    """A PUT body that tries to move the car to company B (and set a
    transferred_from marker) leaves company_id / transferred_from_company_id
    UNCHANGED at company A, while a legitimate co-submitted field
    (current_price) DOES update — proving the strip is targeted, not a
    blanket reject."""
    base = _own_vehicle(1, company_id=COMPANY_ID,
                        transferred_from_company_id=None, current_price=10000)
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle', lambda vid: dict(base))
    captured = _capturing_update_vehicle(monkeypatch, base)

    resp = client.put('/api/carpark/vehicles/1', json={
        'company_id': OTHER_COMPANY_ID,
        'transferred_from_company_id': OTHER_COMPANY_ID,
        'current_price': 12345,
    })
    assert resp.status_code == 200
    vehicle = resp.get_json()['vehicle']

    # The move was stripped: still company A, marker untouched.
    assert vehicle['company_id'] == COMPANY_ID
    assert vehicle['transferred_from_company_id'] is None
    # The legitimate field flowed through.
    assert vehicle['current_price'] == 12345

    # And prove it at the source: the two protected keys never even reached
    # the service, while current_price did.
    assert 'company_id' not in captured['data']
    assert 'transferred_from_company_id' not in captured['data']
    assert captured['data']['current_price'] == 12345


def test_put_vehicle_strips_company_id_even_when_sole_field(client, monkeypatch):
    """A PUT whose ONLY field is company_id must not reassign the company —
    the stripped body is empty, so update_vehicle is handed nothing that
    changes ownership."""
    base = _own_vehicle(1, company_id=COMPANY_ID)
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle', lambda vid: dict(base))
    captured = _capturing_update_vehicle(monkeypatch, base)

    resp = client.put('/api/carpark/vehicles/1', json={'company_id': OTHER_COMPANY_ID})
    assert resp.status_code == 200
    assert resp.get_json()['vehicle']['company_id'] == COMPANY_ID
    assert 'company_id' not in captured['data']


# ── FINANCE GATING ────────────────────────────────────────────────────────

def _canned_summary():
    return {
        'rows': [{
            'id': 1, 'vin': 'TESTVIN0000000001', 'brand': 'TestBrand', 'model': 'TestModel',
            'status': 'SOLD', 'sale_price': 15000,
            'acquisition_price': 12000, 'total_costs': 1000,
            'gross_margin': 2000, 'margin_pct': 13.3, 'bonus_leasing': 300,
        }],
        'stage_counts': {'vandut': 1, 'all': 1},
        'totals': {'acquisition_price': 12000, 'total_costs': 1000,
                   'sale_price': 15000, 'gross_margin': 2000},
        'total': 1, 'page': 1, 'per_page': 25,
    }


def test_summary_strips_finance_fields_for_non_finance_user(client, monkeypatch):
    _set_user(monkeypatch, FakeUser(can_view_carpark_finance=False))
    monkeypatch.setattr(dispo_mod._dispo_repo, 'summary', lambda *a, **k: _canned_summary())

    resp = client.get('/api/carpark/dispo/summary')
    body = resp.get_json()
    row = body['rows'][0]

    for field in ('acquisition_price', 'total_costs', 'gross_margin', 'margin_pct', 'bonus_leasing'):
        assert field not in row, f'{field} should be stripped for non-finance user'
    assert row['sale_price'] == 15000  # sale_price is kept
    assert body['totals'] is None


def test_summary_includes_finance_fields_for_finance_user(client, monkeypatch):
    _set_user(monkeypatch, FakeUser(can_view_carpark_finance=True))
    monkeypatch.setattr(dispo_mod._dispo_repo, 'summary', lambda *a, **k: _canned_summary())

    resp = client.get('/api/carpark/dispo/summary')
    body = resp.get_json()
    row = body['rows'][0]

    for field in ('acquisition_price', 'total_costs', 'gross_margin', 'margin_pct', 'bonus_leasing'):
        assert field in row, f'{field} should be present for finance user'
    assert body['totals'] is not None
    assert body['totals']['gross_margin'] == 2000


def test_kpis_strips_gross_margin_mtd_for_non_finance_user(client, monkeypatch):
    _set_user(monkeypatch, FakeUser(can_view_carpark_finance=False))
    monkeypatch.setattr(dispo_mod._dispo_repo, 'kpis', lambda *a, **k: {
        'cars_in_stock': 5, 'reserved': 1, 'sold_this_month': 2,
        'delivered_this_month': 1, 'avg_days_in_stock': 30, 'aged_over_60': 0,
        'gross_margin_mtd': 4000,
    })
    resp = client.get('/api/carpark/dispo/kpis')
    body = resp.get_json()
    assert 'gross_margin_mtd' not in body
    assert body['cars_in_stock'] == 5


def test_kpis_includes_gross_margin_mtd_for_finance_user(client, monkeypatch):
    _set_user(monkeypatch, FakeUser(can_view_carpark_finance=True))
    monkeypatch.setattr(dispo_mod._dispo_repo, 'kpis', lambda *a, **k: {
        'cars_in_stock': 5, 'reserved': 1, 'sold_this_month': 2,
        'delivered_this_month': 1, 'avg_days_in_stock': 30, 'aged_over_60': 0,
        'gross_margin_mtd': 4000,
    })
    resp = client.get('/api/carpark/dispo/kpis')
    assert resp.get_json()['gross_margin_mtd'] == 4000


def test_summary_xlsx_export_returns_spreadsheet_mimetype(client, monkeypatch):
    _set_user(monkeypatch, FakeUser(can_view_carpark_finance=True))
    monkeypatch.setattr(dispo_mod._dispo_repo, 'summary', lambda *a, **k: _canned_summary())

    resp = client.get('/api/carpark/dispo/summary?export=xlsx')
    assert resp.status_code == 200
    assert resp.mimetype == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    assert len(resp.data) > 0


# ── IMPORT ROUTE — IDOR self-scoping + generic 500 ───────────────────────

import io as _io  # noqa: E402


class _FakeReport:
    """Stand-in for ImportService's ImportReport — only needs to_dict()."""
    def __init__(self, company_id):
        self._company_id = company_id

    def to_dict(self):
        return {'dry_run': True, 'company_id': self._company_id, 'total': 0,
                'ok': 0, 'rejects': 0, 'cross_company': 0, 'rows': []}


def _xlsx_upload(company_id_field=None):
    """Build a multipart form dict for the import route. The bytes don't
    have to be a real workbook — _importer.run is monkeypatched in these
    tests — they only need to be non-empty with a .xlsx filename."""
    data = {'file': (_io.BytesIO(b'PK\x03\x04 not-a-real-xlsx-body'), 'centralizator.xlsx')}
    if company_id_field is not None:
        data['company_id'] = str(company_id_field)
    return data


def test_import_route_ignores_client_company_id_and_uses_callers_company(client, monkeypatch):
    """IDOR guard: a client-supplied company_id form field must be ignored —
    the write target is always the authenticated caller's own company."""
    _set_user(monkeypatch, FakeUser(company_id=COMPANY_ID))

    captured = {}

    def _fake_run(stream, company_id, dry_run=True):
        captured['company_id'] = company_id
        captured['dry_run'] = dry_run
        return _FakeReport(company_id)

    monkeypatch.setattr(dispo_mod._importer, 'run', _fake_run)

    # Caller is company 10 but tries to aim the import at company 99999.
    resp = client.post(
        '/api/carpark/dispo/import',
        data=_xlsx_upload(company_id_field=99999),
        content_type='multipart/form-data',
    )
    assert resp.status_code == 200
    # The importer must have been called with the CALLER's company, not the
    # attacker-supplied 99999.
    assert captured['company_id'] == COMPANY_ID
    assert captured['dry_run'] is True
    assert resp.get_json()['company_id'] == COMPANY_ID


def test_import_route_commit_requires_delete_permission(client, monkeypatch):
    _set_user(monkeypatch, FakeUser(can_delete_carpark=False))
    monkeypatch.setattr(dispo_mod._importer, 'run',
                         lambda *a, **k: _FakeReport(COMPANY_ID))
    resp = client.post(
        '/api/carpark/dispo/import?commit=true',
        data=_xlsx_upload(),
        content_type='multipart/form-data',
    )
    assert resp.status_code == 403


# ── CLIENTS — CARPARK-SCOPED CRM SEARCH ──────────────────────────────────
#
# /api/carpark/clients/search (vehicles.py) exists so a CarPark editor
# without field-sales access isn't 403'd by /api/field-sales/clients/search's
# field_sales_required gate. It delegates to the same ClientFSRepository the
# field_sales route uses (no duplicated SQL), scoped to the caller's own
# company only.

def test_client_search_requires_min_query_length(client):
    resp = client.get('/api/carpark/clients/search?q=a')
    assert resp.status_code == 400
    assert 'error' in resp.get_json()


def test_client_search_requires_carpark_access(client, monkeypatch):
    _set_user(monkeypatch, FakeUser(can_access_carpark=False))
    resp = client.get('/api/carpark/clients/search?q=popescu')
    assert resp.status_code == 403


def test_client_search_returns_success_shape(client, monkeypatch):
    monkeypatch.setattr(vehicles_mod._client_repo, 'search_clients',
                         lambda *a, **k: [{'id': 1, 'display_name': 'Popescu Vasile'}])

    resp = client.get('/api/carpark/clients/search?q=popescu')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert body['count'] == 1
    assert body['clients'][0]['display_name'] == 'Popescu Vasile'


def test_client_search_scopes_to_callers_company(client, monkeypatch):
    """The caller's OWN company only — NOT field_sales' allowed-companies
    logic — is what gates the search, regardless of any company_id the
    client might pass."""
    captured = {}

    def _search(query, limit=20, company_ids=None):
        captured['query'] = query
        captured['limit'] = limit
        captured['company_ids'] = company_ids
        return []
    monkeypatch.setattr(vehicles_mod._client_repo, 'search_clients', _search)

    resp = client.get('/api/carpark/clients/search?q=popescu&company_id=99999')
    assert resp.status_code == 200
    assert captured['query'] == 'popescu'
    assert captured['company_ids'] == [COMPANY_ID]


def test_client_search_no_company_returns_empty_without_hitting_repo(client, monkeypatch):
    _set_user(monkeypatch, FakeUser(company_id=None))
    called = []
    monkeypatch.setattr(vehicles_mod._client_repo, 'search_clients',
                         lambda *a, **k: called.append(1))

    resp = client.get('/api/carpark/clients/search?q=popescu')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {'success': True, 'clients': [], 'count': 0}
    assert called == []


def test_import_route_generic_500_does_not_leak_internals(client, monkeypatch):
    """A forced unexpected error must return a generic body — no exception
    text / traceback / internal detail in the response."""
    _set_user(monkeypatch, FakeUser())

    def _boom(*a, **k):
        raise RuntimeError('secret internal detail: table carpark_vehicles column xyz')

    monkeypatch.setattr(dispo_mod._importer, 'run', _boom)

    resp = client.post(
        '/api/carpark/dispo/import',
        data=_xlsx_upload(),
        content_type='multipart/form-data',
    )
    assert resp.status_code == 500
    body = resp.get_json()
    assert body == {'error': 'Internal error'}
    assert 'secret internal detail' not in resp.get_data(as_text=True)
