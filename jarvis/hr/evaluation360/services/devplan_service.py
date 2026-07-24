"""Development plans + check-ins (spec §5.5, §7.2, D-family indicators).

A plan is owned by the participant's manager and HR — either may edit goals and
complete check-ins. The participant may VIEW their own plan (read-only) but not
edit it. devplan.created (D3) fires on first creation;
devplan.checkin_completed (D4) on each completed check-in.
"""
import json

from hr.evaluation360.repositories.devplan_repository import DevplanRepository
from hr.evaluation360.repositories.cycle_repository import CycleRepository
from hr.evaluation360.repositories.event_repository import EvalEventRepository
from hr.evaluation360.repositories.report_repository import ReportRepository


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
    def __init__(self, devplan_repo=None, cycle_repo=None, event_repo=None,
                 report_repo=None, reports_resolver=None):
        self.plans = devplan_repo or DevplanRepository()
        self.cycles = cycle_repo or CycleRepository()
        self.events = event_repo or EvalEventRepository()
        self.reports = report_repo or ReportRepository()
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

    # ── plan generation (deterministic seed + optional AI draft) ─────────────
    def suggest_plan(self, cycle_id, employee_id, actor_id, mode='seed', actor_is_hr=False):
        """Propose (never save) a {synthesis, goals[]} draft from the employee's
        report. mode='ai' asks Claude and falls back to the deterministic seed on
        any failure; mode='seed' is fully offline."""
        if not self._can_edit(employee_id, actor_id, actor_is_hr):
            raise DevplanError('not allowed', 403)
        report = self.reports.get_for_employee(cycle_id, employee_id) or {}
        comps = (report.get('aggregates_by_relationship') or {}).get('competencies') or []
        if mode == 'ai':
            try:
                return self._ai_suggestion(comps, report)
            except Exception:
                pass  # graceful fallback — never block the manager on an AI outage
        return self._seed_suggestion(comps)

    @staticmethod
    def _development_priority(c):
        """Rank a competency as a development need: biggest blind spot (self−others)
        first, else lowest 'others' score."""
        gap = c.get('gap')
        return (gap if gap is not None else -999, -(c.get('others') or 0))

    def _seed_suggestion(self, comps):
        scored = [c for c in comps if c.get('others') is not None]
        if not scored:
            return {'synthesis': '', 'goals': []}
        top = max(scored, key=self._development_priority)
        name = top.get('competency_name') or 'această competență'
        return {'synthesis': '', 'goals': [{
            'competency_id': top.get('competency_id'),
            'title': f'Dezvoltă: {name}',
            'description': f'Alege 1–2 acțiuni concrete pentru {name} și stabilește un termen.',
            'target_date': None,
        }]}

    def _ai_suggestion(self, comps, report):
        import ai_agent.services.llm_client as llm_client  # lazy: keeps the AI stack off the import path
        lines = [
            f"- {c.get('competency_name')}: autoevaluare {c.get('self')}, ceilalți {c.get('others')}, diferență {c.get('gap')}"
            for c in comps if c.get('others') is not None
        ]
        prompt = (
            "Ești coach de dezvoltare profesională. Pe baza rezultatelor 360 de mai jos, "
            "propune un plan de dezvoltare. Prioritizează competențele cu cea mai mare diferență "
            "pozitivă (autoevaluare > ceilalți = punct orb) sau cel mai scăzut scor 'ceilalți'.\n\n"
            f"Competențe:\n{chr(10).join(lines)}\n\n"
            f"Sinteza managerului: {report.get('manager_summary') or '—'}\n\n"
            "Răspunde DOAR cu JSON valid: "
            '{"synthesis":"1-2 fraze","goals":[{"competency":"nume","title":"obiectiv scurt",'
            '"description":"1-2 fraze concrete","target_date":null}]}. Maxim 3 obiective, în română.'
        )
        raw = llm_client.ask(prompt, system="Răspunzi exclusiv cu JSON valid.", max_tokens=1200)
        data = json.loads(self._extract_json(raw))
        by_name = {(c.get('competency_name') or '').strip().lower(): c.get('competency_id') for c in comps}
        goals = [{
            'competency_id': by_name.get((g.get('competency') or '').strip().lower()),
            'title': (g.get('title') or '').strip(),
            'description': (g.get('description') or '').strip(),
            'target_date': g.get('target_date'),
        } for g in (data.get('goals') or [])[:3] if (g.get('title') or '').strip()]
        return {'synthesis': (data.get('synthesis') or '').strip(), 'goals': goals}

    @staticmethod
    def _extract_json(raw):
        s = (raw or '').strip()
        start, end = s.find('{'), s.rfind('}')
        return s[start:end + 1] if start != -1 and end != -1 else s

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
