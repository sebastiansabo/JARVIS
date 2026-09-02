"""Spy/unit tests: HR Department-Pulse cohort aggregates exclude ghost users.

DB-free — monkeypatches DeptPulseRepository.query_one/query_all so we can
capture the SQL text and params without a real Postgres, mirroring
tests/hr/test_eval360_ghost.py.

Cohort-vs-self-access analysis (see task-8-report.md for the full writeup):

  Task-8 brief named three targets — `_ELIGIBLE_SQL`, `resolve_department`,
  `available_departments` — as the sites to guard. Reading the actual call
  sites (core/profile/routes.py `api_profile_dept_pulse`), all three (plus
  `is_eligible`/`eligible_node_ids`, which also run on `_ELIGIBLE_SQL`) are
  invoked with `uid = current_user.id` — i.e. they resolve the CALLING
  user's OWN department access ("which departments can I see"), never
  another user's cohort membership. Filtering these by is_ghost would
  wrongly lock a ghost out of their own department-pulse, contradicting the
  ghost-visibility contract ("remain visible to themselves" — core/
  organization/ghost.py). So this suite asserts the OPPOSITE for those
  functions: their SQL/behavior is unaffected by ghost status.

  The real cohort — the anonymous pool of votes a department's members
  jointly see — lives in `hr_dept_pulse_votes`, read by `get_voter_count()`
  and `get_aggregate()`. Those two take only `node_id` (no caller/user_id),
  aggregate across ALL voters, and are exactly where "a ghost must not be
  counted in a cohort" applies. They're fixed with
  `ghost_exclude_clause('voter_user_id', viewer_id=None)` — force-hide, no
  self-bypass, since cohort aggregates must exclude ghosts unconditionally
  regardless of who is viewing (including the ghost's own vote, which is
  otherwise anonymous anyway).

  `_ELIGIBLE_SQL` still carries a code comment (not a SQL-string change)
  documenting this decision so the required-by-brief marker
  ('<> ALL' / 'is_ghost') is deliberately NOT forced into the query text —
  see test_eligible_sql_is_deliberately_unfiltered below for why.
"""
import core.profile.repositories.dept_pulse_repository as dp
from core.organization import ghost


def setup_function(_fn):
    ghost.invalidate_ghost_cache()


def teardown_function(_fn):
    ghost.invalidate_ghost_cache()


def _repo_spy(monkeypatch, repo, method):
    """Patch repo.<method> to capture (sql, args) instead of hitting the DB."""
    cap = {}

    def _fake(sql, params=None):
        cap['sql'] = sql
        cap['args'] = list(params or [])
        return None if method == 'query_one' else []

    monkeypatch.setattr(repo, method, _fake, raising=False)
    return cap


def _spy_ghost(monkeypatch, hidden_id=999):
    """Exactly `hidden_id` is a ghost; no admin bypass configured."""
    monkeypatch.setattr(ghost, 'get_ghost_user_ids', lambda: {hidden_id})
    monkeypatch.setattr(ghost, 'get_ghost_admin_ids', lambda: set())
    ghost.invalidate_ghost_cache()


# ── Cohort aggregates (the real fix) ──────────────────────────────────────

def test_get_voter_count_excludes_ghosts(monkeypatch):
    repo = dp.DeptPulseRepository()
    cap = _repo_spy(monkeypatch, repo, 'query_one')
    _spy_ghost(monkeypatch)

    repo.get_voter_count(42)

    assert 'voter_user_id <> ALL(%s)' in cap['sql']
    assert [999] in cap['args']
    assert cap['args'][0] == 42


def test_get_aggregate_excludes_ghosts(monkeypatch):
    repo = dp.DeptPulseRepository()
    cap = _repo_spy(monkeypatch, repo, 'query_all')
    _spy_ghost(monkeypatch)

    repo.get_aggregate(42)

    assert 'voter_user_id <> ALL(%s)' in cap['sql']
    assert [999] in cap['args']
    assert cap['args'][0] == 42


