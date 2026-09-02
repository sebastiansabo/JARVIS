"""Spy/unit tests: Chat directory / auto-enroll / target-sync exclude ghost
users (task 10).

DB-free — monkeypatches ChatRepository's query/execute methods to capture the
SQL text and params without a real Postgres, mirroring
tests/happy/test_happy_ghost.py.

Scope (per the ghost-users plan, task 10):
  - search_users: the people/@mention/invite directory — a READ surface, so
    it uses the DEFAULT (context) viewer. A super-admin can still find/@mention
    a ghost; a normal user cannot.
  - add_all_active_users: bulk INSERT...SELECT channel enrollment — always
    force-hides ghosts (viewer_id=None), independent of who triggers it.
  - sync_members_from_targets: target-materialization (auto-add-by-audience)
    — every branch (all/company/node) force-hides ghosts (viewer_id=None).

Out of scope (spec boundary, NOT touched): get_posts, get_reactions,
get_channel_members, get_channels' last_message_author — a ghost already in a
channel stays a functional participant and their sent messages still show.
"""
import chat.repositories.chat_repository as cr
from core.organization import ghost


def setup_function(_fn):
    ghost.invalidate_ghost_cache()


def teardown_function(_fn):
    ghost.invalidate_ghost_cache()


def _spy_ghost(monkeypatch, hidden_id=999):
    """Exactly `hidden_id` is a ghost; no admin bypass configured."""
    monkeypatch.setattr(ghost, 'get_ghost_user_ids', lambda: {hidden_id})
    monkeypatch.setattr(ghost, 'get_ghost_admin_ids', lambda: set())
    ghost.invalidate_ghost_cache()


# ── search_users: directory / @mention / invite (READ surface, context viewer) ──

def test_search_users_excludes_ghosts(monkeypatch):
    repo = cr.ChatRepository()
    cap = {}
    monkeypatch.setattr(
        repo, 'query_all',
        lambda sql, args=None: cap.update(sql=sql, args=list(args or [])) or [],
        raising=False)
    _spy_ghost(monkeypatch)
    monkeypatch.setattr(ghost, '_resolve_viewer', lambda: 7)
    ghost.invalidate_ghost_cache()

    repo.search_users('a')

    assert '<> ALL(%s)' in cap['sql']
    assert [999] in cap['args']


def test_search_users_admin_bypasses_ghost_filter(monkeypatch):
    """A super-admin (in ghost_visible_admin_ids) is NOT filtered — they can
    still find/@mention a ghost via the directory search."""
    repo = cr.ChatRepository()
    cap = {}
    monkeypatch.setattr(
        repo, 'query_all',
        lambda sql, args=None: cap.update(sql=sql, args=list(args or [])) or [],
        raising=False)
    monkeypatch.setattr(ghost, 'get_ghost_user_ids', lambda: {999})
    monkeypatch.setattr(ghost, 'get_ghost_admin_ids', lambda: {7})
    monkeypatch.setattr(ghost, '_resolve_viewer', lambda: 7)
    ghost.invalidate_ghost_cache()

    repo.search_users('a')

    assert '<> ALL' not in cap['sql']
    assert 999 not in cap['args']
    assert [999] not in cap['args']


# ── add_all_active_users: bulk channel enrollment (force-hide) ─────────────

def test_add_all_active_users_excludes_ghosts(monkeypatch):
    repo = cr.ChatRepository()
    cap = {}
    monkeypatch.setattr(
        repo, 'execute',
        lambda sql, args=None: cap.update(sql=sql, args=list(args or [])) or None,
        raising=False)
    _spy_ghost(monkeypatch)

    repo.add_all_active_users(channel_id=5)

    assert '<> ALL(%s)' in cap['sql']
    assert [999] in cap['args']
    assert cap['args'][0] == 5  # channel_id placeholder untouched


