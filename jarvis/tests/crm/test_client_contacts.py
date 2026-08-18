import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
import pytest
from flask import Flask
from crm import crm_bp
import crm.routes.clients as clients_mod
import crm.routes._shared as shared


class FakeUser:
    is_authenticated = True
    role_id = None
    can_access_crm = True
    company_id = None


class FakeContacts:
    # Contact 9 belongs to client 5; contact 99 belongs to another client (7)
    # to prove cross-client contact_id tampering is rejected with a 404.
    def __init__(self):
        self.created = None
        self.updated = None
        self.deleted = None
        self._by_id = {
            9: {'id': 9, 'client_id': 5, 'full_name': 'Ion'},
            99: {'id': 99, 'client_id': 7, 'full_name': 'Alt'},
        }

    def list_by_client(self, client_id):
        return [{'id': 1, 'client_id': client_id, 'full_name': 'Ion', 'is_primary': True}]

    def get(self, contact_id):
        return self._by_id.get(contact_id)

    def create(self, client_id, data):
        self.created = (client_id, data)
        return {'id': 2, 'client_id': client_id, **data, 'is_primary': True}

    def update(self, contact_id, data):
        self.updated = (contact_id, data)
        return {'id': contact_id, **data}

    def delete(self, contact_id):
        self.deleted = contact_id
        return True


@pytest.fixture
def client(monkeypatch):
    fake = FakeContacts()
    monkeypatch.setattr(clients_mod, '_contact_repo', fake)
    monkeypatch.setattr(shared, 'current_user', FakeUser())
    app = Flask(__name__)
    app.register_blueprint(crm_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    app._fake = fake
    return app.test_client()


def test_list_contacts(client):
    r = client.get('/api/crm/clients/5/contacts')
    assert r.status_code == 200
    assert r.get_json()['contacts'][0]['full_name'] == 'Ion'


def test_create_contact(client):
    r = client.post('/api/crm/clients/5/contacts', json={'full_name': 'Ana', 'phone': '072'})
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is True
    assert body['contact']['full_name'] == 'Ana'
    assert client.application._fake.created[0] == 5
    assert client.application._fake.created[1]['full_name'] == 'Ana'


def test_create_contact_requires_full_name(client):
    r = client.post('/api/crm/clients/5/contacts', json={'phone': '072'})
    assert r.status_code == 400
    assert r.get_json()['success'] is False


def test_update_contact(client):
    r = client.put('/api/crm/clients/5/contacts/9', json={'phone': '073'})
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is True
    assert client.application._fake.updated == (9, {'phone': '073'})


def test_delete_contact(client):
    r = client.delete('/api/crm/clients/5/contacts/9')
    assert r.status_code == 200
    assert r.get_json()['success'] is True
    assert client.application._fake.deleted == 9


def test_update_contact_mismatched_client_404(client):
    # Contact 99 belongs to client 7, not 5 — must not be mutable via client 5's path.
    r = client.put('/api/crm/clients/5/contacts/99', json={'phone': '073'})
    assert r.status_code == 404
    assert r.get_json()['success'] is False
    assert client.application._fake.updated is None


def test_delete_contact_mismatched_client_404(client):
    r = client.delete('/api/crm/clients/5/contacts/99')
    assert r.status_code == 404
    assert r.get_json()['success'] is False
    assert client.application._fake.deleted is None


def test_gate_valid_requires_all_fields():
    from crm.routes.clients import contact_gate_valid
    full = {'full_name': 'A', 'email': 'a@b.ro', 'phone': '072',
            'driver_license_photo': 'data:...', 'driver_license_serie': 'CJ',
            'driver_license_number': '123456'}
    assert contact_gate_valid(full) is True
    assert contact_gate_valid({**full, 'email': None}) is False
