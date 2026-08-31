"""Spy/unit tests: event-bonus summaries & ranking exclude ghost users.

DB-free — monkeypatches the cursor seam (get_db/get_cursor/release_db) so
ghost_exclude_clause() deterministically returns a clause for a fixed
viewer, mirroring tests/hr/test_hr_employees_ghost.py. These are all
cursor-based aggregate/list queries in hr.events.database, so the ghost
filter must land in-SQL (post-filtering a COUNT/SUM/GROUP BY is wrong).

Covers:
  - get_all_event_bonuses    (list builder, LATERAL join)      -> b.user_id
  - get_event_bonuses_summary (COUNT DISTINCT / SUM aggregate)  -> b.user_id
  - get_bonuses_by_month      (GROUP BY month)                  -> vd.user_id
  - get_bonuses_by_employee   (ranking, GROUP BY employee)      -> vd.user_id
  - get_bonuses_by_event      (GROUP BY event/year/month)       -> vd.user_id
"""
from core.organization import ghost


class FakeCursor:
    """Records the last execute() call; supports fetchall and fetchone."""

    def __init__(self):
        self.sql = None
        self.params = None

    def execute(self, sql, params=None):
        self.sql = sql
        self.params = list(params or [])

    def fetchall(self):
        return []

    def fetchone(self):
        return None


def _spy_db(monkeypatch, db_module, cursor):
    monkeypatch.setattr(db_module, 'get_db', lambda: object())
    monkeypatch.setattr(db_module, 'release_db', lambda conn: None)
    monkeypatch.setattr(db_module, 'get_cursor', lambda conn: cursor)


def _spy_ghost(monkeypatch, hidden_id=999, viewer_id=7):
    """Stub the ghost module seams so exactly `hidden_id` is hidden from `viewer_id`."""
    monkeypatch.setattr(ghost, 'get_ghost_user_ids', lambda: {hidden_id})
    monkeypatch.setattr(ghost, 'get_ghost_admin_ids', lambda: set())
    monkeypatch.setattr(ghost, '_resolve_viewer', lambda: viewer_id)
    ghost.invalidate_ghost_cache()


def test_get_all_event_bonuses_excludes_ghosts(monkeypatch):
    import hr.events.database as db

    cursor = FakeCursor()
    _spy_db(monkeypatch, db, cursor)
    _spy_ghost(monkeypatch)

    result = db.get_all_event_bonuses()

    assert result == []
    assert '<> ALL(%s)' in cursor.sql
    assert [999] in cursor.params


def test_get_event_bonuses_summary_excludes_ghosts(monkeypatch):
    import hr.events.database as db

    cursor = FakeCursor()
    _spy_db(monkeypatch, db, cursor)
    _spy_ghost(monkeypatch)

    db.get_event_bonuses_summary()

    assert '<> ALL(%s)' in cursor.sql
    assert [999] in cursor.params


def test_get_bonuses_by_month_excludes_ghosts(monkeypatch):
    import hr.events.database as db

    cursor = FakeCursor()
    _spy_db(monkeypatch, db, cursor)
    _spy_ghost(monkeypatch)

    result = db.get_bonuses_by_month(2026)

    assert result == []
    assert '<> ALL(%s)' in cursor.sql
    assert [999] in cursor.params


def test_get_bonuses_by_employee_excludes_ghosts(monkeypatch):
    import hr.events.database as db

    cursor = FakeCursor()
    _spy_db(monkeypatch, db, cursor)
    _spy_ghost(monkeypatch)

    result = db.get_bonuses_by_employee()

    assert result == []
    assert '<> ALL(%s)' in cursor.sql
    assert [999] in cursor.params


def test_get_bonuses_by_event_excludes_ghosts(monkeypatch):
    import hr.events.database as db

    cursor = FakeCursor()
    _spy_db(monkeypatch, db, cursor)
    _spy_ghost(monkeypatch)

    result = db.get_bonuses_by_event()

    assert result == []
    assert '<> ALL(%s)' in cursor.sql
    assert [999] in cursor.params
