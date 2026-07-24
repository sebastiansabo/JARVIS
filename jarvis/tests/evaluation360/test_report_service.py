"""Tests for ReportService — build, release/acknowledge, manager summary."""
from unittest.mock import MagicMock

import pytest

from hr.evaluation360.services.report_service import ReportService, ReportError


def _svc(cycle=None, participants=None, reviews=None, questions=None, report=None, report_owner=None):
    rr, resp, cr, tr, ev = (MagicMock() for _ in range(5))
    cr.get.return_value = cycle
    cr.list_participants.return_value = participants or []
    resp.submitted_for_subject.return_value = reviews or []
    tr.list_questions.return_value = questions or []
    rr.get_for_employee.return_value = report
    rr.get.return_value = report
    rr.get_with_owner.return_value = report_owner
    svc = ReportService(rr, resp, cr, tr, ev, reports_resolver=lambda uid: [10])  # manages emp 10
    return svc, rr, resp, cr, tr, ev


def test_build_reports_aggregates_and_upserts_per_participant():
    svc, rr, *_ = _svc(
        cycle={'id': 5, 'template_id': 1},
        participants=[{'id': 100, 'employee_id': 10}, {'id': 101, 'employee_id': 11}],
        questions=[{'competency_id': 1, 'competency_name': 'Comunicare'}],
        reviews=[{'relationship': 'manager', 'answers': [{'competency_id': 1, 'rating': 4, 'not_observed': False}]}])
    assert svc.build_reports(5) == 2
    assert rr.upsert.call_count == 2
    assert rr.upsert.call_args.kwargs['cycle_id'] == 5
    assert 'aggregates' in rr.upsert.call_args.kwargs


def test_build_reports_unknown_cycle():
    svc, *_ = _svc(cycle=None)
    with pytest.raises(ReportError) as e:
        svc.build_reports(999)
    assert e.value.status == 404


def test_my_report_gated_until_released():
    svc, *_ = _svc(report={'id': 1, 'released_at': None, 'employee_id': 10})
    with pytest.raises(ReportError) as e:
        svc.my_report(5, 10)
    assert e.value.status == 403


def test_my_report_returns_when_released():
    rep = {'id': 1, 'released_at': '2026-07-01', 'employee_id': 10, 'aggregates_by_relationship': {}}
    svc, *_ = _svc(report=rep)
    assert svc.my_report(5, 10) == rep


def test_acknowledge_ownership_enforced():
    svc, *_ = _svc(report_owner={'id': 1, 'employee_id': 99, 'released_at': '2026-07-01', 'cycle_id': 5})
    with pytest.raises(ReportError) as e:
        svc.acknowledge(1, employee_id=10)
    assert e.value.status == 403


def test_acknowledge_ok():
    svc, rr, *_ = _svc(report_owner={'id': 1, 'employee_id': 10, 'released_at': '2026-07-01', 'cycle_id': 5})
    assert svc.acknowledge(1, 10) is True
    rr.acknowledge.assert_called_once_with(1)


def test_manager_summary_rejects_short_text():
    svc, *_ = _svc(report_owner={'id': 1, 'employee_id': 10, 'cycle_id': 5})
    with pytest.raises(ReportError) as e:
        svc.set_manager_summary(1, manager_id=7, summary='too short')
    assert e.value.status == 400


def test_manager_summary_requires_direct_report():
    svc, *_ = _svc(report_owner={'id': 1, 'employee_id': 99, 'cycle_id': 5})  # not managed
    with pytest.raises(ReportError) as e:
        svc.set_manager_summary(1, manager_id=7, summary='x' * 400)
    assert e.value.status == 403


def test_manager_summary_ok():
    svc, rr, *_ = _svc(report_owner={'id': 1, 'employee_id': 10, 'cycle_id': 5})
    assert svc.set_manager_summary(1, manager_id=7, summary='x' * 400) is True
    rr.set_manager_summary.assert_called_once()


# ── Release gate (spec §5.4–5.5: summary 300–1500 + scheduled debrief) ────────

def _releasable(**over):
    rep = {'id': 1, 'cycle_id': 5, 'manager_summary': 'x' * 400,
           'debrief_scheduled_at': '2026-08-01T10:00:00'}
    rep.update(over)
    return rep


def test_release_rejects_missing_summary():
    svc, rr, *_ = _svc(report=_releasable(manager_summary=None))
    with pytest.raises(ReportError) as e:
        svc.release(1, actor_id=7)
    assert e.value.status == 422
    rr.release.assert_not_called()


def test_release_rejects_short_summary():
    svc, rr, *_ = _svc(report=_releasable(manager_summary='prea scurt'))
    with pytest.raises(ReportError) as e:
        svc.release(1, actor_id=7)
    assert e.value.status == 422
    rr.release.assert_not_called()


def test_release_rejects_without_debrief():
    svc, rr, *_ = _svc(report=_releasable(debrief_scheduled_at=None))
    with pytest.raises(ReportError) as e:
        svc.release(1, actor_id=7)
    assert e.value.status == 422
    rr.release.assert_not_called()


def test_release_succeeds_with_summary_and_debrief():
    svc, rr, resp, cr, tr, ev = _svc(report=_releasable())
    svc.release(1, actor_id=7)
    rr.release.assert_called_once_with(1)
    assert ev.emit.call_args.args[0] == 'report.released'


def test_schedule_debrief_emits_event():
    svc, rr, resp, cr, tr, ev = _svc(report_owner={'id': 1, 'employee_id': 10, 'cycle_id': 5})
    assert svc.schedule_debrief(1, manager_id=7, scheduled_at='2026-08-01T10:00:00') is True
    rr.schedule_debrief.assert_called_once()
    assert ev.emit.call_args.args[0] == 'debrief.scheduled'


def test_schedule_debrief_requires_direct_report():
    svc, *_ = _svc(report_owner={'id': 1, 'employee_id': 99, 'cycle_id': 5})  # not managed
    with pytest.raises(ReportError) as e:
        svc.schedule_debrief(1, manager_id=7, scheduled_at='2026-08-01')
    assert e.value.status == 403