def test_add_all_active_users_is_viewer_independent(monkeypatch):
    """Must force-hide ghosts even with no request-context viewer — proves
    viewer_id=None (force-hide), not the context-viewer default that would
    let the triggering user's own admin status leak through."""
    repo = cr.ChatRepository()
    cap = {}
    monkeypatch.setattr(
        repo, 'execute',
        lambda sql, args=None: cap.update(sql=sql, args=list(args or [])) or None,
        raising=False)
    _spy_ghost(monkeypatch)

    def _boom():
        raise AssertionError('must not resolve a request-context viewer for enrollment')
    monkeypatch.setattr(ghost, '_resolve_viewer', _boom)

    repo.add_all_active_users(channel_id=5)  # must not raise

    assert '<> ALL(%s)' in cap['sql']
    assert [999] in cap['args']


# ── sync_members_from_targets: target-materialization (force-hide) ─────────

def _fake_query_all_for_targets(targets, calls):
    """Fake query_all that returns `targets` for get_channel_targets() and
    records every other call (the per-branch user-resolution queries)."""
    def _fn(sql, args=None):
        record = {'sql': sql, 'args': list(args or [])}
        calls.append(record)
        if 'digest_channel_targets' in sql:
            return targets
        return []
    return _fn


def test_sync_members_from_targets_all_branch_excludes_ghosts(monkeypatch):
    repo = cr.ChatRepository()
    calls = []
    targets = [{'id': 1, 'target_type': 'all', 'company_id': None, 'node_id': None}]
    monkeypatch.setattr(repo, 'query_all', _fake_query_all_for_targets(targets, calls), raising=False)
    monkeypatch.setattr(repo, 'execute', lambda *a, **k: None, raising=False)
    _spy_ghost(monkeypatch)

    def _boom():
        raise AssertionError('must not resolve a request-context viewer for target-sync')
    monkeypatch.setattr(ghost, '_resolve_viewer', _boom)

    repo.sync_members_from_targets(channel_id=42)  # must not raise

    branch_calls = [c for c in calls if 'FROM users WHERE is_active' in c['sql']]
    assert len(branch_calls) == 1
    assert '<> ALL(%s)' in branch_calls[0]['sql']
    assert [999] in branch_calls[0]['args']


def test_sync_members_from_targets_company_branch_excludes_ghosts(monkeypatch):
    repo = cr.ChatRepository()
    calls = []
    targets = [{'id': 1, 'target_type': 'company', 'company_id': 3, 'node_id': None}]
    monkeypatch.setattr(repo, 'query_all', _fake_query_all_for_targets(targets, calls), raising=False)
    monkeypatch.setattr(repo, 'execute', lambda *a, **k: None, raising=False)
    _spy_ghost(monkeypatch)

    repo.sync_members_from_targets(channel_id=42)

    branch_calls = [c for c in calls if 'company_responsables' in c['sql']]
    assert len(branch_calls) == 1
    sql, args = branch_calls[0]['sql'], branch_calls[0]['args']
    # ghost clause spliced into both halves of the UNION
    assert sql.count('<> ALL(%s)') == 2
    assert args == [3, [999], 3, [999]]


def test_sync_members_from_targets_node_branch_excludes_ghosts(monkeypatch):
    repo = cr.ChatRepository()
    calls = []
    targets = [{'id': 1, 'target_type': 'node', 'company_id': None, 'node_id': 9}]
    monkeypatch.setattr(repo, 'query_all', _fake_query_all_for_targets(targets, calls), raising=False)
    monkeypatch.setattr(repo, 'execute', lambda *a, **k: None, raising=False)
    _spy_ghost(monkeypatch)

    repo.sync_members_from_targets(channel_id=42)

    branch_calls = [c for c in calls if 'structure_node_members' in c['sql'] and 'WITH RECURSIVE' in c['sql']]
    assert len(branch_calls) == 1
    sql, args = branch_calls[0]['sql'], branch_calls[0]['args']
    assert '<> ALL(%s)' in sql
    assert args == [9, [999]]
