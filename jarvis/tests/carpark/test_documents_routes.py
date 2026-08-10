"""Tests for the Documents + checklist + timeline HTTP routes
(carpark/routes/documents.py) plus a focused unit test of
DispoRepository.timeline's merge/sort logic.

Mock-based, mirroring test_dispo_routes.py: a minimal Flask app registers
carpark_bp, LOGIN_DISABLED=True makes @login_required a no-op, and
`current_user` is monkeypatched directly onto every module that references
it at call time (carpark.routes.vehicles — where the carpark_required
family and _verify_vehicle_ownership/_user_company_id live — plus
documents.py itself, which does its own `from flask_login import
current_user`).

No real DB access for the route tests: _vehicle_service (imported into
vehicles.py), documents_mod._document_repo, ._dispo_repo, and
._dispo_service module-level singletons are monkeypatched per test, so
these exercise only the route layer (auth gating, delegation, exception ->
status code mapping, the cross-tenant DELETE guard) — not
DocumentRepository/DispoRepository/DispoService themselves.

The one exception is test_timeline_merges_and_sorts_events, which
exercises DispoRepository.timeline's real merge/sort code directly (no
Flask involved) by monkeypatching only its query_one/query_all — the
lowest layer that would otherwise need a real DB.
"""
import io
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

from carpark import carpark_bp
import carpark.routes.vehicles as vehicles_mod
import carpark.routes.documents as documents_mod

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
    """current_user is read from two different module namespaces at call
    time (see module docstring) — both must be patched together."""
    monkeypatch.setattr(vehicles_mod, 'current_user', user)
    monkeypatch.setattr(documents_mod, 'current_user', user)


def _own_vehicle(vehicle_id=1, company_id=COMPANY_ID, **overrides):
    v = {'id': vehicle_id, 'company_id': company_id, 'status': 'READY_FOR_SALE',
         'brand': 'TestBrand', 'vin': 'TESTVIN0000000001'}
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

def test_list_documents_route_registered(client, monkeypatch):
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle', lambda vid: _own_vehicle(vid))
    monkeypatch.setattr(documents_mod._document_repo, 'list_for_vehicle', lambda vid: [])
    resp = client.get('/api/carpark/vehicles/1/documents')
    assert resp.status_code == 200
    assert resp.get_json() == {'documents': []}


def test_checklist_route_registered(client, monkeypatch):
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle', lambda vid: _own_vehicle(vid))
    monkeypatch.setattr(documents_mod._dispo_service, 'checklist', lambda vid, cid: {
        'required': [], 'present': [], 'missing': [], 'blocks_delivery': False})
    resp = client.get('/api/carpark/vehicles/1/documents/checklist')
    assert resp.status_code == 200


def test_timeline_route_registered(client, monkeypatch):
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle', lambda vid: _own_vehicle(vid))
    monkeypatch.setattr(documents_mod._dispo_repo, 'timeline', lambda vid: [])
    resp = client.get('/api/carpark/vehicles/1/timeline')
    assert resp.status_code == 200
    assert resp.get_json() == {'timeline': []}


def test_list_documents_cross_tenant_returns_404(client, monkeypatch):
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle',
                         lambda vid: _own_vehicle(vid, company_id=OTHER_COMPANY_ID))
    resp = client.get('/api/carpark/vehicles/1/documents')
    assert resp.status_code == 404


# ── CREATE — LINK MODE ───────────────────────────────────────────────────

def test_create_document_link_mode_stores_row(client, monkeypatch):
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle', lambda vid: _own_vehicle(vid))
    calls = {}

    def _create(vehicle_id, data):
        calls['vehicle_id'] = vehicle_id
        calls['data'] = data
        return {'id': 1, 'vehicle_id': vehicle_id, **data}
    monkeypatch.setattr(documents_mod._document_repo, 'create', _create)

    resp = client.post('/api/carpark/vehicles/1/documents', json={
        'document_type': 'pv_intrare',
        'file_url': 'https://example.com/doc.pdf',
        'title': 'PV Intrare',
    })
    assert resp.status_code == 201
    assert calls['vehicle_id'] == 1
    assert calls['data']['document_type'] == 'pv_intrare'
    assert calls['data']['file_url'] == 'https://example.com/doc.pdf'
    assert calls['data']['title'] == 'PV Intrare'
    assert calls['data']['uploaded_by'] == 1  # FakeUser().id


