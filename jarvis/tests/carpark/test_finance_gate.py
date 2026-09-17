"""Tests for `carpark_finance_required` — the decorator that blocks
purely-financial CarPark reads (costs, revenues, profitability, floor-price,
pricing-history, analytics/costs) from users lacking
`can_view_carpark_finance`, even when they otherwise have full
`can_access_carpark` + `can_edit_carpark`.

Uses the real Flask app (`app.py`) so the actual Flask-Login + carpark
permission-decorator wiring is exercised end-to-end (mirrors
`tests/carpark/test_acting_company.py` / `test_photo_upload.py`, the sibling
tests from the same package). Under pytest, the top-level conftest.py mocks
psycopg2 before `app` is imported, so the real `UserRepository.get_by_id`
call made by Flask-Login's user_loader returns `{}` (falsy) instead of a
real user — we patch `app._user_repo.get_by_id` per-test to return a real
user dict so session-based login actually authenticates AND carries the
right `can_access_carpark` / `can_edit_carpark` / `can_view_carpark_finance`
flags (see `core/auth/models.py::User`).

`/vehicles/<id>/profitability` (carpark/routes/costs.py) is used as the
representative route: its view body calls `_verify_vehicle_ownership` (a
real DB call unless mocked) then `_service.get_profitability` — NOTE the
service attribute in costs.py is `_service`, not `_vehicle_service` (that
belongs to vehicles.py); the brief's example mock target was corrected here
after reading the real module.

GOTCHA (same as test_acting_company.py / test_photo_upload.py): `app.py`'s
Flask-Login user_loader caches loaded `User` objects per-process for 60s,
keyed by int(user_id). Reusing a uid already claimed by another carpark test
module (test_company_scope.py claims 93001/93002) would silently read the
stale cached user. We use fresh uids 95001/95002, confirmed unused across
`tests/carpark/` at the time this file was written.
"""
import os
from unittest import mock

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest

import app as app_module
from app import app as flask_app
from carpark.routes import costs as costs_module


@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    return flask_app.test_client()


def _login(client, monkeypatch, uid, finance=False):
    user = {'id': uid, 'email': f't{uid}@x.com', 'name': 'T', 'company_id': 1,
            'can_access_carpark': True, 'can_edit_carpark': True,
            'can_view_carpark_finance': finance}
    monkeypatch.setattr(app_module._user_repo, 'get_by_id', lambda _u: user)
    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)


def test_profitability_forbidden_without_finance(client, monkeypatch):
    _login(client, monkeypatch, uid=95001, finance=False)
    r = client.get('/api/carpark/vehicles/1/profitability')
    assert r.status_code == 403


def test_profitability_allowed_with_finance(client, monkeypatch):
    _login(client, monkeypatch, uid=95002, finance=True)
    with mock.patch.object(costs_module, '_verify_vehicle_ownership',
                            return_value=({'id': 1}, None)), \
         mock.patch.object(costs_module._service, 'get_profitability',
                            return_value={'profit': 0}):
        r = client.get('/api/carpark/vehicles/1/profitability')
    assert r.status_code == 200
