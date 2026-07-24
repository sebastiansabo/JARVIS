"""Development plans + check-ins (spec §5.5, §7.2, D-family indicators).

A plan is owned by the participant's manager and HR — either may edit goals and
complete check-ins. The participant may VIEW their own plan (read-only) but not
edit it. devplan.created (D3) fires on first creation;
devplan.checkin_completed (D4) on each completed check-in.
"""
from hr.evaluation360.repositories.devplan_repository import DevplanRepository
from hr.evaluation360.repositories.cycle_repository import CycleRepository
from hr.evaluation360.repositories.event_repository import EvalEventRepository


class DevplanError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _default_reports_of(user_id):
    try:
        from core.organization.manager_utils import get_managed_employee_ids
        return get_managed_employee_ids(user_id) or []
    except Exception:
        return []


class DevplanService:
    def __init__(self, devplan_repo=None, cycle_repo=None, event_repo=None, reports_resolver=None):
        self.plans = devplan_repo or DevplanRepository()
        self.cycles = cycle_repo or CycleRepository()
        self.events = event_repo or EvalEventRepository()
        self._reports_of = reports_resolver or _default_reports_of

    def _can_edit(self, employee_id, actor_id, actor_is_hr=False):
        # You never author your OWN plan — a manager (of this employee) or HR does.
        # The improvement plan is proposed by the person above you in the hierarchy.
        if actor_id == employee_id:
            return False
        return bool(actor_is_hr) or employee_id in self._reports_of(actor_id)

    def _can_view(self, employee_id, actor_id, actor_is_hr=False):
        # The participant may read their own plan; managers and HR may read too.
        return actor_id == employee_id or self._can_edit(employee_id, actor_id, actor_is_hr)

    def _participant(self, cycle_id, employee_id):
        p = self.cycles.get_participant(cycle_id, employee_id)
        if not p:
            raise DevplanError('not a participant of this cycle', 404)
        return p

    def get_plan(self, cycle_id, employee_id, actor_id, actor_is_hr=False):
        if not self._can_view(employee_id, actor_id, actor_is_hr):
            raise DevplanError('not allowed', 403)
        participant = self._participant(cycle_id, employee_id)
        plan = self.plans.get_for_participant(participant['id'])
        can_edit = self._can_edit(employee_id, actor_id, actor_is_hr)
        # A draft plan is invisible to the employee — only the manager/HR author
        # sees it until it is finalized (spec: "angajatul nu vede până la finalizare").
        if plan and not can_edit and plan.get('status') != 'finalized':
            plan = None
        checkins = self.plans.list_checkins(plan['id']) if plan else []
        return {'participant_id': participant['id'], 'plan': plan, 'checkins': checkins,
                'can_edit': can_edit}

    def save_plan(self, cycle_id, employee_id, actor_id, goals, linked_competencies, actor_is_hr=False):
        """Save/update the plan as a DRAFT — no devplan.created event yet (that
        fires on finalize). Keeps a finalized plan's status if edited later."""
        if not self._can_edit(employee_id, actor_id, actor_is_hr):
            raise DevplanError('not allowed', 403)
        participant = self._participant(cycle_id, employee_id)
        existing = self.plans.get_for_participant(participant['id'])
        if existing:
            return self.plans.update(existing['id'], goals=goals, linked_competencies=linked_competencies)
        return self.plans.create(participant_id=participant['id'], goals=goals,
                                 linked_competencies=linked_competencies, status='draft')

    def finalize_plan(self, cycle_id, employee_id, actor_id, actor_is_hr=False):
        """Publish the plan to the employee. Requires >= 1 goal; emits devplan.created
        (indicator D3) once, on the transition to finalized."""
        if not self._can_edit(employee_id, actor_id, actor_is_hr):
            raise DevplanError('not allowed', 403)
        participant = self._participant(cycle_id, employee_id)
        plan = self.plans.get_for_participant(participant['id'])
        if not plan or not (plan.get('goals') or []):
            raise DevplanError('planul are nevoie de cel puțin un obiectiv', 400)
        already_final = plan.get('status') == 'finalized'
        updated = self.plans.set_status(plan['id'], 'finalized')
        if not already_final:
            self.events.emit('devplan.created', cycle_id=cycle_id, subject_id=employee_id,
                             actor_id=actor_id, payload={'goals': len(plan.get('goals') or [])})
        return updated

    def add_checkin(self, plan_id, actor_id, scheduled_date, note=None, actor_is_hr=False):
        plan = self.plans.get_with_owner(plan_id)
        if not plan:
            raise DevplanError('plan not found', 404)
        if not self._can_edit(plan['employee_id'], actor_id, actor_is_hr):
            raise DevplanError('not allowed', 403)
        return self.plans.add_checkin(plan_id, scheduled_date, note)

    def complete_checkin(self, checkin_id, actor_id, note=None, actor_is_hr=False):
        ci = self.plans.get_checkin_with_owner(checkin_id)
        if not ci:
            raise DevplanError('check-in not found', 404)
        if not self._can_edit(ci['employee_id'], actor_id, actor_is_hr):
            raise DevplanError('not allowed', 403)
        row = self.plans.complete_checkin(checkin_id, note)
        if row is None:
            raise DevplanError('check-in already completed', 409)
        self.events.emit('devplan.checkin_completed', cycle_id=ci['cycle_id'],
                         subject_id=ci['employee_id'], actor_id=actor_id,
                         payload={'checkin_id': checkin_id})
        return row