def test_create_document_link_mode_accepts_dms_document_id_alone(client, monkeypatch):
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle', lambda vid: _own_vehicle(vid))
    calls = {}

    def _create(vehicle_id, data):
        calls['data'] = data
        return {'id': 2, 'vehicle_id': vehicle_id, **data}
    monkeypatch.setattr(documents_mod._document_repo, 'create', _create)

    resp = client.post('/api/carpark/vehicles/1/documents', json={
        'document_type': 'civ', 'dms_document_id': 555,
    })
    assert resp.status_code == 201
    assert calls['data']['dms_document_id'] == 555


def test_create_document_link_mode_requires_file_url_or_dms_id(client, monkeypatch):
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle', lambda vid: _own_vehicle(vid))
    resp = client.post('/api/carpark/vehicles/1/documents', json={'document_type': 'pv_intrare'})
    assert resp.status_code == 400


def test_create_document_missing_type_returns_400(client, monkeypatch):
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle', lambda vid: _own_vehicle(vid))
    resp = client.post('/api/carpark/vehicles/1/documents', json={
        'file_url': 'https://example.com/doc.pdf'})
    assert resp.status_code == 400


def test_create_document_invalid_type_returns_400(client, monkeypatch):
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle', lambda vid: _own_vehicle(vid))
    resp = client.post('/api/carpark/vehicles/1/documents', json={
        'document_type': 'not_a_real_type', 'file_url': 'https://example.com/doc.pdf'})
    assert resp.status_code == 400


def test_create_document_requires_edit_permission(client, monkeypatch):
    _set_user(monkeypatch, FakeUser(can_edit_carpark=False))
    resp = client.post('/api/carpark/vehicles/1/documents', json={
        'document_type': 'pv_intrare', 'file_url': 'https://example.com/doc.pdf'})
    assert resp.status_code == 403


def test_create_document_cross_tenant_returns_404(client, monkeypatch):
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle',
                         lambda vid: _own_vehicle(vid, company_id=OTHER_COMPANY_ID))
    resp = client.post('/api/carpark/vehicles/1/documents', json={
        'document_type': 'pv_intrare', 'file_url': 'https://example.com/doc.pdf'})
    assert resp.status_code == 404


# ── CREATE — UPLOAD MODE ─────────────────────────────────────────────────

def test_create_document_multipart_with_drive_disabled_returns_400(client, monkeypatch):
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle', lambda vid: _own_vehicle(vid))
    monkeypatch.setattr(documents_mod, 'DRIVE_ENABLED', False)
    create_calls = []
    monkeypatch.setattr(documents_mod._document_repo, 'create',
                         lambda vid, data: create_calls.append(data))

    data = {
        'document_type': 'pv_intrare',
        'file': (io.BytesIO(b'%PDF-1.4 fake pdf bytes'), 'doc.pdf'),
    }
    resp = client.post('/api/carpark/vehicles/1/documents', data=data,
                        content_type='multipart/form-data')
    assert resp.status_code == 400
    body = resp.get_json()
    assert 'file_url' in body['error'] or 'disabled' in body['error'].lower()
    assert create_calls == []  # never reached the repo — Drive-disabled short-circuits first


