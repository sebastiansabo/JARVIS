"""Tests for the "Rezolvă gap" flow on the monthly Foaie de Parcurs:

  * absorb_gap()  — close an odometer gap by growing the two bounding sessions'
    km ranges (no new rows); km/route_type recomputed on both.
  * redistribute_gap() — the "client extra" path now persists consilier
    (advisor_name), client signature and the driver-license photo/number/expiry.
  * POST /api/foi-parcurs/route-sheet/absorb-gap route wiring.

The repositories are faked at the module level so no database is touched — the
tests assert the SQL parameters (km math, recomputed distance/route_type,
persisted columns), not a live DB.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest
from flask import Flask

from foi_parcurs import foi_parcurs_bp
import foi_parcurs.services.route_sheet_service as rss
import foi_parcurs.routes.route_sheet as route_sheet_mod


class FakeRepo:
    """Captures execute() calls and answers the handful of query_one() lookups
    absorb_gap / redistribute_gap make, keyed off the SQL text."""

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
    """Patch the module-level repos on route_sheet_service; caller sets rows."""
    repo = FakeRepo()
    monkeypatch.setattr(rss, '_fp_repo', repo)
    monkeypatch.setattr(rss, '_veh_repo', FakeVehRepo())
    return repo


# ── absorb_gap ─────────────────────────────────────────────────────────────

def _two_sessions():
    # before: 1000→1050, gap of 30, after: 1080→1120
    return {
        10: {'id': 10, 'km_start': 1000, 'km_end': 1050, 'company_id': 7},
        11: {'id': 11, 'km_start': 1080, 'km_end': 1120, 'company_id': 7},
    }


def test_absorb_all_to_before(fake_repos):
    fake_repos.rows_by_id = _two_sessions()
    res = rss.absorb_gap('VIN1', 2026, 7, 10, 11, before_km=30, after_km=0)
    assert res == {'before_id': 10, 'after_id': 11, 'before_km': 30,
                   'after_km': 0, 'middles_inserted': 0, 'gap': 30}
    # only the "before" row is updated (after_km == 0, no middles)
    assert len(fake_repos.executed) == 1
    _, params = fake_repos.executed[0]
    new_start, new_end, dist, rtype = params[0], params[1], params[2], params[3]
    assert (new_start, new_end, dist) == (1000, 1080, 80)
    assert rtype == 'Comodat'          # 80 km > td_km_max(50)
    assert params[-1] == 10            # WHERE id
    assert '+30 km' in params[4]       # audit note


def test_absorb_split_between_both(fake_repos):
    fake_repos.rows_by_id = _two_sessions()
    res = rss.absorb_gap('VIN1', 2026, 7, 10, 11, before_km=10, after_km=20)
    assert res['before_km'] == 10 and res['after_km'] == 20 and res['middles_inserted'] == 0
    assert len(fake_repos.executed) == 2
    before, after = fake_repos.executed
    # boundaries meet at 1060: before 1000→1060 (60 km), after 1060→1120 (60 km)
    assert (before[1][0], before[1][1], before[1][2], before[1][3]) == (1000, 1060, 60, 'Comodat')
    assert (after[1][0], after[1][1], after[1][2], after[1][3]) == (1060, 1120, 60, 'Comodat')


def test_absorb_tiles_with_middles(fake_repos):
    fake_repos.rows_by_id = _two_sessions()  # before 1000→1050, after 1080→1120, gap 30
    res = rss.absorb_gap('VIN1', 2026, 7, 10, 11, before_km=5, after_km=10,
                         middles=[{'km': 10, 'client_name': 'X'}, {'km': 5, 'client_name': 'Y'}])
    assert res['middles_inserted'] == 2 and res['gap'] == 30
    # order: before UPDATE, middle1 INSERT, middle2 INSERT, after UPDATE
    assert len(fake_repos.executed) == 4
    bu = fake_repos.executed[0][1]
    au = fake_repos.executed[-1][1]
    assert (bu[0], bu[1], bu[2]) == (1000, 1055, 55)          # before 1000→1055
    assert (au[0], au[1], au[2]) == (1070, 1120, 50)          # after 1070→1120
    m1, m2 = fake_repos.executed[1][1], fake_repos.executed[2][1]
    assert (m1[6], m1[7]) == (1055, 1065) and m1[12] == 'X'   # middle1 slice + name
    assert (m2[6], m2[7]) == (1065, 1070) and m2[12] == 'Y'   # middle2 slice + name


def test_absorb_rejects_sum_mismatch(fake_repos):
    fake_repos.rows_by_id = _two_sessions()
    with pytest.raises(ValueError):
        rss.absorb_gap('VIN1', 2026, 7, 10, 11, before_km=10, after_km=10)  # 20 != gap(30)
    assert fake_repos.executed == []


def test_absorb_rejects_when_no_gap(fake_repos):
    fake_repos.rows_by_id = {
        10: {'id': 10, 'km_start': 1000, 'km_end': 1080, 'company_id': 7},
        11: {'id': 11, 'km_start': 1080, 'km_end': 1120, 'company_id': 7},
    }
    with pytest.raises(ValueError):
        rss.absorb_gap('VIN1', 2026, 7, 10, 11, before_km=0, after_km=0)


def test_absorb_rejects_missing_session(fake_repos):
    fake_repos.rows_by_id = {}
    with pytest.raises(ValueError):
        rss.absorb_gap('VIN1', 2026, 7, 10, 11, before_km=5, after_km=0)


# ── retile_gap: distribute a gap across a window of existing sessions ────────

def _window_three():
    # Andrei 30000-30056 (56) · Ana 30056-30110 (54) · [gap 70] · Elena 30180-30220 (40)
    return {
        1: {'id': 1, 'km_start': 30000, 'km_end': 30056, 'company_id': 7},
        2: {'id': 2, 'km_start': 30056, 'km_end': 30110, 'company_id': 7},
        3: {'id': 3, 'km_start': 30180, 'km_end': 30220, 'company_id': 7},
    }


def test_retile_distributes_across_window(fake_repos):
    fake_repos.rows_by_id = _window_three()
    # +20 Andrei, +30 Ana, +20 Elena (70 total) → new distances 76 / 84 / 60
    res = rss.retile_gap('VIN1', 2026, 7,
                         [{'id': 1, 'distance': 76}, {'id': 2, 'distance': 84}, {'id': 3, 'distance': 60}])
    assert res == {'sessions': 3, 'span': 220}
    ups = [p for _, p in fake_repos.executed]   # (new_start, new_end, dist, rtype, note, id)
    assert (ups[0][0], ups[0][1], ups[0][2], ups[0][5]) == (30000, 30076, 76, 1)  # Andrei
    assert (ups[1][0], ups[1][1], ups[1][2], ups[1][5]) == (30076, 30160, 84, 2)  # Ana
    assert (ups[2][0], ups[2][1], ups[2][2], ups[2][5]) == (30160, 30220, 60, 3)  # Elena
    assert '+30 km' in ups[1][4]   # audit note on the changed distance


def test_retile_all_to_upper_neighbour(fake_repos):
    # window = the two immediate neighbours only; whole 70 km gap onto Ana
    fake_repos.rows_by_id = {k: _window_three()[k] for k in (2, 3)}
    res = rss.retile_gap('VIN1', 2026, 7,
                         [{'id': 2, 'distance': 124}, {'id': 3, 'distance': 40}])
    assert res['span'] == 164 and res['sessions'] == 2
    ups = [p for _, p in fake_repos.executed]
    assert (ups[0][0], ups[0][1], ups[0][2]) == (30056, 30180, 124)  # Ana grows into the gap
    assert (ups[1][0], ups[1][1], ups[1][2]) == (30180, 30220, 40)   # Elena unchanged


def test_retile_rejects_sum_mismatch(fake_repos):
    fake_repos.rows_by_id = {k: _window_three()[k] for k in (2, 3)}
    with pytest.raises(ValueError):
        rss.retile_gap('VIN1', 2026, 7,
                       [{'id': 2, 'distance': 54}, {'id': 3, 'distance': 40}])  # 94 != span 164
    assert fake_repos.executed == []


def test_retile_route_ok(client, monkeypatch):
    captured = {}

    def fake_retile(vin, year, month, allocations, user_name=None):
        captured.update(locals())
        return {'sessions': len(allocations), 'span': 220}

    monkeypatch.setattr(route_sheet_mod, 'retile_gap', fake_retile)
    resp = client.post('/api/foi-parcurs/route-sheet/retile-gap', json={
        'vin': 'VIN1', 'year': 2026, 'month': 7,
        'allocations': [{'id': 1, 'distance': 76}, {'id': 2, 'distance': 84}, {'id': 3, 'distance': 60}],
    })
    assert resp.status_code == 200 and resp.get_json()['success'] is True
    assert len(captured['allocations']) == 3


def test_retile_route_needs_two_sessions(client):
    resp = client.post('/api/foi-parcurs/route-sheet/retile-gap', json={
        'vin': 'VIN1', 'year': 2026, 'month': 7, 'allocations': [{'id': 1, 'distance': 10}]})
    assert resp.status_code == 400


# ── redistribute_gap "client extra" columns ────────────────────────────────

def test_redistribute_persists_extra_client(fake_repos):
    item = {
        'date': '2026-07-15', 'client_name': 'Ion Popescu',
        'km_start': 1050, 'km_end': 1080,
        'advisor_name': 'Ana Consilier',
        'client_signature': 'data:image/png;base64,SIG',
        'driver_license_photo': 'data:image/jpeg;base64,PHOTO',
        'driver_license_number': 'AB123456',
        'driver_license_expiry': '2030-01-01',
    }
    n = rss.redistribute_gap('VIN1', 2026, 7, [item], user_name='Fallback User')
    assert n == 1
    _, params = fake_repos.executed[0]
    # last 4 bound params are the client-extra columns
    client_sig, dl_photo, dl_number, dl_expiry = params[-4], params[-3], params[-2], params[-1]
    assert client_sig == 'data:image/png;base64,SIG'
    assert dl_photo == 'data:image/jpeg;base64,PHOTO'
    assert dl_number == 'AB123456'
    assert dl_expiry == '2030-01-01'
    # advisor comes from the item, not the fallback user
    assert 'Ana Consilier' in params


def test_redistribute_advisor_falls_back_to_user(fake_repos):
    item = {'date': '2026-07-15', 'client_name': 'Ion', 'km_start': 1050, 'km_end': 1075}
    rss.redistribute_gap('VIN1', 2026, 7, [item], user_name='Fallback User')
    _, params = fake_repos.executed[0]
    assert 'Fallback User' in params
    # no license/signature supplied → NULL/empty
    assert params[-4] == ''      # client_signature
    assert params[-3] is None    # driver_license_photo


# ── route wiring ───────────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    return app.test_client()


def test_absorb_route_ok(client, monkeypatch):
    captured = {}

    def fake_absorb(vin, year, month, before_id, after_id, before_km, after_km,
                    middles=None, user_name=None):
        captured.update(locals())
        return {'before_id': before_id, 'after_id': after_id, 'before_km': before_km,
                'after_km': after_km, 'middles_inserted': len(middles or []), 'gap': 30}

    monkeypatch.setattr(route_sheet_mod, 'absorb_gap', fake_absorb)
    resp = client.post('/api/foi-parcurs/route-sheet/absorb-gap', json={
        'vin': 'VIN1', 'year': 2026, 'month': 7,
        'before_id': 10, 'after_id': 11, 'before_km': 5, 'after_km': 10,
        'middles': [{'km': 10, 'client_name': 'X'}, {'km': 5, 'client_name': 'Y'}],
    })
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True
    assert captured['before_id'] == 10 and captured['before_km'] == 5 and captured['after_km'] == 10
    assert len(captured['middles']) == 2


def test_absorb_route_rejects_too_many_middles(client):
    resp = client.post('/api/foi-parcurs/route-sheet/absorb-gap', json={
        'vin': 'VIN1', 'year': 2026, 'month': 7,
        'before_id': 10, 'after_id': 11, 'before_km': 0, 'after_km': 0,
        'middles': [{'km': 1}, {'km': 1}, {'km': 1}, {'km': 1}],
    })
    assert resp.status_code == 400


def test_absorb_route_validates_required(client):
    resp = client.post('/api/foi-parcurs/route-sheet/absorb-gap', json={'vin': 'VIN1'})
    assert resp.status_code == 400


def test_absorb_route_maps_valueerror_to_400(client, monkeypatch):
    def boom(*a, **k):
        raise ValueError('Nu există un gap între aceste sesiuni')
    monkeypatch.setattr(route_sheet_mod, 'absorb_gap', boom)
    resp = client.post('/api/foi-parcurs/route-sheet/absorb-gap', json={
        'vin': 'VIN1', 'year': 2026, 'month': 7,
        'before_id': 10, 'after_id': 11, 'before_km': 0, 'after_km': 0,
    })
    assert resp.status_code == 400
    assert 'gap' in resp.get_json()['error']
