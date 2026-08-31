"""Final-review FIX 3 (IMPORTANT, coverage gap): the Online Users presence
widget (`GET /api/online-users` -> UserRepository.get_online_users /
get_online_count) must not show ghosts as "online" to everyone.

Before the fix, both queries selected active users unfiltered. This is a
READ surface rendered in a request context, so it uses the DEFAULT viewer
(ghost_exclude_clause() with no viewer_id override): super-admins on the
ghost_visible_admin_ids allowlist still see ghosts online, everyone else
doesn't.

Spy tests, DB-free — mirrors tests/biostar/test_biostar_ghost.py and
tests/hr/test_scheduler_ghost.py: monkeypatches UserRepository.query_all to
capture the rendered SQL + positional args instead of hitting Postgres, and
stubs the ghost module seams so ghost_exclude_clause() deterministically
resolves for a fixed viewer.

get_online_count delegates to get_online_users (count = len(list)), so the
exclusion lives in ONE in-SQL WHERE clause and both callers inherit it — this
suite proves both callers actually observe it (not just get_online_users).
"""
import core.auth.repositories.user_repository as ur_mod
from core.organization import ghost


def _spy_normal_viewer(monkeypatch, repo):
    """Non-admin viewer (7): ghost 999 must be excluded in-SQL."""
    cap = {}
    monkeypatch.setattr(
        repo, 'query_all',
        lambda sql, args=None: cap.update(sql=sql, args=list(args or [])) or [],
        raising=False,
    )
    monkeypatch.setattr(ghost, 'get_ghost_user_ids', lambda: {999})
    monkeypatch.setattr(ghost, 'get_ghost_admin_ids', lambda: set())
    monkeypatch.setattr(ghost, '_resolve_viewer', lambda: 7)
    ghost.invalidate_ghost_cache()
    return cap


def _spy_super_admin_viewer(monkeypatch, repo):
    """Viewer (7) IS on the ghost-admin allowlist: no exclusion clause added."""
    cap = {}
    monkeypatch.setattr(
        repo, 'query_all',
        lambda sql, args=None: cap.update(sql=sql, args=list(args or [])) or [],
        raising=False,
    )
    monkeypatch.setattr(ghost, 'get_ghost_user_ids', lambda: {999})
    monkeypatch.setattr(ghost, 'get_ghost_admin_ids', lambda: {7})
    monkeypatch.setattr(ghost, '_resolve_viewer', lambda: 7)
    ghost.invalidate_ghost_cache()
    return cap


def test_get_online_users_excludes_ghosts_for_normal_viewer(monkeypatch):
    repo = ur_mod.UserRepository()
    cap = _spy_normal_viewer(monkeypatch, repo)

    repo.get_online_users()

    assert 'id <> ALL(%s)' in cap['sql']
    assert [999] in cap['args']


def test_get_online_users_no_filter_for_super_admin_viewer(monkeypatch):
    repo = ur_mod.UserRepository()
    cap = _spy_super_admin_viewer(monkeypatch, repo)

    repo.get_online_users()

    assert '<> ALL(%s)' not in cap['sql']


def test_get_online_count_excludes_ghosts_for_normal_viewer(monkeypatch):
    repo = ur_mod.UserRepository()
    cap = _spy_normal_viewer(monkeypatch, repo)

    repo.get_online_count()

    assert 'id <> ALL(%s)' in cap['sql']
    assert [999] in cap['args']


def test_get_online_count_no_filter_for_super_admin_viewer(monkeypatch):
    repo = ur_mod.UserRepository()
    cap = _spy_super_admin_viewer(monkeypatch, repo)

    repo.get_online_count()

    assert '<> ALL(%s)' not in cap['sql']
