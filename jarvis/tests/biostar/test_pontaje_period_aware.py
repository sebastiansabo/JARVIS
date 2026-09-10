"""Spy tests: the pontaje export is period-aware.

A now-closed contract must still appear in the export for a month it actually
worked (badge punch inside the window), instead of being retroactively hidden
once its mapped JARVIS user is flipped to inactive/closed.

DB-free — monkeypatches BioStarRepository.query_all to capture the rendered
SQL + positional args instead of hitting Postgres (same harness as the ghost
spy tests).
"""
import core.connectors.biostar.repositories.biostar_repository as br
from core.organization import ghost


def _spy(monkeypatch, repo):
    cap = {}
    monkeypatch.setattr(repo, 'query_all', lambda sql, args=None: cap.update(sql=sql, args=list(args or [])) or [])
    monkeypatch.setattr(ghost, 'get_ghost_user_ids', lambda: {999})
    monkeypatch.setattr(ghost, 'get_ghost_admin_ids', lambda: set())
    monkeypatch.setattr(ghost, '_resolve_viewer', lambda: 7)   # non-admin viewer
    ghost.invalidate_ghost_cache()
    return cap


def test_get_pontaje_rows_keeps_period_active_closed_contracts(monkeypatch):
    """scope must retain a contract that badged in the window even when its
    mapped JARVIS user is no longer active/open."""
    repo = br.BioStarRepository()
    cap = _spy(monkeypatch, repo)
    repo.get_pontaje_rows('2026-08-01', '2026-08-31')
    sql = cap['sql']
    assert 'period_active' in sql
    assert 'be.biostar_user_id IN (SELECT biostar_user_id FROM period_active)' in sql


def test_get_pontaje_rows_placeholders_match_args(monkeypatch):
    """Every %s placeholder binds exactly one positional arg — guards the added
    period-active window params against a positional-arg misalignment."""
    repo = br.BioStarRepository()
    cap = _spy(monkeypatch, repo)
    repo.get_pontaje_rows('2026-08-01', '2026-08-31', [42])
    assert cap['sql'].count('%s') == len(cap['args'])
