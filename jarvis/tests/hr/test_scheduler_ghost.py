"""Spy/unit tests: scheduled HR alerts & pontaje digests exclude ghost users.

DB-free — monkeypatches the query/repo/SMTP seams so ghost_exclude_clause()
and hidden_ghost_ids() deterministically resolve for a fixed ghost set,
mirroring tests/hr/test_hr_employees_ghost.py and tests/org/test_ghost.py.

Covers:
  - hr.events.repositories.employee_overview_repository
        .EmployeeOverviewRepository.get_all_missing_punches_for_date  (query_all-based; in-SQL)
  - tasks.hr_attendance._drop_ghost_employees / _drop_ghost_rows       (Python row-drop helpers)
  - tasks.hr_attendance.send_pontaje_digest                            (full call, mocked deps)
  - tasks.hr_attendance.send_monthly_pontaje_summary /
        compute_hr_weekly_report_data                                 (wiring check via source)
"""
import datetime
import pathlib

import pytest

from core.organization import ghost


@pytest.fixture(autouse=True)
def _clear_ghost_cache():
    ghost.invalidate_ghost_cache()
    yield
    ghost.invalidate_ghost_cache()


# ── get_all_missing_punches_for_date (query_all-based, missing-punch subject) ──

def test_missing_punches_excludes_ghosts(monkeypatch):
    import hr.events.repositories.employee_overview_repository as eo

    repo = eo.EmployeeOverviewRepository()
    cap = {}
    monkeypatch.setattr(
        repo, 'query_all',
        lambda sql, args=None: cap.update(sql=sql, args=list(args or [])) or [],
        raising=False,
    )
    monkeypatch.setattr(ghost, 'get_ghost_user_ids', lambda: {999})
    monkeypatch.setattr(ghost, 'get_ghost_admin_ids', lambda: set())
    monkeypatch.setattr(ghost, '_resolve_viewer', lambda: None)   # cron context
    ghost.invalidate_ghost_cache()

    repo.get_all_missing_punches_for_date('2026-08-20')

    assert '<> ALL(%s)' in cap['sql']
    assert 'u.id <> ALL(%s)' in cap['sql']
    assert [999] in cap['args']


def test_missing_punches_no_filter_for_super_admin_viewer(monkeypatch):
    """Default viewer resolution: if this query is ever reused from a request
    context by a viewer on the ghost-visible admin list, no exclusion clause
    is added (super-admin bypass) — the cron path itself has no request
    context so `_resolve_viewer()` naturally returns None (hide all)."""
    import hr.events.repositories.employee_overview_repository as eo

    repo = eo.EmployeeOverviewRepository()
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

    repo.get_all_missing_punches_for_date('2026-08-20')

    assert '<> ALL(%s)' not in cap['sql']


# ── Python row-drop helpers used by the pontaje digest builders ─────────────

def test_drop_ghost_employees_removes_hidden_uid():
    from tasks.hr_attendance import _drop_ghost_employees

    employee_map = {
        7: {'name': 'Normal User', 'jarvis_user_id': 7},
        999: {'name': 'Ghost User', 'jarvis_user_id': 999},
    }
    filtered = _drop_ghost_employees(employee_map, {999})

    assert 7 in filtered
    assert 999 not in filtered
    assert filtered == {7: {'name': 'Normal User', 'jarvis_user_id': 7}}


def test_drop_ghost_employees_noop_when_no_hidden():
    from tasks.hr_attendance import _drop_ghost_employees

    employee_map = {7: {'name': 'Normal User', 'jarvis_user_id': 7}}
    filtered = _drop_ghost_employees(employee_map, set())

    assert filtered == employee_map


def test_drop_ghost_rows_removes_hidden_uid():
    from tasks.hr_attendance import _drop_ghost_rows

    rows = [
        {'user_id': 7, 'name': 'Normal User', 'remaining': 5},
        {'user_id': 999, 'name': 'Ghost User', 'remaining': 20},
    ]
    filtered = _drop_ghost_rows(rows, {999}, key='user_id')

    assert filtered == [{'user_id': 7, 'name': 'Normal User', 'remaining': 5}]


