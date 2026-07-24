"""Tests for DevplanService — plan CRUD, check-in completion, co-ownership."""
from unittest.mock import MagicMock

import pytest

from hr.evaluation360.services.devplan_service import DevplanService, DevplanError

PART = {'id': 100, 'cycle_id': 5, 'employee_id': 10}


def _svc(participant=None, existing_plan=None, checkin_owner=None, complete_row=None, manages=(10,)):
    dp, cr, ev = MagicMock(), MagicMock(), MagicMock()
    cr.get_participant.return_value = participant
    dp.get_for_participant.return_value = existing_plan
    dp.create.return_value = {'id': 50}
    dp.update.return_value = {'id': 50}
    dp.get_checkin_with_owner.return_value = checkin_owner
    dp.complete_checkin.return_value = complete_row
    dp.list_checkins.return_value = []
    svc = DevplanService(dp, cr, ev, reports_resolver=lambda uid: list(manages))
    return svc, dp, cr, ev


def test_save_plan_creates_and_emits_devplan_created():
    svc, dp, _, ev = _svc(participant=PART, existing_plan=None)
    svc.save_plan(5, 10, actor_id=10, goals=[{'text': 'x'}], linked_competencies=[1])
    dp.create.assert_called_once()
    assert ev.emit.call_args[0][0] == 'devplan.created'


def test_save_plan_updates_without_event():
    svc, dp, _, ev = _svc(participant=PART, existing_plan={'id': 50})
    svc.save_plan(5, 10, actor_id=10, goals=[], linked_competencies=[])
    dp.update.assert_called_once()
    ev.emit.assert_not_called()


def test_save_plan_ownership_enforced():
    svc, *_ = _svc(participant=PART, manages=())  # actor 7 manages nobody, isn't the employee
    with pytest.raises(DevplanError) as e:
        svc.save_plan(5, 10, actor_id=7, goals=[], linked_competencies=[])
    assert e.value.status == 403


def test_manager_may_edit_direct_report_plan():
    svc, dp, *_ = _svc(participant=PART, existing_plan=None, manages=(10,))
    svc.save_plan(5, 10, actor_id=7, goals=[{'text': 'g'}], linked_competencies=[])  # 7 manages 10
    dp.create.assert_called_once()


def test_complete_checkin_emits_and_completes():
    owner = {'id': 1, 'plan_id': 50, 'employee_id': 10, 'cycle_id': 5}
    svc, dp, _, ev = _svc(checkin_owner=owner, complete_row={'id': 1, 'completed_at': 'now'})
    svc.complete_checkin(1, actor_id=10, note='done')
    assert ev.emit.call_args[0][0] == 'devplan.checkin_completed'


def test_complete_checkin_already_completed_is_409():
    owner = {'id': 1, 'plan_id': 50, 'employee_id': 10, 'cycle_id': 5}
    svc, *_ = _svc(checkin_owner=owner, complete_row=None)  # repo None → already completed
    with pytest.raises(DevplanError) as e:
        svc.complete_checkin(1, actor_id=10)
    assert e.value.status == 409


def test_participant_cannot_edit_own_plan():
    # The subject is NOT a manager of anyone and isn't HR → editing is forbidden.
    svc, *_ = _svc(participant=PART, manages=())
    with pytest.raises(DevplanError) as e:
        svc.save_plan(5, 10, actor_id=10, goals=[{'text': 'x'}], linked_competencies=[])
    assert e.value.status == 403


def test_hr_may_edit_plan():
    # HR manages nobody but the actor_is_hr flag grants edit rights.
    svc, dp, *_ = _svc(participant=PART, existing_plan=None, manages=())
    svc.save_plan(5, 10, actor_id=99, goals=[{'text': 'g'}], linked_competencies=[], actor_is_hr=True)
    dp.create.assert_called_once()


def test_participant_may_view_own_plan_readonly():
    # Subject can read their own plan even though they can't edit it.
    svc, *_ = _svc(participant=PART, existing_plan={'id': 50, 'goals': []}, manages=())
    out = svc.get_plan(5, 10, actor_id=10)  # not a manager, not HR
    assert out['can_edit'] is False
    assert out['participant_id'] == 100
