"""Reviewer capture flow: inbox, form assembly, idempotent draft autosave, and
write-once submit — with ownership enforcement and event emission.

A reviewer may only touch their own assignments. Submitting is transactional and
immutable (the repo's SQL guards enforce write-once); a second submit or any
draft-after-submit is rejected. Raw responses are only ever returned to the
owning reviewer.
"""
from hr.evaluation360.repositories.response_repository import ResponseRepository
from hr.evaluation360.repositories.assignment_repository import AssignmentRepository
from hr.evaluation360.repositories.cycle_repository import CycleRepository
from hr.evaluation360.repositories.template_repository import EvalTemplateRepository
from hr.evaluation360.repositories.event_repository import EvalEventRepository


class ResponseError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class ResponseService:
    def __init__(self, response_repo=None, assignment_repo=None, cycle_repo=None,
                 template_repo=None, event_repo=None):
        self.responses = response_repo or ResponseRepository()
        self.assignments = assignment_repo or AssignmentRepository()
        self.cycles = cycle_repo or CycleRepository()
        self.templates = template_repo or EvalTemplateRepository()
        self.events = event_repo or EvalEventRepository()

    def _owned(self, assignment_id, reviewer_id):
        a = self.assignments.get(assignment_id)
        if not a:
            raise ResponseError('assignment not found', 404)
        if a.get('reviewer_id') != reviewer_id:
            raise ResponseError('not your assignment', 403)
        return a

    def my_assignments(self, reviewer_id):
        """The reviewer's to-do inbox."""
        return self.assignments.list_by_reviewer(reviewer_id)

    def get_form(self, assignment_id, reviewer_id):
        a = self._owned(assignment_id, reviewer_id)
        cycle = self.cycles.get(a['cycle_id'])
        questions = []
        if cycle and cycle.get('template_id'):
            questions = self.templates.list_questions(cycle['template_id'])
        resp = self.responses.get_by_assignment(assignment_id)
        return {
            'assignment': a,
            'questions': questions,
            'draft': (resp or {}).get('draft_payload') or {},
            'is_submitted': bool((resp or {}).get('is_submitted')),
        }

    def save_draft(self, assignment_id, reviewer_id, patch, device=None):
        """Idempotent per-question autosave. First save flips the assignment to
        in_progress and emits assignment.started."""
        a = self._owned(assignment_id, reviewer_id)
        row = self.responses.save_draft(assignment_id, patch, device)
        if row is None:
            raise ResponseError('response already submitted', 409)
        if a['status'] == 'invited':
            self.assignments.set_status(assignment_id, 'in_progress')
            self.events.emit('assignment.started', cycle_id=a['cycle_id'],
                             subject_id=a['subject_id'], assignment_id=assignment_id,
                             actor_id=reviewer_id, device=device)
        return row

    def submit(self, assignment_id, reviewer_id, answers, device=None):
        """Write the final answers once. Rejects a second submit (immutable)."""
        a = self._owned(assignment_id, reviewer_id)
        row = self.responses.submit(assignment_id, answers, device)
        if row is None:
            raise ResponseError('response already submitted', 409)
        self.assignments.set_status(assignment_id, 'submitted')
        self.events.emit('assignment.submitted', cycle_id=a['cycle_id'],
                         subject_id=a['subject_id'], assignment_id=assignment_id,
                         actor_id=reviewer_id, device=device,
                         payload={'answers': len(answers or [])})
        return row

    def self_decline(self, assignment_id, reviewer_id, reason):
        a = self._owned(assignment_id, reviewer_id)
        self.assignments.decline(assignment_id, reason)
        self.events.emit('assignment.declined', cycle_id=a['cycle_id'],
                         assignment_id=assignment_id, actor_id=reviewer_id,
                         payload={'reason': reason, 'self': True})
        return True