def test_create_document_multipart_with_drive_enabled_uploads_and_creates(client, monkeypatch):
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle', lambda vid: _own_vehicle(vid))
    monkeypatch.setattr(documents_mod, 'DRIVE_ENABLED', True)

    upload_calls = {}

    def _fake_upload(file_bytes, filename, invoice_date, company, invoice_number, mime_type):
        upload_calls['args'] = (filename, invoice_date, company, invoice_number, mime_type)
        return 'https://drive.google.com/file/d/FAKE123/view'
    monkeypatch.setattr(documents_mod, 'upload_invoice_to_drive', _fake_upload)

    create_calls = {}

    def _create(vehicle_id, data):
        create_calls['data'] = data
        return {'id': 3, 'vehicle_id': vehicle_id, **data}
    monkeypatch.setattr(documents_mod._document_repo, 'create', _create)

    file_content = b'%PDF-1.4 fake pdf bytes'
    data = {
        'document_type': 'factura_achizitie',
        'file': (io.BytesIO(file_content), 'invoice.pdf', 'application/pdf'),
    }
    resp = client.post('/api/carpark/vehicles/1/documents', data=data,
                        content_type='multipart/form-data')
    assert resp.status_code == 201
    assert create_calls['data']['file_url'] == 'https://drive.google.com/file/d/FAKE123/view'
    assert create_calls['data']['file_size'] == len(file_content)
    assert create_calls['data']['document_type'] == 'factura_achizitie'
    assert upload_calls['args'][2] == 'TestBrand'  # company= vehicle brand


def test_create_document_upload_exceeding_size_cap_returns_400(client, monkeypatch):
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle', lambda vid: _own_vehicle(vid))
    monkeypatch.setattr(documents_mod, 'DRIVE_ENABLED', True)
    monkeypatch.setattr(documents_mod, '_MAX_UPLOAD_BYTES', 10)  # shrink cap for a fast test
    create_calls = []
    monkeypatch.setattr(documents_mod._document_repo, 'create',
                         lambda vid, data: create_calls.append(data))

    data = {
        'document_type': 'pv_intrare',
        'file': (io.BytesIO(b'x' * 100), 'big.pdf'),
    }
    resp = client.post('/api/carpark/vehicles/1/documents', data=data,
                        content_type='multipart/form-data')
    assert resp.status_code == 400
    assert create_calls == []


# ── DELETE ────────────────────────────────────────────────────────────────

def test_delete_document_unknown_returns_404(client, monkeypatch):
    monkeypatch.setattr(documents_mod._document_repo, 'get', lambda doc_id: None)
    resp = client.delete('/api/carpark/documents/999')
    assert resp.status_code == 404


def test_delete_document_cross_tenant_returns_404(client, monkeypatch):
    """The key security test: a document whose vehicle belongs to another
    company must 404 (not leak a 403 or succeed), and the actual delete
    must never be reached."""
    monkeypatch.setattr(documents_mod._document_repo, 'get',
                         lambda doc_id: {'id': doc_id, 'vehicle_id': 1, 'document_type': 'pv_intrare'})
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle',
                         lambda vid: _own_vehicle(vid, company_id=OTHER_COMPANY_ID))
    delete_calls = []
    monkeypatch.setattr(documents_mod._document_repo, 'delete',
                         lambda doc_id: delete_calls.append(doc_id) or True)

    resp = client.delete('/api/carpark/documents/5')
    assert resp.status_code == 404
    assert delete_calls == []


def test_delete_document_owned_deletes(client, monkeypatch):
    monkeypatch.setattr(documents_mod._document_repo, 'get',
                         lambda doc_id: {'id': doc_id, 'vehicle_id': 1, 'document_type': 'pv_intrare'})
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle', lambda vid: _own_vehicle(vid))
    delete_calls = []

    def _delete(doc_id):
        delete_calls.append(doc_id)
        return True
    monkeypatch.setattr(documents_mod._document_repo, 'delete', _delete)

    resp = client.delete('/api/carpark/documents/5')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True
    assert delete_calls == [5]


def test_delete_document_requires_delete_permission(client, monkeypatch):
    _set_user(monkeypatch, FakeUser(can_delete_carpark=False))
    resp = client.delete('/api/carpark/documents/5')
    assert resp.status_code == 403


# ── CHECKLIST — DELEGATION ────────────────────────────────────────────────

def test_checklist_delegates_to_dispo_service(client, monkeypatch):
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle', lambda vid: _own_vehicle(vid))
    calls = {}

    def _checklist(vehicle_id, company_id):
        calls['args'] = (vehicle_id, company_id)
        return {'required': ['pv_intrare'], 'present': [], 'missing': ['pv_intrare'],
                'blocks_delivery': True}
    monkeypatch.setattr(documents_mod._dispo_service, 'checklist', _checklist)

    resp = client.get('/api/carpark/vehicles/1/documents/checklist')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['missing'] == ['pv_intrare']
    assert body['blocks_delivery'] is True
    assert calls['args'] == (1, COMPANY_ID)


