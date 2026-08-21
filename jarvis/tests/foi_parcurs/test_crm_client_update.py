import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
import json
import pytest
from flask import Flask
from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.test_drive as td_mod


class FakeRepo:
    """In-memory stand-in. Client 1 has empty contact details; client 2 already
    has phone + email + license (used to prove overwrite behaviour)."""

    def __init__(self):
        self.clients = {
            1: {'id': 1, 'phone': None, 'email': None, 'driver_license_number': None},
            2: {'id': 2, 'phone': '0700000000', 'email': 'set@already.ro',
                'driver_license_number': 'AB123456'},
        }
        self.update_calls = []
        self.audit_rows = []

    def get_by_id(self, client_id):
        return self.clients.get(client_id)

    def update(self, client_id, data):
        self.update_calls.append((client_id, data))
        row = self.clients.get(client_id)
        if row is None:
            return None
        row.update(data)
        return row

    def execute(self, sql, params=None):
        # Only the audit INSERT flows through execute() in this route.
        if 'crm_client_audit' in sql:
            self.audit_rows.append(params)
        return None


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


def test_fill_phone_and_email(client):
    r = client.patch('/api/foi-parcurs/crm-clients/1',
                     json={'phone': '0712 345-678', 'email': 'a@b.ro'})
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is True
    assert body['client']['phone'] == '0712345678'  # spaces/dashes stripped
    assert body['client']['email'] == 'a@b.ro'


def test_fill_email_only(client):
    r = client.patch('/api/foi-parcurs/crm-clients/1', json={'email': 'x@y.ro'})
    assert r.status_code == 200
    _, data = client.application._fake_repo.update_calls[-1]
    assert 'phone' not in data
    assert data['email'] == 'x@y.ro'


def test_fill_license_number(client):
    r = client.patch('/api/foi-parcurs/crm-clients/1',
                     json={'driver_license_number': 'XY987654'})
    assert r.status_code == 200
    assert r.get_json()['client']['driver_license_number'] == 'XY987654'


def test_audit_written_on_change(client):
    r = client.patch('/api/foi-parcurs/crm-clients/2', json={'email': 'fixed@correct.ro'})
    assert r.status_code == 200
    rows = client.application._fake_repo.audit_rows
    assert len(rows) == 1
    client_id, action, changes_json, user_id, source = rows[0]
    assert client_id == 2 and action == 'contact_update' and source == 'td_form'
    changes = json.loads(changes_json)
    assert changes['email'] == {'old': 'set@already.ro', 'new': 'fixed@correct.ro'}


def test_audit_skipped_when_no_effective_change(client):
    # Re-sending the SAME email must not produce an audit row.
    r = client.patch('/api/foi-parcurs/crm-clients/2', json={'email': 'set@already.ro'})
    assert r.status_code == 200
    assert client.application._fake_repo.audit_rows == []


def test_invalid_phone_rejected(client):
    r = client.patch('/api/foi-parcurs/crm-clients/1', json={'phone': '12345'})
    assert r.status_code == 400
    assert 'Invalid phone' in r.get_json()['error']


def test_empty_body_no_change(client):
    r = client.patch('/api/foi-parcurs/crm-clients/1', json={})
    assert r.status_code == 200
    # Nothing was written.
    assert client.application._fake_repo.update_calls == []


def test_unknown_id_404(client):
    r = client.patch('/api/foi-parcurs/crm-clients/999', json={'email': 'z@z.ro'})
    assert r.status_code == 404


def test_existing_values_are_overwritten(client):
    """Editing is allowed: existing phone/email are corrected in place."""
    r = client.patch('/api/foi-parcurs/crm-clients/2',
                     json={'phone': '0711111111', 'email': 'fixed@correct.ro'})
    assert r.status_code == 200
    body = r.get_json()
    assert body['client']['phone'] == '0711111111'
    assert body['client']['email'] == 'fixed@correct.ro'


def test_existing_license_is_overwritten(client):
    r = client.patch('/api/foi-parcurs/crm-clients/2',
                     json={'driver_license_number': 'NEW999'})
    assert r.status_code == 200
    assert r.get_json()['client']['driver_license_number'] == 'NEW999'


# ── widened: fiscal identity + address editable from the Driving Hub ──

def test_fill_cui(client):
    r = client.patch('/api/foi-parcurs/crm-clients/1', json={'cui': ' RO9999999 '})
    assert r.status_code == 200
    _, data = client.application._fake_repo.update_calls[-1]
    assert data['cui'] == 'RO9999999'  # trimmed


def test_edit_full_record(client):
    r = client.patch('/api/foi-parcurs/crm-clients/1', json={
        'display_name': 'ACME SRL', 'cui': 'RO123', 'nr_reg': 'J40/1/2020',
        'street': 'Str. Test 1', 'city': 'Cluj', 'region': 'Cluj',
    })
    assert r.status_code == 200
    _, data = client.application._fake_repo.update_calls[-1]
    assert data == {
        'display_name': 'ACME SRL', 'cui': 'RO123', 'nr_reg': 'J40/1/2020',
        'street': 'Str. Test 1', 'city': 'Cluj', 'region': 'Cluj',
    }


def test_empty_display_name_rejected(client):
    r = client.patch('/api/foi-parcurs/crm-clients/1', json={'display_name': '  '})
    assert r.status_code == 400
    # Must not have attempted an update.
    assert client.application._fake_repo.update_calls == []


# ── GET single client: login-gated full-record hydration for the TD form ──
# The full CRM GET (/api/crm/clients/<id>) is @crm_required, so a consilier
# without sales access cannot use it to hydrate CUI/address of a client picked
# from the lean search results. This login-gated GET mirrors the search/create/
# PATCH endpoints so the Driving Hub Client card can show/edit those fields.

def test_get_client_returns_full_record(client):
    r = client.get('/api/foi-parcurs/crm-clients/2')
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is True
    assert body['client']['id'] == 2
    assert body['client']['email'] == 'set@already.ro'


def test_get_unknown_client_404(client):
    r = client.get('/api/foi-parcurs/crm-clients/999')
    assert r.status_code == 404
    assert r.get_json()['success'] is False
