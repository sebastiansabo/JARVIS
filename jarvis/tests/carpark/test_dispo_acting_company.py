"""Tests that Dispo summary/kpis honor the acting (tenant-switcher) company,
not just the caller's own company_id.

Mirrors the mock pattern in test_dispo_routes.py: a minimal Flask app
registers carpark_bp, LOGIN_DISABLED=True makes @login_required a no-op, and
current_user is monkeypatched onto every module namespace that reads it
(vehicles.py — where _acting_company_id/_user_company_id live — and dispo.py,
which does its own `from flask_login import current_user`). No real DB
access: _dispo_repo's summary/kpis are monkeypatched per test so only the
route layer (arg wiring) is exercised.

Slice B / Task 1: dispo_summary and dispo_kpis must resolve company_id via
_acting_company_id() (request-provided company_id else the user's own),
consistent with the vehicles.py list/detail routes from Slice A. The intent
endpoints (reserve/sell/deliver/remove-from-stock) and dispo_import
deliberately stay on _user_company_id() and are NOT covered here — see
test_dispo_routes.py for those.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

from carpark import carpark_bp
import carpark.routes.vehicles as vehicles_mod
import carpark.routes.dispo as dispo_mod

COMPANY_ID = 10
ACTING_COMPANY_ID = 11


class FakeUser:
    def __init__(self, id=1, company_id=COMPANY_ID, name='Test User',
                 can_access_carpark=True, can_edit_carpark=True,
                 can_delete_carpark=True, can_view_carpark_finance=False):
        self.id = id
        self.company_id = company_id
        self.name = name
        self.is_authenticated = True
        self.can_access_carpark = can_access_carpark
        self.can_edit_carpark = can_edit_carpark
        self.can_delete_carpark = can_delete_carpark
        self.can_view_carpark_finance = can_view_carpark_finance


def _set_user(monkeypatch, user):
    monkeypatch.setattr(vehicles_mod, 'current_user', user)
    monkeypatch.setattr(dispo_mod, 'current_user', user)


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(carpark_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def default_user(monkeypatch):
    _set_user(monkeypatch, FakeUser())


def _canned_summary_result():
    return {
        'rows': [], 'stage_counts': {}, 'totals': {}, 'total': 0, 'page': 1, 'per_page': 25,
    }


def _canned_kpis_result():
    return {
        'cars_in_stock': 0, 'reserved': 0, 'sold_this_month': 0,
        'delivered_this_month': 0, 'avg_days_in_stock': 0, 'aged_over_60': 0,
        'gross_margin_mtd': 0,
    }


# ── SUMMARY — acting company ─────────────────────────────────────────────

def test_summary_with_company_id_uses_acting_company(client, monkeypatch):
    """?company_id=11 for a user whose own company is 10 must query as 11,
    not 10 — the acting/tenant-switcher company wins."""
    calls = {}

    def _summary(company_id, *a, **k):
        calls['company_id'] = company_id
        return _canned_summary_result()
    monkeypatch.setattr(dispo_mod._dispo_repo, 'summary', _summary)

    resp = client.get(f'/api/carpark/dispo/summary?company_id={ACTING_COMPANY_ID}')
    assert resp.status_code == 200
    assert calls['company_id'] == ACTING_COMPANY_ID
    assert calls['company_id'] != COMPANY_ID


def test_summary_without_company_id_falls_back_to_own_company(client, monkeypatch):
    calls = {}

    def _summary(company_id, *a, **k):
        calls['company_id'] = company_id
        return _canned_summary_result()
    monkeypatch.setattr(dispo_mod._dispo_repo, 'summary', _summary)

    resp = client.get('/api/carpark/dispo/summary')
    assert resp.status_code == 200
    assert calls['company_id'] == COMPANY_ID


# ── KPIS — acting company ────────────────────────────────────────────────

def test_kpis_with_company_id_uses_acting_company(client, monkeypatch):
    calls = {}

    def _kpis(company_id, *a, **k):
        calls['company_id'] = company_id
        return _canned_kpis_result()
    monkeypatch.setattr(dispo_mod._dispo_repo, 'kpis', _kpis)

    resp = client.get(f'/api/carpark/dispo/kpis?company_id={ACTING_COMPANY_ID}')
    assert resp.status_code == 200
    assert calls['company_id'] == ACTING_COMPANY_ID
    assert calls['company_id'] != COMPANY_ID


def test_kpis_without_company_id_falls_back_to_own_company(client, monkeypatch):
    calls = {}

    def _kpis(company_id, *a, **k):
        calls['company_id'] = company_id
        return _canned_kpis_result()
    monkeypatch.setattr(dispo_mod._dispo_repo, 'kpis', _kpis)

    resp = client.get('/api/carpark/dispo/kpis')
    assert resp.status_code == 200
    assert calls['company_id'] == COMPANY_ID
