"""Spy/unit tests: 360-evaluation rater/ratee pools & population exclude
ghost users.

DB-free — monkeypatches CycleRepository.query_all so ghost_exclude_clause()
deterministically returns a clause for a fixed viewer, mirroring
tests/hr/test_hr_employees_ghost.py.

Covers:
  - peer_pool                (same-department pool)          -> u.id (driving)
  - sincron_peer_pool         (org-node pool)                 -> u.id (INNER-joined)
  - list_eligible_employees   (population picker)             -> u.id (driving)
  - sincron_org_tree          (org tree + member_count)       -> se.mapped_jarvis_user_id
                                inside the `elig` member-count CTE (INNER-joined
                                there, so the outer LEFT JOIN's NULLs never reach
                                the ghost filter — COUNT DISTINCT ignores NULLs).
"""
import pytest

import hr.evaluation360.repositories.cycle_repository as cr
from core.organization import ghost


@pytest.fixture
def spy_ghost(monkeypatch):
    """Stub the ghost module seams so exactly {999} is hidden from viewer 7.

    Invalidates the ghost cache in both setup and teardown so this test's
    monkeypatched seams can never leak a cached value into (or pick one up
    stale from) another test.
    """
    monkeypatch.setattr(ghost, 'get_ghost_user_ids', lambda: {999})
    monkeypatch.setattr(ghost, 'get_ghost_admin_ids', lambda: set())
    monkeypatch.setattr(ghost, '_resolve_viewer', lambda: 7)
    ghost.invalidate_ghost_cache()
    try:
        yield
    finally:
        ghost.invalidate_ghost_cache()


def _repo_spy(monkeypatch, repo):
    cap = {}
    monkeypatch.setattr(
        repo, 'query_all',
        lambda sql, args=None: cap.update(sql=sql, args=list(args or [])) or [],
        raising=False)
    return cap


def test_peer_pool_excludes_ghosts(monkeypatch, spy_ghost):
    repo = cr.CycleRepository()
    cap = _repo_spy(monkeypatch, repo)

    repo.peer_pool(employee_id=1)

    assert 'u.id <> ALL(%s)' in cap['sql']
    assert [999] in cap['args']


def test_sincron_peer_pool_excludes_ghosts(monkeypatch, spy_ghost):
    repo = cr.CycleRepository()
    cap = _repo_spy(monkeypatch, repo)

    repo.sincron_peer_pool(employee_id=1)

    assert 'u.id <> ALL(%s)' in cap['sql']
    assert [999] in cap['args']


def test_list_eligible_employees_excludes_ghosts(monkeypatch, spy_ghost):
    repo = cr.CycleRepository()
    cap = _repo_spy(monkeypatch, repo)

    repo.list_eligible_employees()

    assert 'u.id <> ALL(%s)' in cap['sql']
    assert [999] in cap['args']


def test_sincron_org_tree_excludes_ghosts_from_member_count(monkeypatch, spy_ghost):
    repo = cr.CycleRepository()
    cap = _repo_spy(monkeypatch, repo)

    repo.sincron_org_tree()

    assert 'se.mapped_jarvis_user_id <> ALL(%s)' in cap['sql']
    assert [999] in cap['args']
