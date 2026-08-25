"""Tests for the Weekly Driving Digest service (jarvis/foi_parcurs/services/driving_digest_service.py).

Unit tests only — no DB. psycopg2 is mocked by jarvis/conftest.py, and every
collaborator (repos, LLM client, email/notify infra) is monkeypatched at the
module level, mirroring tests/foi_parcurs/test_reports.py.
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')
from datetime import datetime
from foi_parcurs.services import driving_digest_service as dds


# --- Task 1: week-range helper ---------------------------------------------

def test_week_range_previous_mon_to_sun():
    # Wednesday 2026-08-26 → previous week Mon 2026-08-17 .. Sun 2026-08-23
    frm, to = dds._week_range(datetime(2026, 8, 26, 9, 0))
    assert frm == '2026-08-17'
    assert to == '2026-08-23'


def test_week_range_on_monday_uses_prior_week():
    # Monday 2026-08-24 → previous week Mon 2026-08-17 .. Sun 2026-08-23
    frm, to = dds._week_range(datetime(2026, 8, 24, 8, 0))
    assert frm == '2026-08-17'
    assert to == '2026-08-23'


# --- Task 2: Company-Brand enumeration -------------------------------------

def test_enumerate_company_brands_flattens_pairs():
    companies = [
        {'id': 9, 'company': 'Autoworld PLUS S.R.L.',
         'brands_list': [{'brand': 'Mazda'}, {'brand': 'MG Motor'}]},
        {'id': 11, 'company': 'Autoworld PREMIUM S.R.L.', 'brands_list': [{'brand': 'Volvo'}]},
        {'id': 99, 'company': 'No Brands SRL', 'brands_list': []},
    ]
    pairs = dds._enumerate_company_brands(companies)
    assert (9, 'Autoworld PLUS S.R.L.', 'Mazda') in pairs
    assert (9, 'Autoworld PLUS S.R.L.', 'MG Motor') in pairs
    assert (11, 'Autoworld PREMIUM S.R.L.', 'Volvo') in pairs
    assert all(cid != 99 for cid, _, _ in pairs)  # no-brand company skipped


# --- Task 3: metrics collection ---------------------------------------------

class _FakeFp:
    def __init__(self): self.calls = []
    def report_bundle(self, **kw): self.calls.append(kw); return {'kpis': {'total_sessions': 5, 'total_km': 100}, 'top_advisors': [], 'utilization': [], 'client_vs_internal': []}
class _FakeVeh:
    def __init__(self): self.calls = []
    def report_fleet(self, **kw): self.calls.append(kw); return {'fuel_composition': [], 'top_odometer': []}


def test_collect_calls_aggregates_scoped_to_company_and_brand(monkeypatch):
    fp, veh = _FakeFp(), _FakeVeh()
    monkeypatch.setattr(dds, '_fp_repo', fp)
    monkeypatch.setattr(dds, '_vehicle_repo', veh)
    m = dds._collect(9, 'Mazda', '2026-08-17', '2026-08-23')
    assert fp.calls[0]['company_id'] == 9 and fp.calls[0]['brand'] == 'Mazda'
    assert fp.calls[0]['document_type'] == 'sales'
    assert veh.calls[0]['brand'] == 'Mazda'
    assert m['kpis']['total_sessions'] == 5
    assert 'fuel_composition' in m


def test_collect_board_is_group_wide(monkeypatch):
    fp, veh = _FakeFp(), _FakeVeh()
    monkeypatch.setattr(dds, '_fp_repo', fp)
    monkeypatch.setattr(dds, '_vehicle_repo', veh)
    dds._collect_board('2026-08-17', '2026-08-23')
    assert fp.calls[0]['company_id'] is None and fp.calls[0]['brand'] is None


# --- Task 4: AI narrative + templated fallback ------------------------------

def test_narrative_uses_llm(monkeypatch):
    monkeypatch.setattr(dds, '_llm_ask', lambda prompt, system='', model=None: 'REZUMAT AI')
    txt = dds._narrative({'kpis': {'total_sessions': 5, 'total_km': 100}}, 'Autoworld PLUS · Mazda')
    assert txt == 'REZUMAT AI'


def test_narrative_falls_back_when_llm_raises(monkeypatch):
    def boom(*a, **k): raise RuntimeError('no key')
    monkeypatch.setattr(dds, '_llm_ask', boom)
    txt = dds._narrative({'kpis': {'total_sessions': 5, 'total_km': 100}}, 'Grup')
    assert '5' in txt and 'sesiuni' in txt.lower()  # deterministic fallback mentions the figure
