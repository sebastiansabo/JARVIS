"""Foaie de Parcurs 'Finalizat' lock:
  - finalize/unlock service logic (guards on not-generated / wrong state)
  - the full-freeze guard helpers (route_sheet_lock_block / session_lock_block)
  - finalize endpoint (login-only) + a 423 on a locked mutation endpoint.
Unlock's v2 permission gate is enforced by @v2_permission_required (DB-backed) and
is covered by the migration grants, not re-tested here.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

import foi_parcurs.services.route_sheet_service as rss
import foi_parcurs.routes._shared as shared
import foi_parcurs.routes.route_sheet as rs_mod
from foi_parcurs import foi_parcurs_bp


# ── service: finalize / unlock ───────────────────────────────────────────────
class FakeStore:
    def __init__(self):
        self.sheet_row = None    # SELECT pdf_bytes, status
        self.status_row = None   # SELECT status
        self.state_row = None    # get_lock_state SELECT
        self.execs = []

    def query_one(self, sql, params):
        if 'pdf_bytes' in sql:
            return self.sheet_row
        if 'finalized_at, finalized_by_name' in sql:
            return self.state_row
        if 'SELECT status FROM' in sql:
            return self.status_row
        return None

    def query_all(self, sql, params):
        return []

    def execute(self, sql, params, returning=False):
        self.execs.append((sql, params))


@pytest.fixture
def store(monkeypatch):
    s = FakeStore()
    monkeypatch.setattr(rss, '_store', s)
    return s


def test_finalize_sets_status_and_logs(store):
    store.sheet_row = {'pdf_bytes': b'%PDF-', 'status': 'draft'}
    store.state_row = {'status': 'finalizat', 'finalized_at': 't', 'finalized_by_name': 'U',
                       'unlocked_at': None, 'unlocked_by_name': None}
    out = rss.finalize_sheet('VF1', 2026, 9, user_id=7, user_name='U')
    assert out['status'] == 'finalizat'
    assert any("status='finalizat'" in sql for sql, _ in store.execs)          # the UPDATE
    assert any('fp_route_sheet_lock_events' in sql for sql, _ in store.execs)  # audit row


def test_finalize_requires_generated_pdf(store):
    store.sheet_row = {'pdf_bytes': None, 'status': 'draft'}
    with pytest.raises(ValueError):
        rss.finalize_sheet('VF1', 2026, 9)


def test_finalize_rejects_already_finalizat(store):
    store.sheet_row = {'pdf_bytes': b'%PDF-', 'status': 'finalizat'}
    with pytest.raises(ValueError):
        rss.finalize_sheet('VF1', 2026, 9)


def test_unlock_sets_draft_and_logs(store):
    store.status_row = {'status': 'finalizat'}
    store.state_row = {'status': 'draft', 'finalized_at': 't', 'finalized_by_name': 'U',
                       'unlocked_at': 'u', 'unlocked_by_name': 'C'}
    out = rss.unlock_sheet('VF1', 2026, 9, user_id=3, user_name='C', reason='corectie')
    assert out['status'] == 'draft'
    assert any("status='draft'" in sql for sql, _ in store.execs)
    # reason is passed through to the audit insert
    assert any('fp_route_sheet_lock_events' in sql and 'corectie' in (p or ())
               for sql, p in store.execs)


def test_unlock_rejects_when_not_finalizat(store):
    store.status_row = {'status': 'draft'}
    with pytest.raises(ValueError):
        rss.unlock_sheet('VF1', 2026, 9)


def test_status_defaults_to_draft_when_absent(store):
    store.status_row = None
    assert rss.route_sheet_status('VF1', 2026, 9) == 'draft'
    assert rss.is_finalized('VF1', 2026, 9) is False


# ── guard helpers ────────────────────────────────────────────────────────────
def test_route_sheet_lock_block_423_when_finalized(monkeypatch):
    monkeypatch.setattr(rss, 'is_finalized', lambda v, y, m: True)
    res = shared.route_sheet_lock_block('VF1', 2026, 9)
    assert res is not None and res[1] == 423 and res[0]['locked'] is True


def test_route_sheet_lock_block_none_when_draft(monkeypatch):
    monkeypatch.setattr(rss, 'is_finalized', lambda v, y, m: False)
    assert shared.route_sheet_lock_block('VF1', 2026, 9) is None


def test_session_lock_block_derives_month_from_departure(monkeypatch):
    seen = {}
    monkeypatch.setattr(rss, 'is_finalized',
                        lambda v, y, m: (seen.update(vin=v, year=y, month=m), True)[1])
    res = shared.session_lock_block({'id': 5, 'vin': 'VF1', 'departure_datetime': '2026-09-12T10:00:00'})
    assert res[1] == 423
    assert seen == {'vin': 'VF1', 'year': 2026, 'month': 9}


def test_session_lock_block_none_when_no_date(monkeypatch):
    monkeypatch.setattr(rss, 'is_finalized', lambda v, y, m: True)
    # No drive date → no (year, month) → cannot be in a finalized month → allowed.
    assert shared.session_lock_block({'id': 5, 'vin': 'VF1'}) is None


# ── endpoints ────────────────────────────────────────────────────────────────
@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    return app.test_client()


def test_finalize_endpoint_ok(client, monkeypatch):
    monkeypatch.setattr(rs_mod, 'finalize_sheet',
                        lambda v, y, m, user_id=None, user_name=None: {'status': 'finalizat', 'finalized_by_name': 'U'})
    r = client.post('/api/foi-parcurs/route-sheet/finalize', json={'vin': 'V', 'year': 2026, 'month': 9})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['status'] == 'finalizat'


def test_finalize_endpoint_400_when_not_generated(client, monkeypatch):
    def boom(*a, **k):
        raise ValueError('Foaia de parcurs trebuie generată înainte de finalizare.')
    monkeypatch.setattr(rs_mod, 'finalize_sheet', boom)
    r = client.post('/api/foi-parcurs/route-sheet/finalize', json={'vin': 'V', 'year': 2026, 'month': 9})
    assert r.status_code == 400


def test_scop_endpoint_returns_423_when_finalized(client, monkeypatch):
    monkeypatch.setattr(rss, 'is_finalized', lambda v, y, m: True)
    r = client.post('/api/foi-parcurs/route-sheet/scop',
                    json={'vin': 'V', 'year': 2026, 'month': 9, 'session_id': 1, 'text': 'x'})
    assert r.status_code == 423
    assert r.get_json()['locked'] is True


def test_redistribute_gap_returns_423_when_finalized(client, monkeypatch):
    monkeypatch.setattr(rss, 'is_finalized', lambda v, y, m: True)
    r = client.post('/api/foi-parcurs/route-sheet/redistribute-gap',
                    json={'vin': 'V', 'year': 2026, 'month': 9, 'contracts': [{'id': 1}]})
    assert r.status_code == 423
