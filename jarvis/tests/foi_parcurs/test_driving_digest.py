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


# --- Task 5: HTML rendering -------------------------------------------------

def test_render_section_contains_title_narrative_and_kpis():
    html = dds._render_section('Autoworld PLUS · Mazda',
                               {'kpis': {'total_sessions': 5, 'total_km': 100, 'completion_rate': 90}},
                               'Rezumat text')
    assert 'Autoworld PLUS · Mazda' in html
    assert 'Rezumat text' in html
    assert '5' in html and '100' in html


def test_render_email_wraps_sections():
    doc = dds._render_email(['<section>A</section>', '<section>B</section>'], '17.08–23.08')
    assert doc.strip().lower().startswith('<!doctype html>') or '<html' in doc.lower()
    assert '17.08–23.08' in doc and '<section>A</section>' in doc and '<section>B</section>' in doc


# --- Task 6: recipient resolution -------------------------------------------

class _FakeCompanyRepo:
    # get_responsables returns the REAL shape: {user_id, user_name} (no email).
    def get_responsables(self, cid): return [{'user_id': 1, 'user_name': 'Mgr X'}] if cid == 9 else []
    # The real class exposes get(company_id), not get_by_id.
    def get(self, cid): return {'id': cid, 'alert_email': 'fallback@aw.ro'}
class _FakeUserRepo:
    def get_all(self): return [
        {'id': 1, 'email': 'mgr@aw.ro', 'role_name': 'Manager'},
        {'id': 2, 'email': 'board1@aw.ro', 'role_name': 'board'},
        {'id': 3, 'email': 'board2@aw.ro', 'role_name': 'Board'},
    ]


def test_company_recipients_resolves_responsable_emails(monkeypatch):
    # responsable user_id 1 → resolved to mgr@aw.ro via the users id→email map
    monkeypatch.setattr(dds, '_company_repo', _FakeCompanyRepo())
    monkeypatch.setattr(dds, '_user_repo', _FakeUserRepo())
    emails, ids = dds._company_recipients(9)
    assert emails == ['mgr@aw.ro'] and ids == [1]


def test_company_recipients_falls_back_to_alert_email(monkeypatch):
    # no responsables → fall back to companies.alert_email, no in-app recipients
    monkeypatch.setattr(dds, '_company_repo', _FakeCompanyRepo())
    monkeypatch.setattr(dds, '_user_repo', _FakeUserRepo())
    emails, ids = dds._company_recipients(11)
    assert emails == ['fallback@aw.ro'] and ids == []


def test_board_recipients_by_role(monkeypatch):
    monkeypatch.setattr(dds, '_user_repo', _FakeUserRepo())
    emails, ids = dds._board_recipients()
    assert set(emails) == {'board1@aw.ro', 'board2@aw.ro'} and set(ids) == {2, 3}


# --- Task 7: gate + generate_and_send orchestration -------------------------

def _patch_send_infra(monkeypatch):
    sent = []
    monkeypatch.setattr(dds, '_send_email', lambda **kw: sent.append(kw) or (True, ''))
    monkeypatch.setattr(dds, '_notify_users', lambda **kw: None)
    monkeypatch.setattr(dds, '_smtp_ok', lambda: True)
    # data stubs
    monkeypatch.setattr(dds, '_enumerate_company_brands', lambda companies: [(9, 'Autoworld PLUS', 'Mazda')])
    monkeypatch.setattr(dds, '_all_companies', lambda: [{'id': 9, 'company': 'Autoworld PLUS', 'brands_list': [{'brand': 'Mazda'}]}])
    monkeypatch.setattr(dds, '_collect', lambda *a, **k: {'kpis': {'total_sessions': 3}})
    monkeypatch.setattr(dds, '_collect_board', lambda *a, **k: {'kpis': {'total_sessions': 9}})
    monkeypatch.setattr(dds, '_narrative', lambda *a, **k: 'txt')
    monkeypatch.setattr(dds, '_company_recipients', lambda cid: (['mgr@aw.ro'], [1]))
    monkeypatch.setattr(dds, '_board_recipients', lambda: (['board@aw.ro'], [2]))
    return sent


def test_skips_when_disabled(monkeypatch):
    _patch_send_infra(monkeypatch)
    monkeypatch.setattr(dds, '_settings_enabled', lambda: False)
    monkeypatch.setattr(dds, '_is_prod', lambda: True)
    out = dds.generate_and_send()
    assert out['sent'] == 0 and out['skipped'] == 'disabled'


def test_skips_when_not_prod(monkeypatch):
    _patch_send_infra(monkeypatch)
    monkeypatch.setattr(dds, '_settings_enabled', lambda: True)
    monkeypatch.setattr(dds, '_is_prod', lambda: False)
    out = dds.generate_and_send()
    assert out['sent'] == 0 and out['skipped'] == 'not_prod'


def test_sends_company_and_board_when_enabled_prod(monkeypatch):
    sent = _patch_send_infra(monkeypatch)
    monkeypatch.setattr(dds, '_settings_enabled', lambda: True)
    monkeypatch.setattr(dds, '_is_prod', lambda: True)
    out = dds.generate_and_send()
    # one company-brand email + one board email
    assert out['sent'] == 2
    tos = [s['to_email'] for s in sent]
    assert 'mgr@aw.ro' in tos and 'board@aw.ro' in tos


def test_is_prod_true_for_prod_db(monkeypatch):
    # prod DB host → prod, even without FLASK_ENV (DO services carry none)
    monkeypatch.setenv('DATABASE_URL',
                       'postgresql://doadmin:x@jarvis-main-do-user-24639451-0.k.db.ondigitalocean.com:25060/defaultdb')
    monkeypatch.delenv('FLASK_ENV', raising=False)
    assert dds._is_prod() is True


def test_is_prod_false_for_staging_db(monkeypatch):
    # staging DB host → NOT prod, so staging never emails
    monkeypatch.setenv('DATABASE_URL',
                       'postgresql://doadmin:x@mkt-staging-do-user-24639451-0.k.db.ondigitalocean.com:25060/defaultdb')
    monkeypatch.delenv('FLASK_ENV', raising=False)
    assert dds._is_prod() is False


# --- Task 8: scheduler task wrapper -----------------------------------------

def test_task_wrapper_swallows_errors(monkeypatch):
    import tasks.driving_digest as td
    monkeypatch.setattr(td, 'generate_and_send', lambda: (_ for _ in ()).throw(RuntimeError('x')))
    td.run_weekly_driving_digest()  # must not raise
