"""Contract tests for the reviewer capture flow (spec §2.3, §6.2)."""
from unittest.mock import MagicMock

import pytest

from hr.evaluation360.services.response_service import ResponseService, ResponseError

OWNED = {'id': 1, 'cycle_id': 5, 'subject_id': 10, 'reviewer_id': 7, 'status': 'invited'}


def _svc(assignment=None, draft_row=None, submit_row=None, response_row=None, cycle=None):
    rr, ar, cr, tr, ev = (MagicMock() for _ in range(5))
    ar.get.return_value = assignment
    rr.save_draft.return_value = draft_row
    rr.submit.return_value = submit_row
    rr.get_by_assignment.return_value = response_row
    cr.get.return_value = cycle
    tr.list_questions.return_value = []
    return ResponseService(rr, ar, cr, tr, ev), rr, ar, cr, tr, ev


def test_ownership_enforced():
    svc, *_ = _svc(assignment={'id': 1, 'reviewer_id': 99})
    with pytest.raises(ResponseError) as e:
        svc.get_form(1, reviewer_id=7)
    assert e.value.status == 403


def test_missing_assignment_is_404():
    svc, *_ = _svc(assignment=None)
    with pytest.raises(ResponseError) as e:
        svc.save_draft(1, 7, {'q1': 4})
    assert e.value.status == 404


def test_first_draft_starts_assignment_and_delegates_merge():
    svc, rr, ar, cr, tr, ev = _svc(assignment=dict(OWNED), draft_row={'draft_payload': {'q1': 4}})
    svc.save_draft(1, 7, {'q1': 4}, device='mobile')
    rr.save_draft.assert_called_once_with(1, {'q1': 4}, 'mobile')  # merge delegated to repo (idempotent SQL)
    ar.set_status.assert_called_once_with(1, 'in_progress')
    assert ev.emit.call_args[0][0] == 'assignment.started'


def test_draft_on_inprogress_does_not_restart():
    a = dict(OWNED, status='in_progress')
    svc, rr, ar, cr, tr, ev = _svc(assignment=a, draft_row={'draft_payload': {'q1': 5}})
    svc.save_draft(1, 7, {'q1': 5})
    ar.set_status.assert_not_called()
    ev.emit.assert_not_called()


def test_draft_after_submit_rejected():
    # repo returns None → the response is already submitted (immutable)
    svc, *_ = _svc(assignment=dict(OWNED), draft_row=None)
    with pytest.raises(ResponseError) as e:
        svc.save_draft(1, 7, {'q1': 4})
    assert e.value.status == 409


def test_submit_writes_once_and_sets_status():
    svc, rr, ar, cr, tr, ev = _svc(assignment=dict(OWNED), submit_row={'id': 1, 'is_submitted': True})
    svc.submit(1, 7, [{'question_id': 'q1', 'rating': 4}], device='web')
    rr.submit.assert_called_once()
    ar.set_status.assert_called_once_with(1, 'submitted')
    assert ev.emit.call_args[0][0] == 'assignment.submitted'


def test_second_submit_rejected_immutable():
    # repo returns None → already submitted; must not re-touch the assignment
    svc, rr, ar, *_ = _svc(assignment=dict(OWNED), submit_row=None)
    with pytest.raises(ResponseError) as e:
        svc.submit(1, 7, [])
    assert e.value.status == 409
    ar.set_status.assert_not_called()


def test_resume_returns_saved_draft():
    svc, *_ = _svc(
        assignment=dict(OWNED),
        response_row={'draft_payload': {'q1': 3}, 'is_submitted': False},
        cycle={'id': 5, 'template_id': None})
    form = svc.get_form(1, 7)
    assert form['draft'] == {'q1': 3}
    assert form['is_submitted'] is False


# ── Behavioral anchors (spec §6.2: anchor text before the scale) ─────────────

def test_list_questions_query_selects_level_descriptors():
    """The form query must join the competency's level_descriptors, otherwise the
    behavioral anchors never reach the reviewer (the original bug)."""
    from hr.evaluation360.repositories.template_repository import EvalTemplateRepository
    repo = EvalTemplateRepository()
    captured = {}

    def _cap(sql, params=None):
        captured['sql'] = sql
        return []

    repo.query_all = _cap
    repo.list_questions(1)
    assert 'level_descriptors' in captured['sql']


def test_get_form_forwards_anchor_descriptors():
    """get_form must surface the per-competency anchor payload to the client."""
    q = {'id': 1, 'competency_id': 2, 'competency_name': 'Comunicare', 'type': 'rating',
         'text_by_audience': {'peer': 'Cât de bine demonstrează: Comunicare?'},
         'competency_level_descriptors': {
             'ro': {'min_label': 'Rar', 'max_label': 'Constant',
                    'levels': ['n1', 'n2', 'n3', 'n4', 'n5']}}}
    svc, rr, ar, cr, tr, ev = _svc(assignment=dict(OWNED), cycle={'id': 5, 'template_id': 9})
    tr.list_questions.return_value = [q]
    form = svc.get_form(1, 7)
    anchors = form['questions'][0]['competency_level_descriptors']
    assert anchors['ro']['min_label'] == 'Rar'
    assert len(anchors['ro']['levels']) == 5
