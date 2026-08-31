"""Spy/unit tests: Happy Pulse cohorts, Campaign targets, and monthly-giveable
enrollment exclude ghost users (task 9).

DB-free — monkeypatches repository query/execute methods (and, for the
multi-statement execute_many() sites, a MagicMock cursor) so we can capture
the SQL text and params without a real Postgres, mirroring
tests/profile/test_dept_pulse_ghost.py and tests/hr/test_eval360_ghost.py.

All three surfaces here are enrollment / target-materialization / scheduled
bodies (spec: pulse invites, campaign targets, monthly wallet grants) — per
the ghost-users plan, these must exclude ghosts UNCONDITIONALLY, regardless
of who triggers the action. So every fix below calls
ghost_exclude_clause(col, viewer_id=None) (force-hide), never the
context-viewer default.
"""
from unittest.mock import MagicMock

import happy.jobs as jobs
import happy.repositories.campaign_repository as cr
import happy.repositories.pulse_repository as pr
from core.organization import ghost
from happy.repositories import PraiseRepository


def setup_function(_fn):
    ghost.invalidate_ghost_cache()


def teardown_function(_fn):
    ghost.invalidate_ghost_cache()


def _spy_ghost(monkeypatch, hidden_id=999):
    """Exactly `hidden_id` is a ghost; no admin bypass configured."""
    monkeypatch.setattr(ghost, 'get_ghost_user_ids', lambda: {hidden_id})
    monkeypatch.setattr(ghost, 'get_ghost_admin_ids', lambda: set())
    ghost.invalidate_ghost_cache()


def _fake_execute_many(cap, fetchone_value):
    """Return a replacement for repo.execute_many that runs the real
    callback against a MagicMock cursor and records every cursor.execute()
    call, so multi-statement (UPDATE/INSERT/SELECT-count) bodies can be
    inspected without a DB."""
    def _run(work):
        cur = MagicMock()
        cur.fetchone.return_value = fetchone_value
        result = work(cur)
        cap['calls'] = cur.execute.call_args_list
        return result
    return _run


def _find_call(calls, needle):
    for c in calls:
        sql = c[0][0]
        if needle in sql:
            return sql, list(c[0][1] or [])
    raise AssertionError(f'no cursor.execute call contains {needle!r}')


# ── Campaign targets: refresh_targets() (real enrollment/materialization) ──

def test_refresh_targets_excludes_ghosts(monkeypatch):
    repo = cr.CampaignRepository()
    _spy_ghost(monkeypatch)
    monkeypatch.setattr(repo, 'get_audience', lambda campaign_id: [])
    cap = {}
    monkeypatch.setattr(repo, 'execute_many', _fake_execute_many(cap, {'n': 0}))

    repo.refresh_targets(campaign_id=1)

    sql, params = _find_call(cap['calls'], 'INSERT INTO happy.campaign_targets')
    assert '<> ALL(%s)' in sql
    assert [999] in params


def test_refresh_targets_ghost_exclusion_is_viewer_independent(monkeypatch):
    """Must exclude ghosts even with no request-context viewer at all (e.g.
    the nightly new-joiner-inheritance job) — proves viewer_id=None
    (force-hide), not the context-viewer default that would self-bypass."""
    repo = cr.CampaignRepository()
    _spy_ghost(monkeypatch)
    monkeypatch.setattr(repo, 'get_audience', lambda campaign_id: [])

    def _boom():
        raise AssertionError('must not resolve a request-context viewer for enrollment')
    monkeypatch.setattr(ghost, '_resolve_viewer', _boom)

    cap = {}
    monkeypatch.setattr(repo, 'execute_many', _fake_execute_many(cap, {'n': 0}))

    repo.refresh_targets(campaign_id=1)  # must not raise

    sql, params = _find_call(cap['calls'], 'INSERT INTO happy.campaign_targets')
    assert '<> ALL(%s)' in sql
    assert [999] in params


# ── Campaign targets: preview_audience() (shares _audience_where) ──────────

def test_preview_audience_excludes_ghosts(monkeypatch):
    repo = cr.CampaignRepository()
    _spy_ghost(monkeypatch)
    cap = {}

    def fake_query_one(sql, params=None):
        cap['count_sql'] = sql
        cap['count_params'] = list(params or [])
        return {'n': 0}

    def fake_query_all(sql, params=None):
        cap['cohorts_sql'] = sql
        cap['cohorts_params'] = list(params or [])
        return []

    monkeypatch.setattr(repo, 'query_one', fake_query_one)
    monkeypatch.setattr(repo, 'query_all', fake_query_all)

    repo.preview_audience([])

    assert '<> ALL(%s)' in cap['count_sql']
    assert [999] in cap['count_params']
    assert '<> ALL(%s)' in cap['cohorts_sql']
    assert [999] in cap['cohorts_params']


# ── Pulse: open_pulse() default (all-active-users) audience ────────────────

