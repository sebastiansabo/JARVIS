# jarvis/tests/carpark/test_sale_documents_routes.py
"""Sale-document routes (generate/preview/save) + leasing-companies
directory — Task 6 of the CarPark "Documente vanzare" plan.

Mirrors the harness in test_autovit_routes_auth.py / test_documents_routes.py:
a bare Flask app with only carpark_bp registered, LOGIN_DISABLED=True (makes
flask_login's `@login_required` a no-op absent a real LoginManager), and
`current_user` monkeypatched directly in every module that reads it at call
time (carpark.routes.vehicles for the permission decorators + ownership
check, carpark.routes.sale_documents for the route bodies). The facade/repos
are patched so no real DB or Google Drive call ever happens.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
import pytest
from flask import Flask, jsonify

from carpark import carpark_bp
import carpark.routes.vehicles as vehicles_mod
import carpark.routes.sale_documents as sale_docs_routes


class AdminUser:
    is_authenticated = True
    id = 1
    name = 'Admin'
    company_id = 10
    can_access_carpark = True
    can_edit_carpark = True
    can_view_carpark_finance = True
    can_access_settings = True


class NoEditUser:
    # CarPark access but no edit permission — must be rejected by
    # carpark_edit_required on every sale-document / leasing-company route.
    is_authenticated = True
    id = 2
    name = 'Viewer'
    company_id = 10
    can_access_carpark = True
    can_edit_carpark = False
    can_view_carpark_finance = False
    can_access_settings = False


def _set_user(monkeypatch, user):
    monkeypatch.setattr(vehicles_mod, 'current_user', user)
    monkeypatch.setattr(sale_docs_routes, 'current_user', user)


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(carpark_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    return app.test_client()


@pytest.fixture
def vehicle():
    return {
        'id': 42, 'company_id': 10, 'vin': 'VIN123', 'brand': 'Audi',
        'salesperson_user_id': None, 'buyer_client_id': None,
    }


# ── generate ──

def test_generate_contract_streams_pdf(client, monkeypatch, vehicle):
    _set_user(monkeypatch, AdminUser())
    monkeypatch.setattr(sale_docs_routes, '_verify_vehicle_ownership', lambda vid: (vehicle, None))
    monkeypatch.setattr(
        sale_docs_routes, 'generate_sale_document',
        lambda vehicle_id, doc_type, form: (b'%PDF-1.4 fake pdf bytes', 'contract_vanzare_VIN123.pdf')
    )
    r = client.post('/api/carpark/vehicles/42/sale-documents/generate',
                     json={'doc_type': 'contract', 'form': {'contract_number': '7'}})
    assert r.status_code == 200
    assert r.content_type == 'application/pdf'
    assert r.data.startswith(b'%PDF')


def test_generate_missing_contract_number_400(client, monkeypatch, vehicle):
    _set_user(monkeypatch, AdminUser())
    monkeypatch.setattr(sale_docs_routes, '_verify_vehicle_ownership', lambda vid: (vehicle, None))

    def _raise(vehicle_id, doc_type, form):
        raise ValueError('Numărul contractului este obligatoriu.')
    monkeypatch.setattr(sale_docs_routes, 'generate_sale_document', _raise)

    r = client.post('/api/carpark/vehicles/42/sale-documents/generate',
                     json={'doc_type': 'contract', 'form': {}})
    assert r.status_code == 400
    assert 'obligatoriu' in r.get_json()['error']


def test_generate_unknown_vehicle_404(client, monkeypatch):
    _set_user(monkeypatch, AdminUser())
    monkeypatch.setattr(
        sale_docs_routes, '_verify_vehicle_ownership',
        lambda vid: (None, (jsonify({'error': 'Vehicle not found'}), 404))
    )
    r = client.post('/api/carpark/vehicles/999/sale-documents/generate',
                     json={'doc_type': 'contract', 'form': {}})
    assert r.status_code == 404


def test_generate_requires_edit_permission_403(client, monkeypatch, vehicle):
    _set_user(monkeypatch, NoEditUser())
    # Not reached, but patch defensively so a permission bug can't be masked
    # by an AttributeError turning into some other status code.
    monkeypatch.setattr(sale_docs_routes, '_verify_vehicle_ownership', lambda vid: (vehicle, None))
    r = client.post('/api/carpark/vehicles/42/sale-documents/generate',
                     json={'doc_type': 'contract', 'form': {}})
    assert r.status_code == 403


# ── save ──

def test_save_drive_disabled_400(client, monkeypatch, vehicle):
    _set_user(monkeypatch, AdminUser())
    monkeypatch.setattr(sale_docs_routes, '_verify_vehicle_ownership', lambda vid: (vehicle, None))
    monkeypatch.setattr(sale_docs_routes, 'DRIVE_ENABLED', False)
    r = client.post('/api/carpark/vehicles/42/sale-documents/save',
                     json={'doc_type': 'contract', 'form': {'contract_number': '7'}})
    assert r.status_code == 400
    assert 'Drive' in r.get_json()['error']


def test_save_creates_document_row(client, monkeypatch, vehicle):
    _set_user(monkeypatch, AdminUser())
    monkeypatch.setattr(sale_docs_routes, '_verify_vehicle_ownership', lambda vid: (vehicle, None))
    monkeypatch.setattr(sale_docs_routes, 'DRIVE_ENABLED', True)
    monkeypatch.setattr(
        sale_docs_routes, 'generate_sale_document',
        lambda vehicle_id, doc_type, form: (b'%PDF-1.4 fake', 'contract_vanzare_VIN123.pdf')
    )
    monkeypatch.setattr(
        sale_docs_routes, 'upload_invoice_to_drive',
        lambda *a, **kw: 'https://drive.google.com/file/d/fake/view'
    )

    captured = {}

    class FakeDocumentRepository:
        def create(self, vehicle_id, data):
            captured['vehicle_id'] = vehicle_id
            captured['data'] = data
            return dict(id=1, vehicle_id=vehicle_id, **data)

    monkeypatch.setattr(sale_docs_routes, 'DocumentRepository', FakeDocumentRepository)

    r = client.post('/api/carpark/vehicles/42/sale-documents/save',
                     json={'doc_type': 'contract', 'form': {'contract_number': '7'}})
    assert r.status_code == 201
    assert captured['vehicle_id'] == 42
    assert captured['data']['document_type'] == 'contract_vanzare'
    assert captured['data']['file_url'] == 'https://drive.google.com/file/d/fake/view'
    assert r.get_json()['document']['document_type'] == 'contract_vanzare'


# ── leasing companies ──

def test_leasing_list_and_create(client, monkeypatch):
    _set_user(monkeypatch, AdminUser())

    class FakeLeasingCompanyRepository:
        def list_all(self):
            return [{'id': 1, 'name': 'BT Leasing'}]

        def create(self, data, created_by):
            return {'id': 2, 'name': data.get('name'), 'created_by': created_by}

    monkeypatch.setattr(sale_docs_routes, 'LeasingCompanyRepository', FakeLeasingCompanyRepository)

    r = client.get('/api/carpark/leasing-companies')
    assert r.status_code == 200
    assert r.get_json()['leasing_companies'] == [{'id': 1, 'name': 'BT Leasing'}]

    r = client.post('/api/carpark/leasing-companies', json={'name': 'New Leasing Co'})
    assert r.status_code == 201
    body = r.get_json()['leasing_company']
    assert body['name'] == 'New Leasing Co'
    assert body['created_by'] == 1