def test_drop_ghost_rows_noop_when_no_hidden():
    from tasks.hr_attendance import _drop_ghost_rows

    rows = [{'user_id': 7, 'name': 'Normal User'}]
    filtered = _drop_ghost_rows(rows, set())

    assert filtered == rows


# ── send_pontaje_digest — full call, ghost excluded from the emailed CSV ────

def test_send_pontaje_digest_excludes_ghost_from_csv_body(monkeypatch):
    import tasks.hr_attendance as hr_att
    import core.notifications.repositories as notif_repo_pkg
    import core.services.notification_service as notif_svc
    import core.connectors.biostar.repositories.biostar_repository as bio_mod
    import core.connectors.sincron.repositories.sincron_repository as sincron_mod

    # Fix "today" to a deterministic Thursday so weekend/Monday branches
    # don't change behavior depending on when this test happens to run.
    _real_date = datetime.date

    class _FixedDate:
        @staticmethod
        def today():
            return _real_date(2026, 8, 20)

    monkeypatch.setattr(datetime, 'date', _FixedDate)

    class FakeNotifRepo:
        def get_settings(self):
            return {
                'pontaje_digest_enabled': 'true',
                'pontaje_digest_daily_recipients': 'ops@example.com',
            }

    monkeypatch.setattr(notif_repo_pkg, 'NotificationRepository', FakeNotifRepo)
    monkeypatch.setattr(notif_svc, 'is_smtp_configured', lambda: True)

    sent = {}

    def fake_send_email(**kwargs):
        sent['kwargs'] = kwargs
        return True, None

    monkeypatch.setattr(notif_svc, 'send_email', fake_send_email)

    class FakeBioRepo:
        def get_daily_summary(self, date_str):
            return []

        def get_all_employees(self, active_only=True):
            return [
                {'biostar_user_id': 'B1', 'mapped_jarvis_user_id': 7,
                 'mapped_jarvis_user_name': 'Normal User', 'jarvis_user_active': True,
                 'user_group_name': 'Ops'},
                {'biostar_user_id': 'B2', 'mapped_jarvis_user_id': 999,
                 'mapped_jarvis_user_name': 'Ghost User', 'jarvis_user_active': True,
                 'user_group_name': 'Ops'},
            ]

    monkeypatch.setattr(bio_mod, 'BioStarRepository', FakeBioRepo)

    class FakeSincronRepo:
        def get_all_day_codes(self, year, month):
            return []

    monkeypatch.setattr(sincron_mod, 'SincronRepository', FakeSincronRepo)

    monkeypatch.setattr(ghost, 'get_ghost_user_ids', lambda: {999})
    monkeypatch.setattr(ghost, 'get_ghost_admin_ids', lambda: set())
    monkeypatch.setattr(ghost, '_resolve_viewer', lambda: None)
    ghost.invalidate_ghost_cache()

    hr_att.send_pontaje_digest()

    assert 'kwargs' in sent, "send_email was never called — digest aborted early"
    csv_bytes = sent['kwargs']['attachments'][0][1]
    csv_text = csv_bytes.decode('utf-8-sig')
    assert 'Normal User' in csv_text
    assert 'Ghost User' not in csv_text
    assert 'Total employees: 1' in sent['kwargs']['html_body']


# ── send_monthly_pontaje_summary / compute_hr_weekly_report_data ───────────
# Both pull from calendar/holiday-repository DB state that's impractical to
# fully mock in a DB-free unit test; verify the wiring at the source level
# (same standard as tests/hr/test_hr_employees_ghost.py's route-wiring check)
# alongside the direct helper-drop tests above, which prove the drop logic
# itself is correct.

def _hr_attendance_source():
    path = pathlib.Path(__file__).resolve().parents[2] / 'tasks' / 'hr_attendance.py'
    return path.read_text()


def test_pontaje_digests_import_hidden_ghost_ids():
    src = _hr_attendance_source()
    assert 'from core.organization.ghost import hidden_ghost_ids' in src


def test_daily_and_monthly_digest_wire_ghost_drop():
    src = _hr_attendance_source()
    assert src.count('_drop_ghost_employees(employee_map, hidden_ghost_ids(None))') == 2


def test_weekly_report_wires_ghost_drop():
    src = _hr_attendance_source()
    assert "_drop_ghost_rows(all_co, hidden_ghost_ids(None), key='user_id')" in src
