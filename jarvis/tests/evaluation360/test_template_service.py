"""Tests for EvalTemplateService — competency validation, template CRUD, and the
fork-on-edit invariant (a published template is immutable; edits fork a draft)."""
from unittest.mock import MagicMock

import pytest

from hr.evaluation360.services.template_service import EvalTemplateService, TemplateError


def _svc(templates=None):
    repo, ev = MagicMock(), MagicMock()
    store = templates or {}
    repo.get_template.side_effect = lambda tid: store.get(tid)
    repo.list_questions.return_value = []
    return EvalTemplateService(repo=repo, event_repo=ev), repo, ev, store


def test_create_competency_requires_name():
    svc, repo, ev, _ = _svc()
    with pytest.raises(TemplateError):
        svc.create_competency({'name': '   '})
    repo.create_competency.assert_not_called()


def test_create_competency_ok_emits_event():
    svc, repo, ev, _ = _svc()
    repo.create_competency.return_value = {'id': 3, 'name': 'Comunicare'}
    out = svc.create_competency({'name': 'Comunicare', 'cluster': 'Core'}, actor_id=1)
    assert out['id'] == 3
    repo.create_competency.assert_called_once()
    assert ev.emit.called


def test_save_draft_template_edits_in_place():
    svc, repo, ev, _ = _svc(
        {1: {'id': 1, 'status': 'draft', 'name': 'T', 'competency_ids': [], 'rating_scale': {}}})
    res = svc.save_template(
        1, {'name': 'T2', 'questions': [{'competency_id': 5, 'type': 'rating'}]}, actor_id=1)
    repo.set_template_meta.assert_called_once()
    assert repo.set_template_meta.call_args.kwargs['name'] == 'T2'
    repo.replace_questions.assert_called_once_with(1, [{'competency_id': 5, 'type': 'rating'}])
    repo.create_template.assert_not_called()      # no fork for a draft
    assert res['forked'] is False


def test_save_published_template_forks_a_new_draft():
    store = {
        1: {'id': 1, 'status': 'published', 'name': 'T', 'competency_ids': [1], 'rating_scale': {}},
        2: {'id': 2, 'status': 'draft', 'name': 'T', 'competency_ids': [1], 'rating_scale': {}},
    }
    svc, repo, ev, _ = _svc(store)
    repo.max_version.return_value = 1
    repo.create_template.return_value = store[2]
    res = svc.save_template(1, {'name': 'T', 'questions': [{'competency_id': 1}]}, actor_id=1)
    assert repo.create_template.call_args.kwargs['version'] == 2
    assert repo.create_template.call_args.kwargs['forked_from_id'] == 1
    repo.copy_questions.assert_called_once_with(1, 2)   # questions carried to the fork
    repo.replace_questions.assert_called_once_with(2, [{'competency_id': 1}])  # edits hit the fork
    assert res['forked'] is True
    assert res['template']['id'] == 2


def test_archived_template_cannot_be_edited():
    svc, repo, ev, _ = _svc({1: {'id': 1, 'status': 'archived', 'name': 'T'}})
    with pytest.raises(TemplateError):
        svc.save_template(1, {'name': 'X'})


def test_publish_requires_at_least_one_question():
    svc, repo, ev, _ = _svc({1: {'id': 1, 'status': 'draft', 'name': 'T'}})
    repo.list_questions.return_value = []
    with pytest.raises(TemplateError):
        svc.publish_template(1)
    repo.set_template_status.assert_not_called()


def test_publish_sets_status_when_questions_present():
    svc, repo, ev, _ = _svc({1: {'id': 1, 'status': 'draft', 'name': 'T'}})
    repo.list_questions.return_value = [{'id': 9}]
    svc.publish_template(1, actor_id=1)
    repo.set_template_status.assert_called_once_with(1, 'published')


def test_question_for_competency_fans_text_across_audiences():
    q = EvalTemplateService.question_for_competency(7, 'Cât de bine comunică?')
    assert q['competency_id'] == 7 and q['type'] == 'rating' and q['required'] is True
    assert set(q['text_by_audience']) == {'self', 'manager', 'peer', 'direct_report'}
    assert q['text_by_audience']['peer'] == 'Cât de bine comunică?'
