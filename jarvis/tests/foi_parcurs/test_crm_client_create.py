import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
import pytest
from flask import Flask
from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.test_drive as td_mod


class FakeRepo:
    """In-memory stand-in for the CRM client repo. `create` mints an id;
    `execute` records the post-create UPDATE(s); `get_by_id` returns the row."""

    def __init__(self):
        self.rows = {}
        self._next = 10
        self.execute_calls = []

    def create(self, **kwargs):
        cid = self._next
        self._next += 1
        self.rows[cid] = {
            'id': cid,
            'display_name': kwargs.get('display_name'),
            'phone': kwargs.get('phone'),
            'email': kwargs.get('email'),
            'cnp': None,
            'driver_license_number': None,
            'driver_license_expiry': None,
        }
        return {'id': cid}

    def execute(self, sql, params=None):
        self.execute_calls.append((sql, params))
        return None

    def get_by_id(self, client_id):
        return self.rows.get(client_id)


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


def test_create_persists_scanned_license(client):
    """A client created from the Test Drive scan must persist the scanned
    driver_license_number + expiry, so the drive's client-license gate passes
    and the number is reusable next time."""
    r = client.post('/api/foi-parcurs/crm-clients', json={
        'display_name': 'Ion Pop',
        'phone': '+40721234567',
        'driver_license_number': 'B123456',
        'driver_license_expiry': '2030-01-01',
    })
    assert r.status_code == 200, r.get_json()
    calls = client.application._fake_repo.execute_calls
    lic = [c for c in calls if 'driver_license_number' in c[0]]
    assert lic, 'handler must persist the scanned driver_license_number'
    _, params = lic[0]
    assert 'B123456' in params
    assert '2030-01-01' in params


def test_create_without_license_no_license_update(client):
    """No license supplied → the handler issues no license UPDATE."""
    r = client.post('/api/foi-parcurs/crm-clients', json={
        'display_name': 'Ana Ion',
        'phone': '+40721234567',
    })
    assert r.status_code == 200
    calls = client.application._fake_repo.execute_calls
    assert not any('driver_license_number' in c[0] for c in calls)
