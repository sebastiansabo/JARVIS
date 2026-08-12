"""Tests for the permissive tenant-switcher backend in
`carpark/routes/vehicles.py`:

- `_acting_company_id()` — the company the caller is acting as. Honors a
  request-provided `company_id` with NO authorization (by design — see the
  Slice A design doc), falling back to `current_user.company_id`.
- `_verify_vehicle_ownership()` — now exists-only: 404 only when the
  vehicle does not exist, never on a company mismatch.

Uses the real Flask app (`app.py`) so the actual Flask-Login + carpark
permission-decorator wiring is exercised end-to-end for the route-level
tests (mirrors `tests/carpark/test_photo_upload.py`, the sibling test from
the same package). Under pytest, the top-level conftest.py mocks psycopg2
before `app` is imported, so the real `UserRepository.get_by_id` call made
by Flask-Login's user_loader returns `{}` (falsy) instead of a real user —
we patch `app._user_repo.get_by_id` per-test to return a real user dict so
session-based login actually authenticates AND carries the right
`company_id` / `can_access_carpark` / `can_edit_carpark` flags (see
`core/auth/models.py::User`).

GOTCHA (same as test_photo_upload.py): `app.py`'s Flask-Login user_loader
caches loaded `User` objects per-process for 60s, keyed by int(user_id).
Reusing the same uid across tests with different company_id/permission
dicts would silently read the stale cached user. We dodge this by giving
every test its own unique uid.
"""
import os
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest

import app as app_module
from app import app as flask_app
from carpark.routes import vehicles as vehicles_module
from carpark.routes import analytics as analytics_module


@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    return flask_app.test_client()


def _login(client, monkeypatch, uid, company_id=1, **perm_overrides):
    """Log a session in as `uid`, whose loaded User carries `company_id`
    and full carpark access unless overridden."""
    user_dict = {
        'id': uid,
        'email': f'test{uid}@example.com',
        'name': 'Test User',
        'company_id': company_id,
        'can_access_carpark': True,
        'can_edit_carpark': True,
    }
    user_dict.update(perm_overrides)
    monkeypatch.setattr(app_module._user_repo, 'get_by_id', lambda _uid: user_dict)
    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)


# ═══════════════════════════════════════════════
# list_vehicles: request-provided company_id vs. fallback
# ═══════════════════════════════════════════════

def test_list_vehicles_uses_requested_company_id(client, monkeypatch):
    """?company_id=11 from a user in company 1 must be honored (permissive
    tenant switch — no authorization check)."""
    _login(client, monkeypatch, uid=91001, company_id=1)
    with mock.patch.object(vehicles_module._vehicle_service, 'get_catalog',
                            return_value={'vehicles': [], 'total': 0}) as get_catalog:
        r = client.get('/api/carpark/vehicles?company_id=11')
    assert r.status_code == 200
    filters = get_catalog.call_args.args[0]
    assert filters['company_id'] == '11'


def test_list_vehicles_falls_back_to_user_company_id(client, monkeypatch):
    """No company_id in the request -> defaults to current_user.company_id."""
    _login(client, monkeypatch, uid=91002, company_id=7)
    with mock.patch.object(vehicles_module._vehicle_service, 'get_catalog',
                            return_value={'vehicles': [], 'total': 0}) as get_catalog:
        r = client.get('/api/carpark/vehicles')
    assert r.status_code == 200
    filters = get_catalog.call_args.args[0]
    assert filters['company_id'] == '7'


# ═══════════════════════════════════════════════
# create_vehicle: request body company_id wins over the user's own
# ═══════════════════════════════════════════════

def test_create_vehicle_uses_requested_company_id(client, monkeypatch):
    _login(client, monkeypatch, uid=91003, company_id=1)
    with mock.patch.object(vehicles_module._vehicle_service, 'create_vehicle',
                            return_value={'id': 55, 'vin': 'X' * 17, 'company_id': 11}) as create:
        body = {'vin': 'X' * 17, 'brand': 'BMW', 'model': 'X5', 'company_id': 11}
        r = client.post('/api/carpark/vehicles', json=body)
    assert r.status_code == 201
    sent_data = create.call_args.args[0]
    assert sent_data['company_id'] == 11


# ═══════════════════════════════════════════════
# _verify_vehicle_ownership: now exists-only (no company check)
# ═══════════════════════════════════════════════

def test_verify_ownership_foreign_company_is_allowed(monkeypatch):
    """An existing vehicle belonging to a DIFFERENT company than the caller
    must be returned with no error — the isolation check is removed."""
    monkeypatch.setattr(vehicles_module, 'current_user', SimpleNamespace(company_id=1))
    with mock.patch.object(vehicles_module._vehicle_service, 'get_vehicle',
                            return_value={'id': 42, 'company_id': 999}):
        with flask_app.test_request_context():
            vehicle, err = vehicles_module._verify_vehicle_ownership(42)
    assert err is None
    assert vehicle == {'id': 42, 'company_id': 999}


def test_verify_ownership_missing_vehicle_404(monkeypatch):
    """A vehicle id that doesn't exist at all still 404s."""
    monkeypatch.setattr(vehicles_module, 'current_user', SimpleNamespace(company_id=1))
    with mock.patch.object(vehicles_module._vehicle_service, 'get_vehicle', return_value=None):
        with flask_app.test_request_context():
            vehicle, err = vehicles_module._verify_vehicle_ownership(999)
    assert vehicle is None
    assert err is not None
    assert err[1] == 404


# ═══════════════════════════════════════════════
# analytics_summary: request-provided company_id scopes analytics too
# (analytics/pricing/publishing all delegate to the same
# _acting_company_id() from vehicles.py)
# ═══════════════════════════════════════════════

def test_analytics_summary_uses_requested_company_id(client, monkeypatch):
    """?company_id=11 from a user in company 1 must be honored by the
    analytics routes too (permissive tenant switch — no authorization
    check), not just by vehicles.py."""
    _login(client, monkeypatch, uid=91004, company_id=1)
    with mock.patch.object(analytics_module._analytics, 'get_summary',
                            return_value={'total': 0}) as get_summary:
        r = client.get('/api/carpark/analytics/summary?company_id=11')
    assert r.status_code == 200
    cid = get_summary.call_args.args[0]
    assert cid == 11
