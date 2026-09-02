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


def _run(monkeypatch, rows, year=2026, month=8):
    monkeypatch.setattr(rss, '_fp_repo', _FakeFpRepo(rows))
    monkeypatch.setattr(rss, '_veh_repo', _FakeVehRepo())
    # company_id=None on every row keeps aggregate_month off the DB-backed
    # prestator / comodat-routes lookups (they're gated on a company id).
    return rss.aggregate_month('LSJW1', year, month)


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


def test_internal_session_excluded_from_route_sheet(monkeypatch):
    # Internal (company) drives are no longer listed on the client foaie — their
    # KM becomes a gap instead of a "Deplasare" line.
    data = _run(monkeypatch, [_session(
        id=2, is_internal=True, km_start=1500, km_end=1505,
        client_name='', advisor_name='Firma')])
    assert data['trips'] == []


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


def test_internal_drives_excluded_and_km_becomes_gap(monkeypatch):
    # An internal (company) drive between two client drives isn't listed on the
    # foaie; its 100 km stays in the total and surfaces as a gap.
    rows = [
        _session(id=1, is_internal=False, td_status='complete', km_start=1000, km_end=1100),
        _session(id=2, is_internal=True, td_status='driving', km_start=1100, km_end=1200,
                 client_name='', advisor_name='Firma'),
        _session(id=3, is_internal=False, td_status='complete', km_start=1200, km_end=1300),
    ]
    data = _run(monkeypatch, rows)
    assert len(data['trips']) == 2                         # internal not listed
    assert all(not t.get('is_internal') for t in data['trips'])
    assert data['totals']['km'] == 300                     # its 100 km still counted
    from foi_parcurs.services.route_sheet_service import _rows_with_gaps
    gaps = [r for r in _rows_with_gaps(data['trips']) if r['gap']]
    assert len(gaps) == 1 and gaps[0]['distance_km'] == 100  # reflected as a gap


def test_period_uses_departure_not_created():
    # A session created in July but DRIVEN on Aug 1 belongs to August's foaie.
    assert rss._period({'departure_datetime': '2026-08-01 09:00:00',
                        'created_at': '2026-07-30 10:00:00'}) == (2026, 8)
    # No departure → fall back to created_at.
    assert rss._period({'departure_datetime': None,
                        'created_at': '2026-07-15 10:00:00'}) == (2026, 7)


def test_next_month_client_gated_out_of_month(monkeypatch):
    # A client that drove Aug 1 must not appear in July's foaie.
    rows = [
        _session(id=1, td_status='complete', km_start=5651, km_end=5699,
                 departure_datetime='2026-07-28 10:00:00'),
        _session(id=2, td_status='complete', km_start=5699, km_end=5740,
                 departure_datetime='2026-08-01 10:00:00', client_name='Anca'),
    ]
    data = _run(monkeypatch, rows, year=2026, month=7)
    assert len(data['trips']) == 1                         # only the July drive
    assert data['trips'][0]['km_end'] == 5699


def test_boundary_internal_drive_is_trailing_gap(monkeypatch):
    # July: two client drives, plus an internal drive at the odometer edge (after
    # the last client) and a next-month client. The internal 7 km stays as a
    # trailing gap in July; the next-month client is gated out.
    rows = [
        _session(id=1, td_status='complete', km_start=5651, km_end=5699,
                 departure_datetime='2026-07-28 10:00:00'),
        _session(id=2, td_status='complete', km_start=5699, km_end=5740,
                 departure_datetime='2026-07-31 10:00:00'),
        _session(id=3, is_internal=True, td_status='driving', km_start=5740, km_end=5747,
                 departure_datetime='2026-07-30 10:00:00', client_name='', advisor_name='Firma'),
        _session(id=4, td_status='complete', km_start=5747, km_end=5753,
                 departure_datetime='2026-08-01 10:00:00', client_name='Anca'),
    ]
    data = _run(monkeypatch, rows, year=2026, month=7)
    assert len(data['trips']) == 2                         # two July client drives
    assert data['totals']['km'] == 96                      # 5651→5747 incl. the internal 7 km
    assert data['totals']['km_end'] == 5747
    from foi_parcurs.services.route_sheet_service import _rows_with_gaps
    gaps = [r for r in _rows_with_gaps(data['trips'], data['totals']['km_start'], data['totals']['km_end'])
            if r['gap']]
    assert len(gaps) == 1 and gaps[0]['distance_km'] == 7   # trailing internal gap
    assert gaps[0]['km_start'] == 5740 and gaps[0]['km_end'] == 5747
