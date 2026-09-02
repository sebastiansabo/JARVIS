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


def test_missing_punches_force_hidden_even_for_super_admin_viewer(monkeypatch):
    """Final-review FIX 4: this call site is explicit scheduler-suppression
    (ghost_exclude_clause('u.id', viewer_id=None)), NOT the default-viewer
    read-surface behavior — so the exclusion clause is present regardless of
    what `_resolve_viewer()` would resolve to (even a ghost-visible
    super-admin id), since `viewer_id=None` is passed explicitly and
    `_resolve_viewer()` is never even consulted. A ghost must never be a
    "missing punch" subject, full stop; nobody (including L0) gets notified
    about it via this path. (Previously this relied on the default viewer
    resolution happening to return None because the cron has no request
    context — now it's explicit/defense-in-depth.)"""
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

    assert 'u.id <> ALL(%s)' in cap['sql']
    assert [999] in cap['args']


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


# ── send_monthly_pontaje_summary source-wiring ─────────────────────────────
# send_monthly_pontaje_summary iterates the previous month day-by-day through
# HolidayRepository().is_holiday(d) (real per-day DB round-trips) and its own
# get_daily_summary loop, so a full mocked call would mean re-implementing a
# calendar's worth of fakes. Its ghost drop is the exact same _drop_ghost_
# employees(employee_map, hidden_ghost_ids(None)) call already proven correct
# by the direct helper tests above and exercised end-to-end by the
# send_pontaje_digest CSV test; a source-wiring assertion (same standard as
# tests/hr/test_hr_employees_ghost.py's route-wiring check) confirms it's
# present at the right point. compute_hr_weekly_report_data, by contrast, gets
# a real BEHAVIORAL test below (its boundaries are cleanly patchable).

def _hr_attendance_source():
    path = pathlib.Path(__file__).resolve().parents[2] / 'tasks' / 'hr_attendance.py'
    return path.read_text()


def test_pontaje_digests_import_hidden_ghost_ids():
    src = _hr_attendance_source()
    assert 'from core.organization.ghost import hidden_ghost_ids' in src


def test_daily_and_monthly_digest_wire_ghost_drop():
    src = _hr_attendance_source()
    assert src.count('_drop_ghost_employees(employee_map, hidden_ghost_ids(None))') == 2


# ── compute_hr_weekly_report_data — behavioral: ghost fully absent from the ──
#    department aggregate (BOTH headcount AND CO used/remaining) ──────────────

_PRIMARY_CO_SQL_MARK = 'FROM primary_contracts'


def _patch_weekly_report_boundaries(monkeypatch, *, dept_rows, co_rows,
                                    leave_rows, used_by_company=None):
    """Patch every fetch boundary compute_hr_weekly_report_data touches so it
    runs purely on fabricated rows (no DB). Routes BaseRepository.query_all
    (shared by _base, sincron_repo, _company_repo) by SQL substring."""
    import core.base_repository as base_mod
    import hr.co_balance.repository as co_mod
    import core.connectors.biostar.repositories.biostar_repository as bio_mod
    import core.utils.work_calendar as cal_mod

    def fake_query_all(self, sql, params=None):
        if 'u.department' in sql:                       # dept_rows / headcount source
            return list(dept_rows)
        if 'company_name, count_for_leave' in sql:      # sincron leave-allowed set
            return list(leave_rows)
        return []                                       # aliases, companies, primary_contracts, etc.

    monkeypatch.setattr(base_mod.BaseRepository, 'query_all', fake_query_all)
    monkeypatch.setattr(co_mod.CoBalanceRepository, 'get_all_for_year',
                        lambda self, year: list(co_rows))
    monkeypatch.setattr(co_mod.CoBalanceRepository, 'get_used_ytd_by_user_company',
                        lambda self, year, **kw: dict(used_by_company or {}))
    monkeypatch.setattr(bio_mod.BioStarRepository, 'get_range_summary',
                        lambda self, s, e, jarvis_user_ids=None: [])
    monkeypatch.setattr(bio_mod.BioStarRepository, 'get_all_employees',
                        lambda self, active_only=True: [])
    monkeypatch.setattr(cal_mod, 'get_working_days_range', lambda s, e: 20)


def test_weekly_report_excludes_ghost_from_dept_aggregate(monkeypatch):
    from datetime import date
    from tasks.hr_attendance import compute_hr_weekly_report_data

    # One ghost (999) and one normal (7) user, both active in dept "Sales",
    # both with CO at company "ACME" (ghost has MORE remaining, so a leak
    # would be obvious in the totals).
    dept_rows = [
        {'id': 7, 'department': 'Sales', 'company': 'ACME'},
        {'id': 999, 'department': 'Sales', 'company': 'ACME'},
    ]
    co_rows = [
        {'user_id': 7, 'company_name': 'ACME', 'total_available': 20,
         'prenume': 'Norm', 'nume': 'User', 'departament': 'Sales'},
        {'user_id': 999, 'company_name': 'ACME', 'total_available': 30,
         'prenume': 'Ghost', 'nume': 'User', 'departament': 'Sales'},
    ]
    leave_rows = [
        {'mapped_jarvis_user_id': 7, 'company_name': 'ACME', 'count_for_leave': True},
        {'mapped_jarvis_user_id': 999, 'company_name': 'ACME', 'count_for_leave': True},
    ]
    _patch_weekly_report_boundaries(
        monkeypatch, dept_rows=dept_rows, co_rows=co_rows, leave_rows=leave_rows,
    )

    monkeypatch.setattr(ghost, 'get_ghost_user_ids', lambda: {999})
    monkeypatch.setattr(ghost, 'get_ghost_admin_ids', lambda: set())
    monkeypatch.setattr(ghost, '_resolve_viewer', lambda: None)
    ghost.invalidate_ghost_cache()

    result = compute_hr_weekly_report_data(reference_date=date(2026, 8, 20), period='ytd')

    # Department aggregate: ghost gone from BOTH headcount and CO totals.
    sales = [d for d in result['leave_by_department'] if d['department'] == 'Sales']
    assert len(sales) == 1
    assert sales[0]['headcount'] == 1, "ghost must not be counted in department headcount"
    assert sales[0]['co_remaining'] == 20.0, "only the non-ghost's 20 CO days remain (ghost's 30 excluded)"

    # Named CO roster in the digest body is ghost-free too.
    roster_names = {r['name'] for r in result['all_co_rows']}
    assert 'Norm User' in roster_names
    assert 'Ghost User' not in roster_names
    top_names = {r['name'] for r in result['top_10_co']}
    assert 'Ghost User' not in top_names


def test_weekly_report_wires_ghost_drop_source():
    """Belt-and-suspenders source check: the all_co drop and the dept-map
    drop both reuse the single hoisted _hidden_ghosts set (viewer=None)."""
    src = _hr_attendance_source()
    assert '_hidden_ghosts = hidden_ghost_ids(None)' in src
    assert "_drop_ghost_rows(all_co, _hidden_ghosts, key='user_id')" in src
    assert 'if dr[\'id\'] in _hidden_ghosts:' in src
