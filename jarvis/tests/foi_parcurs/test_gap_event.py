"""Tests for the "Eveniment" gap-distribution path on the monthly Foaie de
Parcurs — distributing an unjustified odometer gap onto a promo EVENT instead of
a client (Client extra) or the neighbouring sessions (Absorb).

An event distribution inserts a gap-fill session tagged `source='gap-event'`
with the event name in `itinerary`. On the sheet it renders as a documented
promo trip (`Deplasare în interes de serviciu — participare la {event}, în scop
de promovare`), NOT a Test Drive, so the gap closes and stops reading
"nejustificat".

Repos are faked at module level so no database is touched.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest

import foi_parcurs.services.route_sheet_service as rss


# ── aggregate_month: a gap-event row renders as a promo trip ────────────────

class AggFakeRepo:
    """Serves aggregate_month's get_contracts + the (ungated) project query_all."""

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
        # company_id None → prestator/comodat/project company lookups are skipped.
        return {'mark': 'VW', 'model': 'Golf', 'fuel_type': 'Diesel',
                'company_id': None, 'registration_number': 'B123ABC'}


def _event_and_td_rows():
    common = {'company_id': None, 'registration_number': 'B123ABC',
              'route_type': 'TD', 'fuel_consumed_liters': 0, 'is_internal': False}
    return [
        {**common, 'id': 100, 'departure_datetime': '2026-07-15T10:00:00',
         'created_at': '2026-07-15T10:00:00', 'km_start': 1050, 'km_end': 1080,
         'distance_km': 30, 'source': 'gap-event', 'itinerary': 'Salon Auto',
         'advisor_name': 'Ion Consilier', 'client_name': ''},
        {**common, 'id': 101, 'departure_datetime': '2026-07-16T10:00:00',
         'created_at': '2026-07-16T10:00:00', 'km_start': 1080, 'km_end': 1100,
         'distance_km': 20, 'source': 'td_form', 'itinerary': 'oraș',
         'advisor_name': 'Ana', 'client_name': 'Client X'},
    ]


@pytest.fixture
def agg(monkeypatch):
    monkeypatch.setattr(rss, '_fp_repo', AggFakeRepo(_event_and_td_rows()))
    monkeypatch.setattr(rss, '_veh_repo', AggFakeVeh())


def test_gap_event_row_renders_promo_traseu(agg):
    data = rss.aggregate_month('VIN1', 2026, 7)
    ev = next(t for t in data['trips'] if t['km_start'] == 1050)
    assert ev['traseu'] == ('Deplasare în interes de serviciu — participare la '
                            'Salon Auto, în scop de promovare')
    # An event drive is NOT a test drive (so the monthly summary counts it apart).
    assert ev['is_td'] is False
    # Șofer = the consilier, since an event drive has no client name.
    assert ev['driver'] == 'Ion Consilier'


def test_ordinary_td_row_still_renders_test_drive(agg):
    data = rss.aggregate_month('VIN1', 2026, 7)
    td = next(t for t in data['trips'] if t['km_start'] == 1080)
    assert td['traseu'] == 'Test Drive VW Golf'
    assert td['is_td'] is True


# ── redistribute_gap: an event item persists source + event name ────────────

class FakeRepo:
    def __init__(self):
        self.executed = []

    def query_one(self, sql, params=None):
        if 'fp_km_configs' in sql:
            return {'td_km_max': 50}
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


def test_redistribute_event_item_persists_source_and_name(fake_repos):
    item = {'date': '2026-07-15', 'event_name': 'Salon Auto București',
            'km_start': 1050, 'km_end': 1080, 'advisor_name': 'Ion Consilier'}
    n = rss.redistribute_gap('VIN1', 2026, 7, [item], user_name='Fallback User')
    assert n == 1
    _, params = fake_repos.executed[0]
    assert 'gap-event' in params                 # source tag
    assert 'Salon Auto București' in params      # event name stored in itinerary
    assert 'Ion Consilier' in params             # consilier (Șofer)
    # No client name / signature / license for an event drive.
    assert params[-4] == ''                      # client_signature
    assert params[-3] is None                    # driver_license_photo


def test_redistribute_event_item_sets_return_datetime_from_end(fake_repos):
    item = {'date': '2026-08-05', 'end_date': '2026-08-12', 'event_name': 'Roadshow',
            'km_start': 6008, 'km_end': 6222}
    rss.redistribute_gap('VIN1', 2026, 8, [item])
    _, params = fake_repos.executed[0]
    # Plecare from the start date, Sosire from the end date → an event interval.
    assert any(isinstance(p, str) and p.startswith('2026-08-05') for p in params)
    assert any(isinstance(p, str) and p.startswith('2026-08-12') for p in params)


def test_redistribute_client_extra_has_no_return_datetime(fake_repos):
    # A single-day client-extra fill has no end_date → return_datetime stays NULL.
    item = {'date': '2026-08-05', 'client_name': 'Ion', 'km_start': 6008, 'km_end': 6222}
    rss.redistribute_gap('VIN1', 2026, 8, [item])
    _, params = fake_repos.executed[0]
    assert not any(isinstance(p, str) and p.startswith('2026-08-12') for p in params)
