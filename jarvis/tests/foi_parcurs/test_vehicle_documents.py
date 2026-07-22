import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
import pytest
from flask import Flask
from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.vehicles as veh_mod


class FakeVehicleRepo:
    def __init__(self):
        self.vehicles = {
            1: {
                'id': 1, 'vin': 'WAUZZZ1', 'registration_number': 'SB 01 ABC',
                'insurance_doc': 'data:application/pdf;base64,JVBERi0x',
                'talon_doc': 'data:image/jpeg;base64,/9j/4AAQ',
                'civ_doc': None, 'registration_doc': None, 'offer_doc': None,
            },
        }

    def get_by_id(self, vehicle_id):
        return self.vehicles.get(vehicle_id)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(veh_mod, '_vehicle_repo', FakeVehicleRepo())
    app = Flask(__name__)
    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    return app.test_client()


def test_get_pdf_document(client):
    r = client.get('/api/foi-parcurs/vehicles/1/documents/insurance')
    assert r.status_code == 200
    body = r.get_json()
    assert body['type'] == 'insurance'
    assert body['data_url'].startswith('data:application/pdf')
    assert body['filename'] == 'Asigurare_SB01ABC.pdf'


def test_get_image_document_extension(client):
    r = client.get('/api/foi-parcurs/vehicles/1/documents/talon')
    assert r.status_code == 200
    assert r.get_json()['filename'].endswith('.jpg')


def test_empty_document_404(client):
    r = client.get('/api/foi-parcurs/vehicles/1/documents/civ')
    assert r.status_code == 404


def test_unknown_type_400(client):
    r = client.get('/api/foi-parcurs/vehicles/1/documents/bogus')
    assert r.status_code == 400


def test_unknown_vehicle_404(client):
    r = client.get('/api/foi-parcurs/vehicles/999/documents/insurance')
    assert r.status_code == 404
