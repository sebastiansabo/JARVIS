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
