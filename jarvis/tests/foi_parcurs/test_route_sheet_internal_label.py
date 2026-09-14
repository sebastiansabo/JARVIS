"""Phase 1 cosmetic route-sheet changes:
  A) `include_internal` — internal drives can be dropped from the exported
     listing while the month's odometer span (and thus KM totals) stays intact,
     so any excluded KM surfaces as a normal gap row.
  B) distance-based client-drive label — a trip over 50 km reads
     'Comodat / Test Drive {model}', 50 km or less stays 'Test Drive {model}'.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from foi_parcurs.services import route_sheet_service as rss
from foi_parcurs.services.route_sheet_service import _td_traseu


# ── B) distance-based label (pure) ──────────────────────────────────────────
def test_td_label_short_drive_is_plain_test_drive():
    assert _td_traseu(30, 'MG HS') == 'Test Drive MG HS'


def test_td_label_exactly_50_is_still_test_drive():
    # "up to 50 km is just Test Drive" — 50 is inclusive.
    assert _td_traseu(50, 'MG HS') == 'Test Drive MG HS'


def test_td_label_over_50_is_comodat_test_drive():
    assert _td_traseu(51, 'MG HS') == 'Comodat / Test Drive MG HS'


def test_td_label_none_distance_defaults_to_test_drive():
    assert _td_traseu(None, 'MG HS') == 'Test Drive MG HS'


# ── A) include_internal + integration of the label into aggregate_month ─────
class _FakeFpRepo:
    def __init__(self, rows):
        self._rows = rows

    def get_contracts(self, **_):
        return list(self._rows), len(self._rows)

    def query_all(self, *_a, **_k):
        return []


def _contract(cid, km_start, km_end, *, is_internal=False, itinerary='', day=5):
    return {
        'id': cid,
        'company_id': None,          # falsy → skips the CompanyRepository DB lookup
        'company_name': 'Autoworld',
        'departure_datetime': f'2026-09-{day:02d}T10:00:00',
        'return_datetime': f'2026-09-{day:02d}T12:00:00',
        'created_at': f'2026-09-{day:02d}T09:00:00',
        'km_start': km_start,
        'km_end': km_end,
        'distance_km': km_end - km_start,
        'is_internal': is_internal,
        'source': 'batch',
        'itinerary': itinerary,
        'advisor_name': 'Advisor',
        'client_name': 'Client',
        'route_type': 'TD',
        'registration_number': 'CJ01ABC',
    }


def _setup(monkeypatch, rows):
    monkeypatch.setattr(rss, '_fp_repo', _FakeFpRepo(rows))
    monkeypatch.setattr(rss, '_veh_repo',
                        type('V', (), {'get_by_vin': staticmethod(lambda vin: {'mark': 'MG', 'model': 'HS'})})())


# a short client drive, an internal drive between them, then a long client drive
def _rows():
    return [
        _contract(1, 1000, 1030, day=3),                       # 30 km client → Test Drive
        _contract(2, 1030, 1200, is_internal=True,
                  itinerary='Deplasare service', day=5),        # 170 km internal
        _contract(3, 1200, 1260, day=8),                       # 60 km client → Comodat / Test Drive
    ]


def test_aggregate_includes_internal_by_default(monkeypatch):
    _setup(monkeypatch, _rows())
    data = rss.aggregate_month('VF1X', 2026, 9)
    traseus = [t['traseu'] for t in data['trips']]
    assert traseus == ['Test Drive MG HS', 'Deplasare service', 'Comodat / Test Drive MG HS']
    assert data['totals']['sessions'] == 3
    assert data['totals']['km'] == 260          # 1260 − 1000


def test_aggregate_excludes_internal_but_keeps_km_span(monkeypatch):
    _setup(monkeypatch, _rows())
    data = rss.aggregate_month('VF1X', 2026, 9, include_internal=False)
    traseus = [t['traseu'] for t in data['trips']]
    # internal row is gone from the listing …
    assert traseus == ['Test Drive MG HS', 'Comodat / Test Drive MG HS']
    assert data['totals']['sessions'] == 2
    # … but the odometer span (and total KM) is unchanged — continuity preserved.
    assert data['totals']['km_start'] == 1000
    assert data['totals']['km_end'] == 1260
    assert data['totals']['km'] == 260


def test_excluded_internal_km_surfaces_as_gap_row(monkeypatch):
    _setup(monkeypatch, _rows())
    data = rss.aggregate_month('VF1X', 2026, 9, include_internal=False)
    rows = rss._rows_with_gaps(data['trips'], data['totals']['km_start'], data['totals']['km_end'])
    gaps = [r for r in rows if r['gap']]
    # the 1030→1200 stretch the internal drive covered is now an unjustified gap
    assert any(g['km_start'] == 1030 and g['km_end'] == 1200 for g in gaps)