def test_checklist_cross_tenant_permission_error_returns_403(client, monkeypatch):
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle', lambda vid: _own_vehicle(vid))

    def _raise(*a, **k):
        raise PermissionError(f'Vehicle 1 does not belong to company {COMPANY_ID}')
    monkeypatch.setattr(documents_mod._dispo_service, 'checklist', _raise)

    resp = client.get('/api/carpark/vehicles/1/documents/checklist')
    assert resp.status_code == 403


# ── TIMELINE — DELEGATION ─────────────────────────────────────────────────

def test_timeline_delegates_and_returns_events(client, monkeypatch):
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle', lambda vid: _own_vehicle(vid))
    canned = [
        {'type': 'vehicle_date', 'label': 'Achiziție', 'date': '2026-01-01', 'meta': {}},
        {'type': 'document', 'label': 'pv_intrare', 'date': '2026-02-01T00:00:00', 'meta': {}},
    ]
    monkeypatch.setattr(documents_mod._dispo_repo, 'timeline', lambda vid: canned)

    resp = client.get('/api/carpark/vehicles/1/timeline')
    assert resp.status_code == 200
    events = resp.get_json()['timeline']
    assert len(events) == 2
    assert events[0]['type'] == 'vehicle_date'
    assert events[1]['type'] == 'document'


def test_timeline_cross_tenant_returns_404(client, monkeypatch):
    monkeypatch.setattr(vehicles_mod._vehicle_service, 'get_vehicle',
                         lambda vid: _own_vehicle(vid, company_id=OTHER_COMPANY_ID))
    resp = client.get('/api/carpark/vehicles/1/timeline')
    assert resp.status_code == 404


# ── DispoRepository.timeline — merge/sort unit test (no Flask, no DB) ─────

def test_timeline_merges_and_sorts_events():
    """Exercises the real merge+sort logic in DispoRepository.timeline by
    monkeypatching only its DB-facing query_one/query_all methods — proves
    the three sources (status history, vehicle lifecycle dates, documents)
    come back interleaved in true chronological order, including a
    date-vs-datetime comparison (acquisition_date is a DATE, the status
    change and document rows carry TIMESTAMPs)."""
    from datetime import date, datetime

    from carpark.repositories.dispo_repository import DispoRepository

    repo = DispoRepository()

    def fake_query_one(sql, params=None):
        assert 'FROM carpark_vehicles' in sql
        return {
            'acquisition_date': date(2026, 1, 1),
            'supplier_payment_date': None,
            'intake_pv_date': None,
            'listing_date': date(2026, 3, 1),
            'sale_date': None,
            'delivery_date': None,
            'stock_removed_date': None,
        }

    def fake_query_all(sql, params=None):
        if 'carpark_status_history' in sql:
            return [{
                'old_status': None, 'new_status': 'ACQUIRED', 'notes': None,
                'changed_by': 1, 'created_at': datetime(2026, 1, 1, 9, 0),
            }]
        if 'carpark_vehicle_documents' in sql:
            return [{
                'id': 5, 'document_type': 'pv_intrare', 'title': None,
                'upload_date': datetime(2026, 2, 1, 12, 0),
            }]
        raise AssertionError(f'unexpected query in timeline(): {sql}')

    repo.query_one = fake_query_one
    repo.query_all = fake_query_all

    events = repo.timeline(1)

    # Chronological order: acquisition_date (Jan 1 00:00) -> status_change
    # (Jan 1 09:00) -> document (Feb 1) -> listing_date (Mar 1).
    assert [e['type'] for e in events] == [
        'vehicle_date', 'status_change', 'document', 'vehicle_date',
    ]
    assert events[0]['meta']['field'] == 'acquisition_date'
    assert events[1]['meta']['new_status'] == 'ACQUIRED'
    assert events[2]['meta']['document_type'] == 'pv_intrare'
    assert events[3]['meta']['field'] == 'listing_date'

    # Every event has the documented shape.
    for event in events:
        assert set(event.keys()) == {'type', 'label', 'date', 'meta'}
