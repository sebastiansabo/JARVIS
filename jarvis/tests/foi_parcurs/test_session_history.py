"""Tests for the Test Drive session HISTORY log:
- GET /api/foi-parcurs/test-drive/<id>/history returns the audit events.
- A mutation (extend) appends an event via repo.log_session_event.

Flask test client with FoiParcursRepository mocked at module level
(mirrors test_test_drive_return.py).
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.test_drive as test_drive_mod


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True  # login_required is a no-op
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_history_endpoint_returns_events(client, monkeypatch):
    events = [
        {'id': 2, 'action': 'return', 'actor': 'Popa Dragoș', 'created_at': '2026-08-19T15:52:00'},
        {'id': 1, 'action': 'activate', 'actor': 'Popa Dragoș', 'created_at': '2026-08-18T16:30:00'},
    ]
    monkeypatch.setattr(test_drive_mod._fp_repo, 'get_session_events', lambda sid: events)

    resp = client.get('/api/foi-parcurs/test-drive/7/history')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert body['events'] == events


def test_extend_appends_history_event(client, monkeypatch):
    monkeypatch.setattr(test_drive_mod._fp_repo, 'get_contract_by_id',
                        lambda id: {'id': id, 'route_type': 'TD', 'status': 'FILLED',
                                    'departure_datetime': None})
    monkeypatch.setattr(test_drive_mod._fp_repo, 'extend_return',
                        lambda *a, **k: {'id': 7, 'status': 'FILLED'})
    logged = []
    monkeypatch.setattr(test_drive_mod._fp_repo, 'log_session_event',
                        lambda session_id, action, actor=None: logged.append((session_id, action)))

    resp = client.put('/api/foi-parcurs/test-drive/7/extend',
                      json={'return_datetime': '2026-08-20T17:00:00'})
    assert resp.status_code == 200
    assert logged == [(7, 'extend')]
