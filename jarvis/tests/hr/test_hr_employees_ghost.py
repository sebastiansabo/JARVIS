"""Spy/unit tests: HR analytics surfaces exclude ghost users.

DB-free — monkeypatches the cursor/query seams so ghost_exclude_clause()
deterministically returns a clause for a fixed viewer, mirroring
tests/biostar/test_biostar_ghost.py.

Covers:
  - hr.events.database.get_all_hr_employees            (cursor-based; in-SQL)
  - hr.events.repositories.employee_overview_repository
        .EmployeeOverviewRepository.get_absence_status_for_date (query_all-based; in-SQL)
  - hr.events.routes.employees._drop_ghosts_from_result (route-level Python drop)
"""
import pathlib
from datetime import date

from core.organization import ghost


def _spy_ghost(monkeypatch, hidden_id=999, viewer_id=7):
    """Stub the ghost module seams so exactly `hidden_id` is hidden from `viewer_id`."""
    monkeypatch.setattr(ghost, 'get_ghost_user_ids', lambda: {hidden_id})
    monkeypatch.setattr(ghost, 'get_ghost_admin_ids', lambda: set())
    monkeypatch.setattr(ghost, '_resolve_viewer', lambda: viewer_id)
    ghost.invalidate_ghost_cache()


# ── get_all_hr_employees (cursor-based) ──────────────────────────────────

def test_get_all_hr_employees_excludes_ghosts(monkeypatch):
    import hr.events.database as db

    captured = {}

    class FakeCursor:
        def execute(self, sql, params=None):
            captured['sql'] = sql
            captured['params'] = list(params or [])

        def fetchall(self):
            return []

    monkeypatch.setattr(db, 'get_db', lambda: object())
    monkeypatch.setattr(db, 'release_db', lambda conn: None)
    monkeypatch.setattr(db, 'get_cursor', lambda conn: FakeCursor())
    _spy_ghost(monkeypatch)

    result = db.get_all_hr_employees(user_context={'scope': 'all'})

    assert result == []
    assert '<> ALL(%s)' in captured['sql']
    assert [999] in captured['params']


def test_get_all_hr_employees_no_filter_for_super_admin(monkeypatch):
    """A viewer on the ghost-visible admin list gets no exclusion clause."""
    import hr.events.database as db

    captured = {}

    class FakeCursor:
        def execute(self, sql, params=None):
            captured['sql'] = sql
            captured['params'] = list(params or [])

        def fetchall(self):
            return []

    monkeypatch.setattr(db, 'get_db', lambda: object())
    monkeypatch.setattr(db, 'release_db', lambda conn: None)
    monkeypatch.setattr(db, 'get_cursor', lambda conn: FakeCursor())
    monkeypatch.setattr(ghost, 'get_ghost_user_ids', lambda: {999})
    monkeypatch.setattr(ghost, 'get_ghost_admin_ids', lambda: {7})
    monkeypatch.setattr(ghost, '_resolve_viewer', lambda: 7)
    ghost.invalidate_ghost_cache()

    db.get_all_hr_employees(user_context={'scope': 'all'})

    assert '<> ALL(%s)' not in captured['sql']


# ── get_absence_status_for_date (query_all-based) ────────────────────────

def test_get_absence_status_for_date_excludes_ghosts(monkeypatch):
    from hr.events.repositories.employee_overview_repository import EmployeeOverviewRepository

    repo = EmployeeOverviewRepository()
    captured = {}

    def fake_query_all(sql, params=None):
        captured['sql'] = sql
        captured['params'] = list(params or [])
        return []

    monkeypatch.setattr(repo, 'query_all', fake_query_all)
    _spy_ghost(monkeypatch)

    result = repo.get_absence_status_for_date(date(2026, 8, 30))

    assert result == []
    assert 'u.id <> ALL(%s)' in captured['sql']
    assert [999] in captured['params']


# ── work-stats route drop logic ──────────────────────────────────────────

def test_drop_ghosts_from_result_removes_hidden_uid():
    from hr.events.routes.employees import _drop_ghosts_from_result

    result = {7: {'total_hours': 10}, 999: {'total_hours': 5}}
    filtered = _drop_ghosts_from_result(result, {999})

    assert 7 in filtered
    assert 999 not in filtered
    assert filtered == {7: {'total_hours': 10}}


def test_drop_ghosts_from_result_noop_when_no_hidden():
    from hr.events.routes.employees import _drop_ghosts_from_result

    result = {7: {'total_hours': 10}}
    filtered = _drop_ghosts_from_result(result, set())

    assert filtered == result


def test_work_stats_route_wires_ghost_drop():
    """The route must call hidden_ghost_ids(current_user.id) and apply the
    drop to the composed per-employee `result` dict before returning it —
    NOT re-filter get_range_summary, which Task 4 already ghost-filters.
    """
    src = (pathlib.Path(__file__).resolve().parents[2]
           / 'hr' / 'events' / 'routes' / 'employees.py').read_text()

    assert 'from core.organization.ghost import hidden_ghost_ids' in src
    assert 'hidden_ghost_ids(current_user.id)' in src
    assert '_drop_ghosts_from_result(result, hidden)' in src
