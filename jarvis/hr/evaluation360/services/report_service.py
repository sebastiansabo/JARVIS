"""Report building + lifecycle (spec §5.4–5.5, §7).

Aggregation runs server-side and stores only the anonymity-gated report;
employees see their report only once released; managers add a required summary
(300–1500 chars) for their direct reports; acknowledgment is owner-gated.
"""
from hr.evaluation360.domain import aggregation
from hr.evaluation360.repositories.report_repository import ReportRepository
from hr.evaluation360.repositories.response_repository import ResponseRepository
from hr.evaluation360.repositories.cycle_repository import CycleRepository
from hr.evaluation360.repositories.template_repository import EvalTemplateRepository
from hr.evaluation360.repositories.event_repository import EvalEventRepository

MIN_SUMMARY = 300
MAX_SUMMARY = 1500
GAP_FLAG = 1.0


class ReportError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _default_reports_of(user_id):
    try:
        from core.organization.manager_utils import get_managed_employee_ids
        return get_managed_employee_ids(user_id) or []
    except Exception:
        return []


class ReportService:
    def __init__(self, report_repo=None, response_repo=None, cycle_repo=None,
                 template_repo=None, event_repo=None, reports_resolver=None):
        self.reports = report_repo or ReportRepository()
        self.responses = response_repo or ResponseRepository()
        self.cycles = cycle_repo or CycleRepository()
        self.templates = template_repo or EvalTemplateRepository()
        self.events = event_repo or EvalEventRepository()
        self._reports_of = reports_resolver or _default_reports_of

    def _competencies(self, template_id):
        """Ordered distinct competencies from the template's questions + name map."""
        order, names = [], {}
        if not template_id:
            return order, names
        for q in self.templates.list_questions(template_id):
            cid = q.get('competency_id')
            if cid is not None and cid not in names:
                names[cid] = q.get('competency_name')
                order.append(cid)
        return order, names

    def build_reports(self, cycle_id):
        """Aggregate every participant's submitted reviews into a stored report."""
        cycle = self.cycles.get(cycle_id)
        if not cycle:
            raise ReportError('cycle not found', 404)
        competency_ids, names = self._competencies(cycle.get('template_id'))
        built = 0
        for p in self.cycles.list_participants(cycle_id):
            reviews = self.responses.submitted_for_subject(cycle_id, p['employee_id'])
            agg = aggregation.build_participant_report(reviews, competency_ids)
            for c in agg['competencies']:
                c['competency_name'] = names.get(c['competency_id'])
            flagged = [c['competency_id'] for c in agg['competencies']
                       if c['gap'] is not None and abs(c['gap']) >= GAP_FLAG]
            self.reports.upsert(
                cycle_id=cycle_id, participant_id=p['id'], aggregates=agg,
                gap_analysis={'flagged_competencies': flagged},
                hidden_categories=agg['hidden_relationships'])
            built += 1
        return built

    def my_reports(self, employee_id):
        """Headers of the employee's released reports."""
        return self.reports.list_for_employee(employee_id)

    def my_report(self, cycle_id, employee_id):
        rep = self.reports.get_for_employee(cycle_id, employee_id)
        if not rep:
            raise ReportError('no report', 404)
        if not rep.get('released_at'):
            raise ReportError('report not released yet', 403)
        return rep

    def release(self, report_id, actor_id):
        rep = self.reports.get(report_id)
        if not rep:
            raise ReportError('not found', 404)
        self.reports.release(report_id)
        self.events.emit('report.released', cycle_id=rep['cycle_id'], actor_id=actor_id,
                         payload={'report_id': report_id})
        return self.reports.get(report_id)

    def acknowledge(self, report_id, employee_id):
        rep = self.reports.get_with_owner(report_id)
        if not rep:
            raise ReportError('not found', 404)
        if rep['employee_id'] != employee_id:
            raise ReportError('not your report', 403)
        if not rep.get('released_at'):
            raise ReportError('report not released yet', 403)
        self.reports.acknowledge(report_id)
        self.events.emit('report.acknowledged', cycle_id=rep['cycle_id'], actor_id=employee_id,
                         payload={'report_id': report_id})
        return True

    def team_reports(self, manager_id):
        """Headers of the manager's direct-reports' reports (for calibration)."""
        return self.reports.list_for_manager(self._reports_of(manager_id))

    def manager_report(self, report_id, manager_id):
        """A direct report's full report (draft or released) for calibration."""
        rep = self.reports.get_with_owner(report_id)
        if not rep:
            raise ReportError('not found', 404)
        if rep['employee_id'] not in self._reports_of(manager_id):
            raise ReportError('not your direct report', 403)
        return rep

    def set_manager_summary(self, report_id, manager_id, summary):
        summary = (summary or '').strip()
        if not (MIN_SUMMARY <= len(summary) <= MAX_SUMMARY):
            raise ReportError(f'summary must be {MIN_SUMMARY}–{MAX_SUMMARY} characters (got {len(summary)})', 400)
        rep = self.reports.get_with_owner(report_id)
        if not rep:
            raise ReportError('not found', 404)
        if rep['employee_id'] not in self._reports_of(manager_id):
            raise ReportError('not a direct report of yours', 403)
        self.reports.set_manager_summary(report_id, summary)
        return True

    def status_list(self, cycle_id):
        """HR status view (flags only)."""
        return self.reports.list_for_cycle(cycle_id)
