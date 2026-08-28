"""Route-sheet 'Traseu / Scop' rule.

A client session is a *Test Drive* regardless of distance — redistributing a KM
gap can grow a client trip past the TD threshold, and it must NOT flip into the
internal-trip label. Only an internal session reads
'Deplasare în interes de serviciu'.
"""
import os, sys
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from foi_parcurs.services import route_sheet_service as rss


class _FakeFpRepo:
    """Minimal stand-in: aggregate_month only calls get_contracts + query_all."""
    def __init__(self, rows):
        self._rows = rows

    def get_contracts(self, **kwargs):
        return list(self._rows), len(self._rows)

    def query_all(self, *args, **kwargs):
        return []


class _FakeVehRepo:
    def get_by_vin(self, vin):
        return {'mark': 'MG', 'model': 'MG ZS HEV', 'company_id': None}


def _run(monkeypatch, rows):
    monkeypatch.setattr(rss, '_fp_repo', _FakeFpRepo(rows))
    monkeypatch.setattr(rss, '_veh_repo', _FakeVehRepo())
    # company_id=None on every row keeps aggregate_month off the DB-backed
    # prestator / comodat-routes lookups (they're gated on a company id).
    return rss.aggregate_month('LSJW1', 2026, 8)


def _session(**over):
    base = {
        'id': 1, 'vin': 'LSJW1', 'company_id': None, 'is_internal': False,
        'distance_km': 20, 'km_start': 1000, 'km_end': 1020,
        'departure_datetime': '2026-08-01 10:00:00',
        'created_at': '2026-08-01 10:00:00',
        'client_name': 'Ion Pop', 'year': 2026, 'month': 8,
    }
    base.update(over)
    return base


def test_client_session_is_test_drive_even_over_td_max(monkeypatch):
    # 500 km client trip — well past the 50 km TD threshold, still a Test Drive.
    data = _run(monkeypatch, [_session(distance_km=500, km_end=1500)])
    trip = data['trips'][0]
    assert trip['traseu'].startswith('Test Drive')
    assert trip['is_td'] is True


def test_internal_session_reads_deplasare(monkeypatch):
    # Short internal trip — the business-trip scop, not Test Drive.
    data = _run(monkeypatch, [_session(
        id=2, is_internal=True, distance_km=5, km_start=1500, km_end=1505,
        client_name='', advisor_name='Firma')])
    trip = data['trips'][0]
    assert trip['traseu'] == 'Deplasare în interes de serviciu'
    assert trip['is_td'] is False


def test_null_is_internal_defaults_to_client(monkeypatch):
    # Legacy rows with NULL is_internal are treated as client → Test Drive.
    data = _run(monkeypatch, [_session(is_internal=None)])
    assert data['trips'][0]['traseu'].startswith('Test Drive')
    assert data['trips'][0]['is_td'] is True


def test_missed_sessions_excluded_from_route_sheet(monkeypatch):
    # Ratate (td_status='missed') never drove — kept out of the sheet entirely.
    rows = [
        _session(id=1, td_status='complete'),
        _session(id=2, td_status='missed', km_start=2000, km_end=2050),
    ]
    data = _run(monkeypatch, rows)
    assert len(data['trips']) == 1  # the missed row is dropped


def test_non_missed_statuses_are_kept(monkeypatch):
    # Everything that isn't 'missed' stays (driving/complete/late/planned…).
    rows = [_session(id=1, td_status='driving'), _session(id=2, td_status='complete')]
    data = _run(monkeypatch, rows)
    assert len(data['trips']) == 2


def test_grace_hours_is_six():
    # No-shows are archived 6h after departure (was 8).
    from foi_parcurs.session_lifecycle import GRACE_HOURS
    assert GRACE_HOURS == 6