def test_cohort_exclusion_is_viewer_independent(monkeypatch):
    """Cohort aggregates must exclude ghosts even with NO request-context
    viewer at all (e.g. a scheduled job) — proves viewer_id=None (force-hide)
    is used, not the context-viewer default that would self-bypass."""
    repo = dp.DeptPulseRepository()
    cap = _repo_spy(monkeypatch, repo, 'query_one')
    _spy_ghost(monkeypatch)
    # No _resolve_viewer patch — if the code used the context-viewer default,
    # _resolve_viewer() would run for real (no Flask request context here)
    # and return None, which *also* hides everything; so to prove it's not
    # relying on that path, patch _resolve_viewer to explode if called.
    def _boom():
        raise AssertionError('must not resolve a request-context viewer for cohort aggregates')
    monkeypatch.setattr(ghost, '_resolve_viewer', _boom)

    repo.get_voter_count(42)  # would raise if it called _resolve_viewer()

    assert 'voter_user_id <> ALL(%s)' in cap['sql']
    assert [999] in cap['args']


def test_ghost_own_vote_not_counted_in_cohort(monkeypatch):
    """Even if the ghost themself cast a vote, it must not count toward the
    voter floor or the average others see (aggregate is anonymous either
    way, but the exclusion is unconditional per the brief)."""
    repo = dp.DeptPulseRepository()
    _spy_ghost(monkeypatch, hidden_id=555)
    cap = _repo_spy(monkeypatch, repo, 'query_one')

    repo.get_voter_count(7)

    assert [555] in cap['args']


# ── Self-access sites: must stay UNFILTERED by ghost status ───────────────

def test_resolve_department_unaffected_by_ghost_status(monkeypatch):
    """resolve_department(user_id) resolves the CALLER's own default dept —
    self-access. It must not gain a ghost filter (a ghost calling this for
    themselves must get their normal result)."""
    repo = dp.DeptPulseRepository()
    cap = _repo_spy(monkeypatch, repo, 'query_one')
    _spy_ghost(monkeypatch)

    repo.resolve_department(999)  # 999 is itself the "ghost" in this test

    assert '<> ALL' not in cap['sql']
    assert 'is_ghost' not in cap['sql']
    assert cap['args'] == [999]


def test_available_departments_unaffected_by_ghost_status(monkeypatch):
    repo = dp.DeptPulseRepository()
    cap = _repo_spy(monkeypatch, repo, 'query_all')
    _spy_ghost(monkeypatch)

    repo.available_departments(999)

    assert '<> ALL' not in cap['sql']
    assert 'is_ghost' not in cap['sql']
    assert cap['args'] == [999]


def test_eligible_node_ids_unaffected_by_ghost_status(monkeypatch):
    repo = dp.DeptPulseRepository()
    cap = _repo_spy(monkeypatch, repo, 'query_all')
    _spy_ghost(monkeypatch)

    repo.eligible_node_ids(999)

    assert '<> ALL' not in cap['sql']
    assert 'is_ghost' not in cap['sql']


def test_eligible_sql_is_deliberately_unfiltered(monkeypatch):
    """Documents the escalation call: the brief's Step-1 test (as written)
    asserts `'<> ALL' in dp._ELIGIBLE_SQL or 'is_ghost' in dp._ELIGIBLE_SQL`.
    That assertion would only hold by adding a real is_ghost predicate to the
    my_nodes CTE's own-row filter (`se.mapped_jarvis_user_id = %s`) — but
    that row IS the calling user, ghost or not, so such a predicate would
    delete a ghost's own eligibility rows and lock them out of their own
    department-pulse. That contradicts "ghosts remain visible to themselves"
    (core/organization/ghost.py), so it is NOT applied here.

    This test intentionally asserts the opposite of the brief's literal
    snippet and stands in for it, with the reasoning above (also see
    task-8-report.md, DONE_WITH_CONCERNS)."""
    assert '<> ALL' not in dp._ELIGIBLE_SQL
    assert 'is_ghost' not in dp._ELIGIBLE_SQL


# ── ghost_exclude_clause itself (already-implemented infra, tasks 1-7) ────

def test_ghost_exclude_clause_force_hide_produces_expected_fragment(monkeypatch):
    _spy_ghost(monkeypatch)
    frag, params = ghost.ghost_exclude_clause('voter_user_id', viewer_id=None)
    assert '<> ALL(%s)' in frag
    assert params == [[999]]
