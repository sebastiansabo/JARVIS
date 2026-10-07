"""Real-DB tests for lead-count KPI increment/decrement (Option B).

Leads are stored as rows in mkt_project_leads. A raw (no-formula) KPI with a
lead source keeps current_value as a live +1/-1 tally as leads are created /
deleted — mirroring link_kpi_deal/unlink_kpi_deal. Formula KPIs (e.g.
'spent / leads') are NOT touched here; they stay on the sync path.

Runs against localhost defaultdb via the require_real_db fixture in conftest.py
(skips cleanly when no real DB is available).
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest  # noqa: E402
from flask import Flask  # noqa: E402
from database import get_db, get_cursor, release_db  # noqa: E402
from marketing.repositories.kpi_repo import KpiRepository  # noqa: E402
from marketing.repositories.lead_repo import ProjectLeadRepository  # noqa: E402
from marketing.repositories.project_repo import ProjectRepository  # noqa: E402
from marketing.repositories.webhook_repo import ProjectWebhookRepository  # noqa: E402
from marketing.routes.leads_webhook import leads_webhook_bp  # noqa: E402
from marketing.services import webhook_token  # noqa: E402

kpi_repo = KpiRepository()
lead_repo = ProjectLeadRepository()
project_repo = ProjectRepository()
webhook_repo = ProjectWebhookRepository()


def _current_value(kpi_id):
    row = kpi_repo.query_one(
        'SELECT current_value FROM mkt_project_kpis WHERE id=%s', (kpi_id,))
    return float(row['current_value'] or 0)


def _make_lead(project_id, name='Lead'):
    return lead_repo.create(project_id, {'contact_name': name})


@pytest.fixture
def mk(require_real_db):
    """Factory: build a project + KPI (+ optional lead source). Cleans up."""
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute('SELECT id FROM companies WHERE is_active ORDER BY id LIMIT 1')
        row = cur.fetchone()
    finally:
        release_db(conn)
    assert row is not None, 'no active company found in seed DB'
    company_id = row['id']

    created_projects, created_defs = [], []

    def _make(formula=None, link_source=True):
        project_id = project_repo.create(
            'LeadKPI Test', company_id, owner_id=1, created_by=1, project_type='campaign')
        created_projects.append(project_id)
        kpi_def_id = kpi_repo.create_definition('Leads Test', 'leads_test', formula=formula)
        created_defs.append(kpi_def_id)
        kpi_id = kpi_repo.add_project_kpi(project_id, kpi_def_id)
        source_id = None
        if link_source:
            source_id = kpi_repo.link_lead_source(kpi_id, role='leads' if formula else 'input')
        return {'project_id': project_id, 'kpi_id': kpi_id,
                'kpi_def_id': kpi_def_id, 'source_id': source_id}

    yield _make

    for pid in created_projects:
        kpi_repo.execute('DELETE FROM mkt_projects WHERE id=%s', (pid,))
    for did in created_defs:
        kpi_repo.execute('DELETE FROM mkt_kpi_definitions WHERE id=%s', (did,))


def test_increment_raises_current_value_by_one(mk):
    k = mk()
    assert _current_value(k['kpi_id']) == 0
    lead_id = _make_lead(k['project_id'])
    kpi_repo.increment_lead_count(k['project_id'], lead_id)
    assert _current_value(k['kpi_id']) == 1


def test_increment_is_idempotent_per_lead(mk):
    k = mk()
    lead_id = _make_lead(k['project_id'])
    kpi_repo.increment_lead_count(k['project_id'], lead_id)
    kpi_repo.increment_lead_count(k['project_id'], lead_id)  # retry must not double-count
    assert _current_value(k['kpi_id']) == 1


def test_decrement_lowers_value_and_floors_at_zero(mk):
    k = mk()
    lead_id = _make_lead(k['project_id'])
    kpi_repo.increment_lead_count(k['project_id'], lead_id)
    kpi_repo.decrement_lead_count(k['project_id'], lead_id)
    assert _current_value(k['kpi_id']) == 0
    # Reversing a lead that's no longer counted must floor at 0, not go negative.
    kpi_repo.decrement_lead_count(k['project_id'], lead_id)
    assert _current_value(k['kpi_id']) == 0


def test_formula_kpi_is_not_incremented(mk):
    # A formula KPI stays on the sync path — lead increments must skip it.
    k = mk(formula='leads + 0')
    lead_id = _make_lead(k['project_id'])
    kpi_repo.increment_lead_count(k['project_id'], lead_id)
    assert _current_value(k['kpi_id']) == 0


def test_seed_on_link_sets_value_to_existing_lead_count(mk):
    # Linking a lead source to a raw KPI with pre-existing leads seeds the count.
    k = mk(link_source=False)
    for _ in range(3):
        _make_lead(k['project_id'])
    kpi_repo.link_lead_source(k['kpi_id'], role='input')
    assert _current_value(k['kpi_id']) == 3


def _lead_snapshot_count(kpi_id):
    row = kpi_repo.query_one(
        "SELECT COUNT(*) AS n FROM mkt_kpi_snapshots WHERE project_kpi_id=%s AND source='lead'",
        (kpi_id,))
    return row['n']


def test_unlink_lead_source_clears_the_lead_tally(mk):
    # Removing the (only, unfiltered) lead source must tear down the ledger it
    # seeded: current_value back to 0 and no orphaned 'lead:' snapshots left to
    # keep decrementing an untracked KPI.
    k = mk(link_source=False)
    for _ in range(3):
        _make_lead(k['project_id'])
    source_id = kpi_repo.link_lead_source(k['kpi_id'], role='input')
    assert _current_value(k['kpi_id']) == 3
    kpi_repo.unlink_lead_source(k['kpi_id'], source_id)
    assert _current_value(k['kpi_id']) == 0
    assert _lead_snapshot_count(k['kpi_id']) == 0


def test_unlink_keeps_tally_while_another_unfiltered_source_remains(mk):
    # A KPI with two unfiltered lead sources still counts leads after one is
    # removed, so the tally must survive until the LAST source goes.
    k = mk(link_source=False)
    for _ in range(2):
        _make_lead(k['project_id'])
    s1 = kpi_repo.link_lead_source(k['kpi_id'], role='input')
    kpi_repo.link_lead_source(k['kpi_id'], role='input')
    assert _current_value(k['kpi_id']) == 2
    kpi_repo.unlink_lead_source(k['kpi_id'], s1)
    assert _current_value(k['kpi_id']) == 2
    assert _lead_snapshot_count(k['kpi_id']) == 2


@pytest.fixture
def webhook_client():
    """Minimal Flask app with only the lead webhook blueprint (no full boot)."""
    app = Flask(__name__)
    app.register_blueprint(leads_webhook_bp)
    return app.test_client()


def test_webhook_lead_create_increments_raw_lead_kpi(mk, webhook_client):
    # The live path: a lead POSTed by Zapier/webhook bumps the raw lead KPI.
    k = mk()
    assert _current_value(k['kpi_id']) == 0
    plaintext, token_hash, prefix = webhook_token.generate_token()
    webhook_repo.create(k['project_id'], 'test-token', token_hash, prefix, created_by=1)

    resp = webhook_client.post(
        '/leads',
        json={'contact_name': 'Zapier Lead', 'phone': '0700111222'},
        headers={'Authorization': f'Bearer {plaintext}'},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    assert _current_value(k['kpi_id']) == 1
