"""Tests for the CarPark tenant-switcher catalog metadata endpoints:

- `GET /api/carpark/companies` — all companies, for the company selector.
- `GET /api/carpark/brands/<company_id>` — a company's brands, for the
  brand selector.

Uses the real Flask app (`app.py`) so the actual Flask-Login + carpark
permission-decorator wiring is exercised end-to-end for the route-level
tests (mirrors `tests/carpark/test_acting_company.py`, the sibling test
from the same package). Under pytest, the top-level conftest.py mocks
psycopg2 before `app` is imported, so the real `UserRepository.get_by_id`
call made by Flask-Login's user_loader returns `{}` (falsy) instead of a
real user — we patch `app._user_repo.get_by_id` per-test to return a real
user dict so session-based login actually authenticates AND carries the
right `can_access_carpark` flag (see `core/auth/models.py::User`).

GOTCHA (same as test_acting_company.py): `app.py`'s Flask-Login
user_loader caches loaded `User` objects per-process for 60s, keyed by
int(user_id). Reusing the same uid across tests with different
permission dicts would silently read the stale cached user. We dodge
this by giving every test its own unique uid.
"""
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


def _login(client, monkeypatch, uid, **perm_overrides):
    """Log a session in as `uid`, whose loaded User carries carpark
    access unless overridden."""
    user_dict = {
        'id': uid,
        'email': f'test{uid}@example.com',
        'name': 'Test User',
        'company_id': 1,
        'can_access_carpark': True,
        'can_edit_carpark': True,
    }
    user_dict.update(perm_overrides)
    monkeypatch.setattr(app_module._user_repo, 'get_by_id', lambda _uid: user_dict)
    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)


# ═══════════════════════════════════════════════
# GET /api/carpark/companies
# ═══════════════════════════════════════════════

def test_list_companies_returns_companies_list(client, monkeypatch):
    _login(client, monkeypatch, uid=92001)
    fake_companies = [{'id': 1, 'name': 'AUTOWORLD'}, {'id': 16, 'name': 'Premium'}]
    with mock.patch.object(vehicles_module._vehicle_service, 'get_companies',
                            return_value=fake_companies) as get_companies:
        r = client.get('/api/carpark/companies')
    assert r.status_code == 200
    body = r.get_json()
    assert body['companies'] == fake_companies
    get_companies.assert_called_once()


def test_list_companies_requires_auth(client):
    r = client.get('/api/carpark/companies')
    assert r.status_code in (302, 401)


# ═══════════════════════════════════════════════
# GET /api/carpark/brands/<company_id>
# ═══════════════════════════════════════════════

def test_list_brands_returns_brands_list(client, monkeypatch):
    _login(client, monkeypatch, uid=92002)
    with mock.patch.object(vehicles_module._vehicle_service, 'get_brands',
                            return_value=['Audi', 'VW']) as get_brands:
        r = client.get('/api/carpark/brands/16')
    assert r.status_code == 200
    body = r.get_json()
    assert body['brands'] == ['Audi', 'VW']
    get_brands.assert_called_once_with(16)


def test_list_brands_requires_auth(client):
    r = client.get('/api/carpark/brands/16')
    assert r.status_code in (302, 401)