def test_open_pulse_default_audience_excludes_ghosts(monkeypatch):
    repo = pr.PulseRepository()
    _spy_ghost(monkeypatch)
    monkeypatch.setattr(repo, 'get_pulse', lambda pulse_id: {'status': 'draft'})
    monkeypatch.setattr(repo, 'get_questions', lambda pulse_id: [{'id': 1}])
    cap = {}
    monkeypatch.setattr(repo, 'execute_many', _fake_execute_many(cap, {'c': 0}))

    repo.open_pulse(pulse_id=1, now='2026-08-31T00:00:00Z')

    sql, params = _find_call(cap['calls'], 'INSERT INTO happy.pulse_invites')
    assert 'SELECT %s, id FROM users' in sql
    assert '<> ALL(%s)' in sql
    assert [999] in params


def test_open_pulse_explicit_audience_is_admin_scoped_not_ghost_filtered(monkeypatch):
    """Documents the scope decision: an explicit admin-picked id list (not
    the default SELECT-all audience) is a per-row VALUES insert, not an
    audience materialization — task 9's brief scopes the ghost fix to
    open_pulse's 'INSERT...SELECT of an audience' branch only. This asserts
    the ghost id IS still inserted here, proving the branch is deliberately
    left as-is (see task-9-report.md)."""
    repo = pr.PulseRepository()
    _spy_ghost(monkeypatch)
    monkeypatch.setattr(repo, 'get_pulse', lambda pulse_id: {'status': 'draft'})
    monkeypatch.setattr(repo, 'get_questions', lambda pulse_id: [{'id': 1}])
    cap = {}
    monkeypatch.setattr(repo, 'execute_many', _fake_execute_many(cap, {'c': 0}))

    repo.open_pulse(pulse_id=1, now='2026-08-31T00:00:00Z', audience_user_ids=[999, 5])

    inserted = [
        c[0][1][1] for c in cap['calls']
        if c[0][0].startswith('INSERT INTO happy.pulse_invites (pulse_id, user_id) VALUES')
    ]
    assert inserted == [999, 5]


# ── Pulse: resolve_cohort / _subtree_members — self-access / no-audience ───

def test_resolve_cohort_own_node_lookup_unaffected_by_ghost_status(monkeypatch):
    """resolve_cohort's initial 'find MY OWN node' lookup resolves the
    CALLING/responding user's own membership (self-access) and the function
    returns a cohort-key STRING, never a user list — must stay unfiltered
    so a ghost can still resolve their own cohort to respond to a pulse."""
    repo = pr.PulseRepository()
    _spy_ghost(monkeypatch)
    calls = []

    def fake_query_one(sql, params=None):
        calls.append((sql, list(params or [])))
        return None  # short-circuits to the "no organigram" company fallback

    monkeypatch.setattr(repo, 'query_one', fake_query_one)

    result = repo.resolve_cohort(999)  # 999 is itself the "ghost" here

    assert result == 'all'
    own_node_sql = calls[0][0]
    assert '<> ALL' not in own_node_sql
    assert 'is_ghost' not in own_node_sql
    assert calls[0][1] == [999]


def test_subtree_members_query_unaffected_by_ghost_status(monkeypatch):
    """Returns a scalar headcount (anonymity-threshold sizing only), never a
    list of user/employee rows — no ghost filter to splice in."""
    repo = pr.PulseRepository()
    _spy_ghost(monkeypatch)
    cap = {}

    def fake_query_one(sql, params=None):
        cap['sql'] = sql
        cap['params'] = list(params or [])
        return {'c': 3}

    monkeypatch.setattr(repo, 'query_one', fake_query_one)

    n = repo._subtree_members(42)

    assert n == 3
    assert '<> ALL' not in cap['sql']
    assert 'is_ghost' not in cap['sql']


# ── Monthly giveable: grant_monthly_giveable() (scheduled enrollment) ──────

def test_grant_monthly_giveable_excludes_ghosts(monkeypatch):
    _spy_ghost(monkeypatch)
    cap = {}

    def fake_query_all(self, sql, params=None):
        cap['sql'] = sql
        cap['params'] = list(params or [])
        return []

    monkeypatch.setattr(PraiseRepository, 'query_all', fake_query_all)

    n = jobs.grant_monthly_giveable()

    assert '<> ALL(%s)' in cap['sql']
    assert [999] in cap['params']
    assert n == 0


def test_grant_monthly_giveable_is_viewer_independent(monkeypatch):
    """Scheduled job — no Flask request context at all — must still hide
    ghosts, proving viewer_id=None (force-hide) is used."""
    _spy_ghost(monkeypatch)

    def _boom():
        raise AssertionError('must not resolve a request-context viewer for a scheduled job')
    monkeypatch.setattr(ghost, '_resolve_viewer', _boom)

    cap = {}

    def fake_query_all(self, sql, params=None):
        cap['sql'] = sql
        cap['params'] = list(params or [])
        return []

    monkeypatch.setattr(PraiseRepository, 'query_all', fake_query_all)

    jobs.grant_monthly_giveable()  # must not raise

    assert '<> ALL(%s)' in cap['sql']
    assert [999] in cap['params']
