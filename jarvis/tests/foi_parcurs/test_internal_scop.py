"""Internal (company) drives on the monthly Foaie de Parcurs.

Internal drives are now LISTED (no longer hidden as a gap). Their Locul/Scopul =
the drive's Comentariu (stored in `itinerary`) verbatim, else a generic purpose.
Event gap-fills read as "Eveniment: {name}". Trips are keyed by the real session
id so per-session manual overrides stay stable.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest

import foi_parcurs.services.route_sheet_service as rss


class AggFakeRepo:
    def __init__(self, rows):
        self.rows = rows

    def get_contracts(self, **kwargs):
        return list(self.rows), len(self.rows)

    def query_all(self, sql, params=None):
        return []

    def query_one(self, sql, params=None):
        return None


class AggFakeVeh:
    def get_by_vin(self, vin):
        return {'mark': 'VW', 'model': 'Golf', 'fuel_type': 'Diesel',
                'company_id': None, 'registration_number': 'B1'}


def _rows():
    base = {'company_id': None, 'registration_number': 'B1', 'route_type': 'TD', 'is_internal': False}
    return [
        {**base, 'id': 201, 'departure_datetime': '2026-08-05T10:00:00', 'created_at': '2026-08-05T10:00:00',
         'km_start': 100, 'km_end': 130, 'distance_km': 30, 'source': 'td_form',
         'itinerary': 'centru', 'client_name': 'Ion', 'advisor_name': 'Ana'},
        {**base, 'id': 202, 'is_internal': True, 'departure_datetime': '2026-08-06T10:00:00', 'created_at': '2026-08-06T10:00:00',
         'km_start': 130, 'km_end': 180, 'distance_km': 50, 'source': 'internal',
         # Stray client_name on an internal log — the driver shown must still be
         # the advisor (driving user), matching the UI's Client column.
         'itinerary': 'Service Brașov', 'client_name': 'Seba', 'advisor_name': 'Vasile Mecanic'},
        {**base, 'id': 203, 'is_internal': True, 'departure_datetime': '2026-08-07T10:00:00', 'created_at': '2026-08-07T10:00:00',
         'km_start': 180, 'km_end': 200, 'distance_km': 20, 'source': 'internal',
         'itinerary': '', 'client_name': '', 'advisor_name': 'Gheo'},
        {**base, 'id': 204, 'departure_datetime': '2026-08-08T10:00:00', 'created_at': '2026-08-08T10:00:00',
         'km_start': 200, 'km_end': 260, 'distance_km': 60, 'source': 'gap-event',
         'itinerary': 'Salon Auto', 'client_name': '', 'advisor_name': 'Seba'},
    ]


@pytest.fixture
def agg(monkeypatch):
    monkeypatch.setattr(rss, '_fp_repo', AggFakeRepo(_rows()))
    monkeypatch.setattr(rss, '_veh_repo', AggFakeVeh())


def _by_km(data, ks):
    return next(t for t in data['trips'] if t['km_start'] == ks)


def test_all_sessions_listed_including_internal(agg):
    data = rss.aggregate_month('V', 2026, 8)
    assert data['totals']['sessions'] == 4


def test_internal_drive_uses_comment_verbatim(agg):
    t = _by_km(rss.aggregate_month('V', 2026, 8), 130)
    assert t['traseu'] == 'Service Brașov'
    assert t['is_td'] is False
    assert t['driver'] == 'Vasile Mecanic'


def test_internal_driver_is_advisor_not_stray_client_name(agg):
    # id 202 is internal with a stray client_name 'Seba'; the Șofer shown on the
    # route sheet must be the driving user (advisor_name), not 'Seba' — matching
    # the UI's Client column (clientCell).
    assert _by_km(rss.aggregate_month('V', 2026, 8), 130)['driver'] == 'Vasile Mecanic'


def test_internal_drive_without_comment_falls_back(agg):
    assert _by_km(rss.aggregate_month('V', 2026, 8), 180)['traseu'] == 'Deplasare în interes de serviciu'


def test_event_row_shows_event_name(agg):
    assert _by_km(rss.aggregate_month('V', 2026, 8), 200)['traseu'] == 'Eveniment: Salon Auto'


def test_client_td_unchanged(agg):
    assert _by_km(rss.aggregate_month('V', 2026, 8), 100)['traseu'] == 'Test Drive VW Golf'


def test_trip_keyed_by_real_session_id(agg):
    assert _by_km(rss.aggregate_month('V', 2026, 8), 130)['id'] == 202


# ── scop resolution: manual override > AI prose > base traseu ──

def test_scop_text_override_wins():
    trip = {'id': 202, 'traseu': 'Service Brașov'}
    assert rss._scop_text(trip, {}, {'202': 'Reparație DEKRA'}) == 'Reparație DEKRA'


def test_scop_text_prose_then_base():
    trip = {'id': 202, 'traseu': 'base text'}
    assert rss._scop_text(trip, {202: 'ai text'}, {}) == 'ai text'
    assert rss._scop_text(trip, {}, {}) == 'base text'


# ── POST /route-sheet/scop wiring ──

@pytest.fixture
def client(monkeypatch):
    from flask import Flask
    from foi_parcurs import foi_parcurs_bp
    app = Flask(__name__)
    app.register_blueprint(foi_parcurs_bp)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    return app.test_client()


def test_scop_route_saves_override(client, monkeypatch):
    import foi_parcurs.routes.route_sheet as mod
    captured = {}

    def fake_set(vin, year, month, session_id, text):
        captured.update(vin=vin, year=year, month=month, session_id=session_id, text=text)
        return {str(session_id): text}

    monkeypatch.setattr(mod, 'set_scop_override', fake_set)
    resp = client.post('/api/foi-parcurs/route-sheet/scop',
                       json={'vin': 'V', 'year': 2026, 'month': 8, 'session_id': 202, 'text': 'Reparație DEKRA'})
    assert resp.status_code == 200 and resp.get_json()['success'] is True
    assert captured['session_id'] == 202 and captured['text'] == 'Reparație DEKRA'


def test_scop_route_validates_required(client):
    resp = client.post('/api/foi-parcurs/route-sheet/scop', json={'vin': 'V'})
    assert resp.status_code == 400
