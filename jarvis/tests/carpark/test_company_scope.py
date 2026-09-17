"""Company-switcher scoping: /api/carpark/companies returns only the
companies a non-Admin may act on; Admin gets all. Real app + mocked service,
mirrors tests/carpark/test_acting_company.py."""
import os
from unittest import mock

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
import app as app_module
from app import app as flask_app
from carpark.routes import vehicles as vehicles_module


@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    return flask_app.test_client()


def _login(client, monkeypatch, uid, company_id=1, **overrides):
    user = {'id': uid, 'email': f't{uid}@x.com', 'name': 'T', 'company_id': company_id,
            'can_access_carpark': True, 'can_edit_carpark': True}
    user.update(overrides)
    monkeypatch.setattr(app_module._user_repo, 'get_by_id', lambda _u: user)
    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)


def test_non_admin_gets_scoped_companies(client, monkeypatch):
    _login(client, monkeypatch, uid=93001, company_id=1)
    monkeypatch.setattr(vehicles_module, 'get_actable_company_ids', lambda _u: {1, 4})
    with mock.patch.object(vehicles_module._vehicle_service, 'get_companies',
                            return_value=[{'id': 1, 'name': 'A'}, {'id': 4, 'name': 'D'}]) as gc:
        r = client.get('/api/carpark/companies')
    assert r.status_code == 200
    assert gc.call_args.kwargs.get('company_ids') == {1, 4} or gc.call_args.args[0] == {1, 4}


def test_admin_gets_all_companies(client, monkeypatch):
    _login(client, monkeypatch, uid=93002, company_id=1, can_access_settings=True)
    with mock.patch.object(vehicles_module._vehicle_service, 'get_companies',
                            return_value=[{'id': 1, 'name': 'A'}]) as gc:
        r = client.get('/api/carpark/companies')
    assert r.status_code == 200
    passed = gc.call_args.kwargs.get('company_ids', gc.call_args.args[0] if gc.call_args.args else None)
    assert passed is None
