import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from unittest.mock import MagicMock
from flask import Flask
from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.test_drive as td


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def repo(monkeypatch):
    m = MagicMock()
    monkeypatch.setattr(td, '_fp_repo', m)
    return m


def _future():
    return '2999-01-01T10:00:00'


def test_reschedule_planned_ok(client, repo):
    repo.get_contract_by_id.return_value = {'id': 5, 'route_type': 'TD', 'status': 'PLANNED'}
    repo.reschedule_session.return_value = {'id': 5, 'status': 'PLANNED'}
    r = client.put('/api/foi-parcurs/test-drive/5/reschedule',
                   json={'departure_datetime': _future(), 'return_datetime': '2999-01-01T11:00:00'})
    assert r.status_code == 200
    assert r.get_json()['success'] is True
    repo.reschedule_session.assert_called_once_with(5, _future(), '2999-01-01T11:00:00')


def test_reschedule_missed_revives(client, repo):
    repo.get_contract_by_id.return_value = {'id': 6, 'route_type': 'TD', 'status': 'MISSED'}
    repo.reschedule_session.return_value = {'id': 6, 'status': 'PLANNED'}
    r = client.put('/api/foi-parcurs/test-drive/6/reschedule', json={'departure_datetime': _future()})
    assert r.status_code == 200


def test_reschedule_rejects_live(client, repo):
    repo.get_contract_by_id.return_value = {'id': 7, 'route_type': 'TD', 'status': 'FILLED'}
    r = client.put('/api/foi-parcurs/test-drive/7/reschedule', json={'departure_datetime': _future()})
    assert r.status_code == 409
    repo.reschedule_session.assert_not_called()


def test_reschedule_requires_departure(client, repo):
    repo.get_contract_by_id.return_value = {'id': 8, 'route_type': 'TD', 'status': 'PLANNED'}
    r = client.put('/api/foi-parcurs/test-drive/8/reschedule', json={})
    assert r.status_code == 400


def test_reschedule_rejects_past(client, repo):
    repo.get_contract_by_id.return_value = {'id': 9, 'route_type': 'TD', 'status': 'PLANNED'}
    r = client.put('/api/foi-parcurs/test-drive/9/reschedule',
                   json={'departure_datetime': '2000-01-01T10:00:00'})
    assert r.status_code == 400
    repo.reschedule_session.assert_not_called()
