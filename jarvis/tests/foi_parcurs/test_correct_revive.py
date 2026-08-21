"""Tests for the correct-endpoint status revive + status-change logging.

Correcting a MISSED (or late-PLANNED) session into an active window (departure
passed, return still in the future) revives it to FILLED ("În desfășurare"),
keeps the Modificat marker (corrected_at), and logs the status change.

Flask test client with contracts route deps mocked at module level.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask
from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes.contracts as contracts_mod


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    monkeypatch.setattr(contracts_mod, '_is_admin', lambda: True)
    return app.test_client()


MISSED_SESSION = {
    'id': 55, 'route_type': 'TD', 'status': 'MISSED',
    'departure_datetime': '2026-08-20T13:16:00', 'return_datetime': '2026-08-21T10:00:00',
    'km_start': 1000, 'km_end': 1000,
}


def test_correct_revives_missed_to_filled_and_logs_status(client, monkeypatch):
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda i: dict(MISSED_SESSION))
    monkeypatch.setattr(contracts_mod._fp_repo, 'correct_session',
                        lambda i, fields, by=None: {**MISSED_SESSION, **fields, 'corrected_at': 'now'})
    monkeypatch.setattr(contracts_mod._fp_repo, 'revive_to_active_if_window_open',
                        lambda i: {**MISSED_SESSION, 'status': 'FILLED', 'corrected_at': 'now'})
    logged = []
    monkeypatch.setattr(contracts_mod._fp_repo, 'log_session_event',
                        lambda sid, action, actor=None: logged.append((sid, action)))

    r = client.put('/api/foi-parcurs/contracts/55/correct',
                   json={'return_datetime': '2026-08-27T14:16:00'})
    assert r.status_code == 200, r.get_json()
    # Revived to FILLED → renders "În desfășurare"; Modificat marker kept.
    assert r.get_json()['contract']['status'] == 'FILLED'
    assert r.get_json()['contract']['corrected_at']
    # Both the status transition and the correct action are in the history.
    assert (55, 'status:MISSED:FILLED') in logged
    assert (55, 'correct') in logged


def test_correct_without_active_window_keeps_status(client, monkeypatch):
    """Correcting a MISSED session whose window is NOT currently active (revive
    returns None) leaves the status untouched and logs no status change."""
    monkeypatch.setattr(contracts_mod._fp_repo, 'get_contract_by_id', lambda i: dict(MISSED_SESSION))
    monkeypatch.setattr(contracts_mod._fp_repo, 'correct_session',
                        lambda i, fields, by=None: {**MISSED_SESSION, **fields})
    monkeypatch.setattr(contracts_mod._fp_repo, 'revive_to_active_if_window_open', lambda i: None)
    logged = []
    monkeypatch.setattr(contracts_mod._fp_repo, 'log_session_event',
                        lambda sid, action, actor=None: logged.append((sid, action)))

    r = client.put('/api/foi-parcurs/contracts/55/correct',
                   json={'return_datetime': '2026-08-27T14:16:00'})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['contract']['status'] == 'MISSED'
    assert not any(a.startswith('status:') for _, a in logged)
    assert (55, 'correct') in logged
