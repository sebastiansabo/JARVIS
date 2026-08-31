"""Spy tests: pontaje/attendance roster queries exclude ghost users.

DB-free — monkeypatches BioStarRepository.query_all to capture the rendered
SQL + positional args instead of hitting Postgres, and stubs the ghost module
seams so ghost_exclude_clause() deterministically returns a clause for a
fixed viewer.
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


def test_get_pontaje_rows_excludes_ghosts(monkeypatch):
    repo = br.BioStarRepository()
    cap = _spy(monkeypatch, repo)
    repo.get_pontaje_rows('2026-08-01', '2026-08-31')
    assert 'be.mapped_jarvis_user_id <> ALL(%s)' in cap['sql']
    assert [999] in cap['args']


def test_get_range_summary_excludes_ghosts(monkeypatch):
    repo = br.BioStarRepository()
    cap = _spy(monkeypatch, repo)
    repo.get_range_summary('2026-08-01', '2026-08-31')
    assert 'be.mapped_jarvis_user_id <> ALL(%s)' in cap['sql']
    assert [999] in cap['args']


def test_get_attendance_overview_excludes_ghosts(monkeypatch):
    repo = br.BioStarRepository()
    cap = _spy(monkeypatch, repo)
    repo.get_attendance_overview('2026-08-30')
    assert 'u.id <> ALL(%s)' in cap['sql']
    assert [999] in cap['args']


def test_get_attendance_week_excludes_ghosts(monkeypatch):
    repo = br.BioStarRepository()
    cap = _spy(monkeypatch, repo)
    repo.get_attendance_week('2026-08-30')
    assert 'u.id <> ALL(%s)' in cap['sql']
    assert [999] in cap['args']


def test_get_daily_summary_excludes_ghosts(monkeypatch):
    repo = br.BioStarRepository()
    cap = _spy(monkeypatch, repo)
    repo.get_daily_summary('2026-08-30')
    assert 'p.mapped_jarvis_user_id <> ALL(%s)' in cap['sql']
    assert 'be3.mapped_jarvis_user_id <> ALL(%s)' in cap['sql']
    # ghost param appears once per UNION branch
    assert cap['args'].count([999]) == 2


def test_get_all_employees_excludes_ghosts(monkeypatch):
    repo = br.BioStarRepository()
    cap = _spy(monkeypatch, repo)
    repo.get_all_employees()
    assert 'be.mapped_jarvis_user_id <> ALL(%s)' in cap['sql']
    assert [999] in cap['args']
