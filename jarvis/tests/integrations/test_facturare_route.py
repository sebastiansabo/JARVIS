"""POST /api/integrations/business-control/facturare/invoices — auth, validation, envelope.

Mirrors tests/dept_pulse/test_dept_pulse_routes.py: a fresh Flask app with the
integrations blueprint, LOGIN_DISABLED, and monkeypatched current_user /
_has_business_control_access / _repo.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
import database  # noqa: F401  prime the import graph before core.integrations (avoids the core.* cold-import cycle)

from datetime import date
from decimal import Decimal

import pytest
from flask import Flask

import core.integrations.routes_facturare as routes_facturare
from core.integrations import integrations_bp

URL = "/api/integrations/business-control/facturare/invoices"


class FakeUser:
    def __init__(self, authed=True, active=True, uid=42):
        self.id = uid
        self.is_authenticated = authed
        self.is_active = active


def _client(monkeypatch, user, has_perm):
    app = Flask(__name__)
    app.register_blueprint(integrations_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    monkeypatch.setattr(routes_facturare, 'current_user', user)
    monkeypatch.setattr(routes_facturare, '_has_business_control_access', lambda u: has_perm)
    return app.test_client()


@pytest.fixture
def client_unauth(monkeypatch):
    return _client(monkeypatch, FakeUser(authed=False), False)


@pytest.fixture
def client_noperm(monkeypatch):
    return _client(monkeypatch, FakeUser(), False)


@pytest.fixture
def client_ok(monkeypatch):
    return _client(monkeypatch, FakeUser(), True)


def test_requires_auth(client_unauth):
    assert client_unauth.post(URL, json={"orders": ["x"]}).status_code == 401


def test_forbidden_without_permission(client_noperm):
    assert client_noperm.post(URL, json={"orders": ["x"]}).status_code == 403


def test_bad_body_returns_400(client_ok):
    assert client_ok.post(URL, json={}).status_code == 400                 # missing orders
    assert client_ok.post(URL, json={"orders": "x"}).status_code == 400    # not a list
    assert client_ok.post(URL, json={"orders": [123]}).status_code == 400  # non-string entry


def test_over_cap_returns_400(client_ok):
    assert client_ok.post(URL, json={"orders": [str(i) for i in range(1001)]}).status_code == 400


def test_happy_path_envelope(client_ok, monkeypatch):
    monkeypatch.setattr(routes_facturare._repo, "by_order_numbers", lambda orders: [
        {"nr_comanda": "150019", "vin": "WAU", "model": "Audi Q3 35 TFSI", "line_id": 1,
         "invoice_number": 9202036, "invoice_type": "INVOICE", "issued_date": date(2026, 9, 9),
         "total_amount_eur": Decimal("31828.00"), "total_amount_ron": Decimal("167170.20"),
         "currency": "EUR", "archived": False}])
    body = client_ok.post(URL, json={"orders": ["150019", "999999"]}).get_json()
    assert body["success"] is True
    assert body["results"][0]["invoice_number"] == "9202036"
    assert body["results"][0]["documents"][0]["type"] == "INVOICE"
    assert body["not_found"] == ["999999"]
