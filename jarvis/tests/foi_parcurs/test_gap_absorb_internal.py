"""Redistributing a gap that came from hidden internal drives must SOFT-SUPERSEDE
those internal drives (Option A): they stay in the DB (audit + Restaurează) but
drop out of the foaie so their KM isn't double-counted against the client km that
now covers the same odometer stretch.

  * retile_gap / redistribute_gap stamp absorbed_at on the internal drives whose
    km range falls inside the just-closed gap (client rows are never touched).
  * aggregate_month excludes absorbed rows from BOTH the listing and the odometer
    span, regardless of include_internal.
  * restore_absorbed clears the flag so a mistaken absorb can be undone.

Repos are faked at module level (no DB); tests assert the SQL text + params.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest

import foi_parcurs.services.route_sheet_service as rss


class FakeRepo:
    """Captures execute() calls and answers the query_one() lookups the gap
    flows make, keyed off the SQL text."""

    def __init__(self, rows=None, td_km_max=50):
        self.rows_by_id = rows or {}
        self.td_km_max = td_km_max
        self.executed = []

    def query_one(self, sql, params=None):
        if 'fp_km_configs' in sql:
            return {'td_km_max': self.td_km_max}
        if 'FROM foi_de_parcurs WHERE id=' in sql:
            return self.rows_by_id.get(params[0])
        if 'FROM foi_de_parcurs WHERE vin=' in sql:
            return {'company_id': 7, 'registration_number': 'B123ABC'}
        return None

    def query_all(self, sql, params=None):
        return []

    def execute(self, sql, params=None, returning=False):
        self.executed.append((sql, params))
        return 1


class FakeVehRepo:
    def get_by_vin(self, vin):
        return {'company_id': 7, 'registration_number': 'B123ABC',
                'fuel_tank_capacity_liters': 50}


@pytest.fixture
def fake_repos(monkeypatch):
    repo = FakeRepo()
    monkeypatch.setattr(rss, '_fp_repo', repo)
    monkeypatch.setattr(rss, '_veh_repo', FakeVehRepo())
    return repo


def _absorb_updates(repo):
    """The SET absorbed_at UPDATE(s) the flow emitted, as (sql, params)."""
    return [(sql, p) for sql, p in repo.executed if 'absorbed_at' in sql and 'NULL' not in sql.split('WHERE')[0]]


# ── retile_gap (Absorb mode) ────────────────────────────────────────────────

def _window_three():
    # Andrei 30000-30056 · Ana 30056-30110 · [gap 70] · Elena 30180-30220
    return {
        1: {'id': 1, 'km_start': 30000, 'km_end': 30056, 'company_id': 7},
        2: {'id': 2, 'km_start': 30056, 'km_end': 30110, 'company_id': 7},
        3: {'id': 3, 'km_start': 30180, 'km_end': 30220, 'company_id': 7},
    }


def test_retile_absorbs_internal_drives_in_window(fake_repos):
    fake_repos.rows_by_id = _window_three()
    rss.retile_gap('VIN1', 2026, 7,
                   [{'id': 1, 'distance': 76}, {'id': 2, 'distance': 84}, {'id': 3, 'distance': 60}])
    marks = _absorb_updates(fake_repos)
    assert len(marks) == 1
    sql, params = marks[0]
    # window span [30000, 30220] is the absorb range
    assert 'VIN1' in params and 30000 in params and 30220 in params
    # only internal, not-already-absorbed rows are touched
    assert 'is_internal' in sql and 'absorbed_at IS NULL' in sql


# ── redistribute_gap (Client-extra / Boundary / Event modes) ────────────────

def test_redistribute_absorbs_internal_drives_in_gap(fake_repos):
    item = {'date': '2026-07-15', 'client_name': 'Ion', 'km_start': 1050, 'km_end': 1080}
    rss.redistribute_gap('VIN1', 2026, 7, [item], user_name='Auditor')
    marks = _absorb_updates(fake_repos)
    assert len(marks) == 1
    sql, params = marks[0]
    assert 'VIN1' in params and 1050 in params and 1080 in params
    assert 'Auditor' in params  # absorbed_by = acting user


def test_redistribute_absorb_range_spans_all_items(fake_repos):
    items = [
        {'date': '2026-07-15', 'client_name': 'A', 'km_start': 1050, 'km_end': 1070},
        {'date': '2026-07-16', 'client_name': 'B', 'km_start': 1070, 'km_end': 1120},
    ]
    rss.redistribute_gap('VIN1', 2026, 7, items, user_name='U')
    sql, params = _absorb_updates(fake_repos)[0]
    assert 1050 in params and 1120 in params  # min km_start .. max km_end


# ── aggregate_month excludes absorbed rows ──────────────────────────────────

def _contract(cid, km_start, km_end, *, is_internal=False, day=5, absorbed=False):
    return {
        'id': cid, 'company_id': None, 'company_name': 'Autoworld',
        'departure_datetime': f'2026-09-{day:02d}T10:00:00',
        'return_datetime': f'2026-09-{day:02d}T12:00:00',
        'created_at': f'2026-09-{day:02d}T09:00:00',
        'km_start': km_start, 'km_end': km_end, 'distance_km': km_end - km_start,
        'is_internal': is_internal, 'source': 'batch', 'itinerary': '',
        'advisor_name': 'Advisor', 'client_name': 'Client', 'route_type': 'TD',
        'registration_number': 'CJ01ABC',
        'absorbed_at': '2026-09-10T10:00:00' if absorbed else None,
    }


class _FakeFpRepo:
    def __init__(self, rows):
        self._rows = rows

    def get_contracts(self, **_):
        return list(self._rows), len(self._rows)

    def query_all(self, *_a, **_k):
        return []


def _setup_agg(monkeypatch, rows):
    monkeypatch.setattr(rss, '_fp_repo', _FakeFpRepo(rows))
    monkeypatch.setattr(rss, '_veh_repo',
                        type('V', (), {'get_by_vin': staticmethod(lambda vin: {'mark': 'MG', 'model': 'HS'})})())


def test_aggregate_excludes_absorbed_from_listing_and_span(monkeypatch):
    # absorbed internal drive sits at the TOP (would otherwise define km_end).
    rows = [
        _contract(1, 1000, 1030, day=3),
        _contract(2, 1030, 1090, day=8),
        _contract(3, 1090, 1200, is_internal=True, day=5, absorbed=True),
    ]
    _setup_agg(monkeypatch, rows)
    data = rss.aggregate_month('VF1X', 2026, 9)  # include_internal defaults True
    assert data['totals']['sessions'] == 2          # absorbed row gone from listing
    assert data['totals']['km_start'] == 1000
    assert data['totals']['km_end'] == 1090         # span no longer reaches the absorbed drive
    assert data['totals']['km'] == 90               # no double-count


# ── restore (undo a mistaken absorb) ────────────────────────────────────────

def test_restore_absorbed_clears_flag(fake_repos, monkeypatch):
    monkeypatch.setattr(rss, 'is_finalized', lambda *a, **k: False)
    fake_repos.rows_by_id = {
        5: {'id': 5, 'vin': 'VIN1', 'km_start': 1090, 'km_end': 1200,
            'departure_datetime': '2026-07-05T10:00:00', 'created_at': '2026-07-05T09:00:00',
            'absorbed_at': '2026-07-10T10:00:00'},
    }
    res = rss.restore_absorbed(5, user_name='U')
    assert res['restored'] is True
    clears = [(sql, p) for sql, p in fake_repos.executed
              if 'absorbed_at' in sql and 'NULL' in sql.split('WHERE')[0]]
    assert len(clears) == 1
    sql, params = clears[0]
    assert 5 in params


def test_restore_noop_when_not_absorbed(fake_repos):
    fake_repos.rows_by_id = {
        6: {'id': 6, 'vin': 'VIN1', 'km_start': 1090, 'km_end': 1200,
            'departure_datetime': '2026-07-05T10:00:00', 'created_at': '2026-07-05T09:00:00',
            'absorbed_at': None},
    }
    res = rss.restore_absorbed(6, user_name='U')
    assert res['restored'] is False
    assert fake_repos.executed == []  # nothing cleared


def test_restore_blocked_when_sheet_finalized(fake_repos, monkeypatch):
    monkeypatch.setattr(rss, 'is_finalized', lambda *a, **k: True)
    fake_repos.rows_by_id = {
        7: {'id': 7, 'vin': 'VIN1', 'km_start': 1090, 'km_end': 1200,
            'departure_datetime': '2026-07-05T10:00:00', 'created_at': '2026-07-05T09:00:00',
            'absorbed_at': '2026-07-10T10:00:00'},
    }
    with pytest.raises(PermissionError):
        rss.restore_absorbed(7, user_name='U')
    assert fake_repos.executed == []  # nothing cleared while locked


# ── restore route wiring ────────────────────────────────────────────────────

@pytest.fixture
def client():
    from flask import Flask
    from foi_parcurs import foi_parcurs_bp
    app = Flask(__name__)
    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    return app.test_client()


def test_restore_route_ok(client, monkeypatch):
    import foi_parcurs.routes.route_sheet as route_sheet_mod
    captured = {}

    def fake_restore(contract_id, user_name=None):
        captured['id'] = contract_id
        return {'restored': True, 'vin': 'VIN1', 'year': 2026, 'month': 7}

    monkeypatch.setattr(route_sheet_mod, 'restore_absorbed', fake_restore)
    resp = client.post('/api/foi-parcurs/route-sheet/restore-absorbed', json={'id': 5})
    assert resp.status_code == 200 and resp.get_json()['success'] is True
    assert captured['id'] == 5


def test_restore_route_requires_id(client):
    resp = client.post('/api/foi-parcurs/route-sheet/restore-absorbed', json={})
    assert resp.status_code == 400


def test_restore_route_locked_returns_423(client, monkeypatch):
    import foi_parcurs.routes.route_sheet as route_sheet_mod

    def boom(contract_id, user_name=None):
        raise PermissionError('Foaia de parcurs este finalizată (blocată)')

    monkeypatch.setattr(route_sheet_mod, 'restore_absorbed', boom)
    resp = client.post('/api/foi-parcurs/route-sheet/restore-absorbed', json={'id': 5})
    assert resp.status_code == 423
