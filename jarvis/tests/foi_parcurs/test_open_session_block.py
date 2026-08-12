"""Tests for the single-open-session rule (Feature B / Rule A):
a car that already has an OPEN (FILLED) session — TD or Comodat — cannot start
a new one. Enforced at the two live-start points (submit-now + activate), with
an admin override (allow_open_session).

Unit-tests the `open_session_block` helper directly, plus route wiring via the
Flask test client (mirrors test_test_drive_return.py).
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

from foi_parcurs import foi_parcurs_bp
import foi_parcurs.routes._shared as shared
import foi_parcurs.routes.test_drive as td_mod


# ── helper unit tests ──────────────────────────────────────────────────

def test_block_returns_409_when_car_out(monkeypatch):
    monkeypatch.setattr(shared._fp_repo, 'get_open_session',
                        lambda vin, exclude_id=None: {'id': 9, 'route_type': 'TD',
                                                      'client_name': 'Ana', 'departure_datetime': '2026-08-11T10:00'})
    res = shared.open_session_block('VIN1')
    assert res is not None
    payload, code = res
    assert code == 409
    assert payload['open_session']['id'] == 9
    assert 'desfășurare' in payload['error']


def test_block_none_when_car_free(monkeypatch):
    monkeypatch.setattr(shared._fp_repo, 'get_open_session', lambda vin, exclude_id=None: None)
    assert shared.open_session_block('VIN1') is None


def test_override_ignored_for_non_privileged(monkeypatch):
    monkeypatch.setattr(shared._fp_repo, 'get_open_session',
                        lambda vin, exclude_id=None: {'id': 5, 'route_type': 'Comodat'})
    assert shared.open_session_block('VIN1', allow_override=True, privileged=False) is not None


def test_override_allowed_for_privileged(monkeypatch):
    monkeypatch.setattr(shared._fp_repo, 'get_open_session',
                        lambda vin, exclude_id=None: {'id': 5, 'route_type': 'TD'})
    assert shared.open_session_block('VIN1', allow_override=True, privileged=True) is None


def test_get_open_session_restricts_to_live_td_form():
    # REGRESSION: batch/allocation rows are also status='FILLED' but are complete
    # paperwork that never returns — they must NOT block a new drive. The query
    # must restrict "open" to live TD-form sessions.
    import inspect
    from foi_parcurs.repositories import foi_parcurs_repository as repo_mod
    src = inspect.getsource(repo_mod.FoiParcursRepository.get_open_session)
    assert "fp.source = 'td_form'" in src
    assert "fp.status = 'FILLED'" in src


# ── route wiring ───────────────────────────────────────────────────────

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


_OUT = {'id': 9, 'route_type': 'TD', 'client_name': 'Ana', 'departure_datetime': '2026-08-11T10:00'}


def _submit_body(**kw):
    body = {'company_id': 1, 'vin': 'VIN1', 'client_id': 2, 'odometer_start': 1000,
            'estimated_km': 50, 'fuel_gauge_start_level': '1/1', 'departure_datetime': '2026-08-12T10:00',
            'advisor_name': 'Adv', 'client_signature': 'data:image/png;base64,x'}
    body.update(kw)
    return body


def test_submit_blocked_when_car_out(client, monkeypatch):
    monkeypatch.setattr(td_mod._vehicle_repo, 'get_lock_by_vin', lambda vin: None)
    monkeypatch.setattr(td_mod._fp_repo, 'get_open_session', lambda vin, exclude_id=None: dict(_OUT))
    resp = client.post('/api/foi-parcurs/test-drive', json=_submit_body())
    assert resp.status_code == 409
    body = resp.get_json()
    assert body['open_session']['id'] == 9
    assert 'open_session' in body


def test_submit_draft_not_blocked(client, monkeypatch):
    # Planning a PLANNED draft is allowed even while the car is out — the block
    # only fires when actually starting. get_open_session must not even be hit.
    called = {'n': 0}
    monkeypatch.setattr(td_mod._vehicle_repo, 'get_lock_by_vin', lambda vin: None)
    monkeypatch.setattr(td_mod._fp_repo, 'get_open_session',
                        lambda vin, exclude_id=None: called.__setitem__('n', called['n'] + 1) or dict(_OUT))
    # A draft needs only company_id/vin/client_id/departure; force the create to a clean stop
    # right after the block would have run by making record fail loudly is overkill — instead
    # assert the block path wasn't taken (no 409 open_session) and get_open_session untouched.
    monkeypatch.setattr(td_mod._fp_repo, 'create_contract', lambda data: {'id': 1, **data})
    resp = client.post('/api/foi-parcurs/test-drive',
                       json={'status': 'PLANNED', 'company_id': 1, 'vin': 'VIN1', 'client_id': 2,
                             'departure_datetime': '2026-08-20T10:00'})
    assert called['n'] == 0
    assert not (resp.get_json() or {}).get('open_session')


def test_activate_blocked_when_car_out(client, monkeypatch):
    monkeypatch.setattr(td_mod._fp_repo, 'get_contract_by_id',
                        lambda id: {'id': id, 'route_type': 'TD', 'status': 'PLANNED', 'vin': 'VIN1',
                                    'company_id': 1})
    monkeypatch.setattr(td_mod._vehicle_repo, 'get_lock_by_vin', lambda vin: None)
    monkeypatch.setattr(td_mod._fp_repo, 'get_open_session', lambda vin, exclude_id=None: dict(_OUT))
    resp = client.put('/api/foi-parcurs/test-drive/1/activate',
                      json={'client_signature': 'data:image/png;base64,x'})
    assert resp.status_code == 409
    assert resp.get_json()['open_session']['id'] == 9
