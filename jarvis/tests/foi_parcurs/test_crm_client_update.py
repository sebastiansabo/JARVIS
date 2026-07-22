import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
import pytest
from flask import Flask
from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.test_drive as td_mod


class FakeRepo:
    def __init__(self):
        self.calls = []
        self.existing = {1}

    def update(self, client_id, data):
        self.calls.append((client_id, data))
        if client_id not in self.existing:
            return None
        return {'id': client_id, 'phone': data.get('phone'), 'email': data.get('email')}


@pytest.fixture
def client(monkeypatch):
    fake = FakeRepo()
    monkeypatch.setattr(td_mod, '_crm_client_repo', fake)
    app = Flask(__name__)
    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    app._fake_repo = fake
    return app.test_client()


def test_update_phone_and_email(client):
    r = client.patch('/api/foi-parcurs/crm-clients/1',
                     json={'phone': '0712 345-678', 'email': 'a@b.ro'})
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is True
    assert body['client']['phone'] == '0712345678'  # spaces/dashes stripped
    assert body['client']['email'] == 'a@b.ro'


def test_update_email_only(client):
    r = client.patch('/api/foi-parcurs/crm-clients/1', json={'email': 'x@y.ro'})
    assert r.status_code == 200
    # phone must NOT be part of the update when not supplied
    _, data = client.application._fake_repo.calls[-1]
    assert 'phone' not in data
    assert data['email'] == 'x@y.ro'


def test_update_invalid_phone(client):
    r = client.patch('/api/foi-parcurs/crm-clients/1', json={'phone': '12345'})
    assert r.status_code == 400
    assert 'Invalid phone' in r.get_json()['error']


def test_update_empty_body(client):
    r = client.patch('/api/foi-parcurs/crm-clients/1', json={})
    assert r.status_code == 400


def test_update_unknown_id(client):
    r = client.patch('/api/foi-parcurs/crm-clients/999', json={'email': 'z@z.ro'})
    assert r.status_code == 404
