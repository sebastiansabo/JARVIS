"""HR-admin API for the 360 module — status & orchestration only.

Every read here is aggregate/status; no endpoint returns individual response
content (spec §2.2). Reads require HR access; writes require HR-manager rights.
Responses use the platform's wrapped-envelope convention ({cycle: ...}).
"""
from flask import request, jsonify
from flask_login import current_user, login_required

from hr.events.routes._shared import hr_required, hr_manager_required
from hr.evaluation360 import eval360_bp
from hr.evaluation360.domain.state_machine import InvalidTransition
from hr.evaluation360.services.cycle_service import CycleService, CycleError
from hr.evaluation360.services.template_service import EvalTemplateService, TemplateError
from hr.evaluation360.services.nomination_service import NominationService
from hr.evaluation360.services.nudge_service import NudgeService, NudgeRateLimited
from hr.evaluation360.services.response_service import ResponseService, ResponseError
from hr.evaluation360.services.report_service import ReportService, ReportError
from hr.evaluation360.services.devplan_service import DevplanService, DevplanError


def _actor_id():
    return getattr(current_user, 'id', None)


@eval360_bp.route('/api/cycles', methods=['GET'])
@hr_required
def list_cycles():
    return jsonify({'cycles': CycleService().cycles.list()})


@eval360_bp.route('/api/cycles', methods=['POST'])
@hr_manager_required
def create_cycle():
    data = request.get_json() or {}
    if not data.get('name'):
        return jsonify({'error': 'name is required'}), 400
    cycle = CycleService().create_cycle(data, created_by=_actor_id())
    return jsonify({'cycle': cycle}), 201


@eval360_bp.route('/api/cycles/<int:cycle_id>', methods=['GET'])
@hr_required
def get_cycle(cycle_id):
    cycle = CycleService().cycles.get(cycle_id)
    if not cycle:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'cycle': cycle})


@eval360_bp.route('/api/cycles/<int:cycle_id>/transition', methods=['POST'])
@hr_manager_required
def transition_cycle(cycle_id):
    data = request.get_json() or {}
    target = data.get('target')
    if not target:
        return jsonify({'error': 'target state is required'}), 400
    try:
        cycle = CycleService().transition(
            cycle_id, target, actor_id=_actor_id(),
            waive_blocking=bool(data.get('waive_blocking')))
    except InvalidTransition as e:
        return jsonify({'error': str(e)}), 400
    except CycleError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'cycle': cycle})


@eval360_bp.route('/api/cycles/<int:cycle_id>/dry-run', methods=['GET'])
@hr_required
def dry_run(cycle_id):
    return jsonify({'dry_run': CycleService().dry_run(cycle_id)})


@eval360_bp.route('/api/cycles/<int:cycle_id>/progress', methods=['GET'])
@hr_required
def progress(cycle_id):
    return jsonify({'progress': CycleService().progress(cycle_id)})


@eval360_bp.route('/api/cycles/<int:cycle_id>/assignments', methods=['GET'])
@hr_required
def list_assignments(cycle_id):
    # Status only — assignments carry no response content.
    rows = CycleService().assignments.list_by_cycle(cycle_id)
    return jsonify({'assignments': rows})


@eval360_bp.route('/api/cycles/<int:cycle_id>/nominations', methods=['POST'])
@hr_manager_required
def fan_out_nominations(cycle_id):
    data = request.get_json() or {}
    subject_id = data.get('subject_id')
    if not subject_id:
        return jsonify({'error': 'subject_id is required'}), 400
    created = NominationService().fan_out(
        cycle_id, subject_id,
        peer_reviewer_ids=data.get('peer_reviewer_ids', []),
        due_at=data.get('due_at'), actor_id=_actor_id())
    return jsonify({'assignments': created}), 201


@eval360_bp.route('/api/cycles/<int:cycle_id>/auto-approve', methods=['POST'])
@hr_manager_required
def auto_approve(cycle_id):
    data = request.get_json() or {}
    n = NominationService().auto_approve_stale(
        cycle_id, hours=int(data.get('hours', 48)), actor_id=_actor_id())
    return jsonify({'auto_approved': n})


@eval360_bp.route('/api/assignments/<int:assignment_id>/decline', methods=['PATCH'])
@hr_manager_required
def decline_assignment(assignment_id):
    data = request.get_json() or {}
    replacement = NominationService().decline_and_replace(
        assignment_id, reason=data.get('reason', ''),
        replacement_reviewer_id=data.get('replacement_reviewer_id'),
        actor_id=_actor_id())
    return jsonify({'replacement': replacement})


@eval360_bp.route('/api/cycles/<int:cycle_id>/nudge', methods=['POST'])
@hr_manager_required
def nudge(cycle_id):
    data = request.get_json() or {}
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id is required'}), 400
    try:
        NudgeService().nudge(cycle_id, user_id, source=data.get('source', 'hr_manual'),
                             actor_id=_actor_id())
    except NudgeRateLimited as e:
        return jsonify({'error': str(e)}), 429
    return jsonify({'ok': True})


@eval360_bp.route('/api/cycles/<int:cycle_id>/generate-assignments', methods=['POST'])
@hr_manager_required
def generate_assignments(cycle_id):
    data = request.get_json() or {}
    summary = CycleService().generate_assignments(
        cycle_id, auto_peers=int(data.get('auto_peers', 4)),
        due_at=data.get('due_at'), actor_id=_actor_id())
    return jsonify({'generated': summary}), 201


# ── Population picker (cycle builder) ────────────────────────────────────────

@eval360_bp.route('/api/eligible-employees', methods=['GET'])
@hr_required
def eligible_employees():
    return jsonify({'employees': CycleService().cycles.list_eligible_employees(
        search=request.args.get('search'), department=request.args.get('department'))})


@eval360_bp.route('/api/departments', methods=['GET'])
@hr_required
def departments():
    return jsonify({'departments': CycleService().cycles.list_departments()})


@eval360_bp.route('/api/sincron-org', methods=['GET'])
@hr_required
def sincron_org_tree():
    # Sincron organigram as a population source (nodes + eligible-member counts).
    return jsonify({'nodes': CycleService().cycles.sincron_org_tree()})


@eval360_bp.route('/api/sincron-org/<int:node_id>/members', methods=['GET'])
@hr_required
def sincron_org_members(node_id):
    return jsonify({'employees': CycleService().cycles.sincron_org_node_members(node_id)})


# ── Competency library + form templates (HR authoring) ───────────────────────

@eval360_bp.route('/api/competencies', methods=['GET'])
@hr_required
def list_competencies():
    include = request.args.get('include_inactive') in ('1', 'true', 'yes')
    return jsonify({'competencies': EvalTemplateService().list_competencies(include_inactive=include)})


@eval360_bp.route('/api/competencies', methods=['POST'])
@hr_manager_required
def create_competency():
    try:
        comp = EvalTemplateService().create_competency(request.get_json() or {}, actor_id=_actor_id())
    except TemplateError as e:
        return jsonify({'error': str(e)}), e.status
    return jsonify({'competency': comp}), 201


@eval360_bp.route('/api/competencies/<int:cid>', methods=['PATCH'])
@hr_manager_required
def update_competency(cid):
    try:
        comp = EvalTemplateService().update_competency(cid, request.get_json() or {}, actor_id=_actor_id())
    except TemplateError as e:
        return jsonify({'error': str(e)}), e.status
    return jsonify({'competency': comp})


@eval360_bp.route('/api/templates', methods=['GET'])
@hr_required
def list_templates():
    include = request.args.get('include_archived') in ('1', 'true', 'yes')
    return jsonify({'templates': EvalTemplateService().list_templates(include_archived=include)})


@eval360_bp.route('/api/templates/<int:tid>', methods=['GET'])
@hr_required
def get_template(tid):
    try:
        return jsonify(EvalTemplateService().get_template(tid))
    except TemplateError as e:
        return jsonify({'error': str(e)}), e.status


@eval360_bp.route('/api/templates', methods=['POST'])
@hr_manager_required
def create_template():
    try:
        return jsonify(EvalTemplateService().create_template(request.get_json() or {}, actor_id=_actor_id())), 201
    except TemplateError as e:
        return jsonify({'error': str(e)}), e.status


@eval360_bp.route('/api/templates/<int:tid>', methods=['PATCH'])
@hr_manager_required
def save_template(tid):
    try:
        return jsonify(EvalTemplateService().save_template(tid, request.get_json() or {}, actor_id=_actor_id()))
    except TemplateError as e:
        return jsonify({'error': str(e)}), e.status


@eval360_bp.route('/api/templates/<int:tid>/publish', methods=['POST'])
@hr_manager_required
def publish_template(tid):
    try:
        return jsonify(EvalTemplateService().publish_template(tid, actor_id=_actor_id()))
    except TemplateError as e:
        return jsonify({'error': str(e)}), e.status


@eval360_bp.route('/api/templates/<int:tid>/fork', methods=['POST'])
@hr_manager_required
def fork_template(tid):
    try:
        return jsonify(EvalTemplateService().fork_template(tid, actor_id=_actor_id())), 201
    except TemplateError as e:
        return jsonify({'error': str(e)}), e.status


@eval360_bp.route('/api/templates/<int:tid>/archive', methods=['POST'])
@hr_manager_required
def archive_template(tid):
    try:
        return jsonify(EvalTemplateService().archive_template(tid, actor_id=_actor_id()))
    except TemplateError as e:
        return jsonify({'error': str(e)}), e.status


# ── Reviewer-facing capture (login + ownership; NOT HR-gated) ────────────────

@eval360_bp.route('/api/me/assignments', methods=['GET'])
@login_required
def my_assignments():
    return jsonify({'assignments': ResponseService().my_assignments(_actor_id())})


@eval360_bp.route('/api/assignments/<int:assignment_id>/form', methods=['GET'])
@login_required
def get_form(assignment_id):
    try:
        return jsonify(ResponseService().get_form(assignment_id, _actor_id()))
    except ResponseError as e:
        return jsonify({'error': str(e)}), e.status


@eval360_bp.route('/api/assignments/<int:assignment_id>/draft', methods=['PUT'])
@login_required
def save_draft(assignment_id):
    data = request.get_json() or {}
    # Accept a whole patch ({question_id: value, ...}) or a single {question_id, value}.
    patch = data.get('patch')
    if patch is None and 'question_id' in data:
        patch = {str(data['question_id']): data.get('value')}
    try:
        row = ResponseService().save_draft(
            assignment_id, _actor_id(), patch or {}, device=data.get('device'))
    except ResponseError as e:
        return jsonify({'error': str(e)}), e.status
    return jsonify({'draft': (row or {}).get('draft_payload') or {}})


@eval360_bp.route('/api/assignments/<int:assignment_id>/submit', methods=['POST'])
@login_required
def submit_response(assignment_id):
    data = request.get_json() or {}
    try:
        ResponseService().submit(
            assignment_id, _actor_id(), data.get('answers', []), device=data.get('device'))
    except ResponseError as e:
        return jsonify({'error': str(e)}), e.status
    return jsonify({'ok': True})


@eval360_bp.route('/api/assignments/<int:assignment_id>/self-decline', methods=['PATCH'])
@login_required
def self_decline(assignment_id):
    data = request.get_json() or {}
    try:
        ResponseService().self_decline(assignment_id, _actor_id(), data.get('reason', ''))
    except ResponseError as e:
        return jsonify({'error': str(e)}), e.status
    return jsonify({'ok': True})


# ── Reports (P4) ─────────────────────────────────────────────────────────────

@eval360_bp.route('/api/cycles/<int:cycle_id>/build-reports', methods=['POST'])
@hr_manager_required
def build_reports(cycle_id):
    try:
        built = ReportService().build_reports(cycle_id)
    except ReportError as e:
        return jsonify({'error': str(e)}), e.status
    return jsonify({'built': built})


@eval360_bp.route('/api/cycles/<int:cycle_id>/reports', methods=['GET'])
@hr_required
def report_status(cycle_id):
    # status flags only — never report content
    return jsonify({'reports': ReportService().status_list(cycle_id)})


@eval360_bp.route('/api/me/reports', methods=['GET'])
@login_required
def my_reports():
    return jsonify({'reports': ReportService().my_reports(_actor_id())})


@eval360_bp.route('/api/me/report/<int:cycle_id>', methods=['GET'])
@login_required
def my_report(cycle_id):
    try:
        return jsonify({'report': ReportService().my_report(cycle_id, _actor_id())})
    except ReportError as e:
        return jsonify({'error': str(e)}), e.status


@eval360_bp.route('/api/me/team-reports', methods=['GET'])
@login_required
def team_reports():
    return jsonify({'reports': ReportService().team_reports(_actor_id())})


@eval360_bp.route('/api/reports/<int:report_id>/manager-view', methods=['GET'])
@login_required
def manager_report(report_id):
    try:
        return jsonify({'report': ReportService().manager_report(report_id, _actor_id())})
    except ReportError as e:
        return jsonify({'error': str(e)}), e.status


@eval360_bp.route('/api/reports/<int:report_id>/release', methods=['POST'])
@hr_manager_required
def release_report(report_id):
    try:
        return jsonify({'report': ReportService().release(report_id, _actor_id())})
    except ReportError as e:
        return jsonify({'error': str(e)}), e.status


@eval360_bp.route('/api/reports/<int:report_id>/manager-release', methods=['POST'])
@login_required
def manager_release_report(report_id):
    # A manager releasing their own direct report's report (manager-gated policy).
    try:
        ReportService().manager_report(report_id, _actor_id())  # ownership check
        return jsonify({'report': ReportService().release(report_id, _actor_id())})
    except ReportError as e:
        return jsonify({'error': str(e)}), e.status


@eval360_bp.route('/api/reports/<int:report_id>/acknowledge', methods=['POST'])
@login_required
def acknowledge_report(report_id):
    try:
        ReportService().acknowledge(report_id, _actor_id())
    except ReportError as e:
        return jsonify({'error': str(e)}), e.status
    return jsonify({'ok': True})


@eval360_bp.route('/api/reports/<int:report_id>/manager-summary', methods=['POST'])
@login_required
def manager_summary(report_id):
    data = request.get_json() or {}
    try:
        ReportService().set_manager_summary(report_id, _actor_id(), data.get('summary', ''))
    except ReportError as e:
        return jsonify({'error': str(e)}), e.status
    return jsonify({'ok': True})


# ── Development plans + check-ins (P5, co-owned by employee + manager) ────────

@eval360_bp.route('/api/dev-plan/<int:cycle_id>/<int:employee_id>', methods=['GET'])
@login_required
def get_dev_plan(cycle_id, employee_id):
    try:
        return jsonify(DevplanService().get_plan(cycle_id, employee_id, _actor_id()))
    except DevplanError as e:
        return jsonify({'error': str(e)}), e.status


@eval360_bp.route('/api/dev-plan/<int:cycle_id>/<int:employee_id>', methods=['POST'])
@login_required
def save_dev_plan(cycle_id, employee_id):
    data = request.get_json() or {}
    try:
        plan = DevplanService().save_plan(
            cycle_id, employee_id, _actor_id(),
            data.get('goals', []), data.get('linked_competencies', []))
    except DevplanError as e:
        return jsonify({'error': str(e)}), e.status
    return jsonify({'plan': plan})


@eval360_bp.route('/api/dev-plans/<int:plan_id>/checkins', methods=['POST'])
@login_required
def add_checkin(plan_id):
    data = request.get_json() or {}
    try:
        ci = DevplanService().add_checkin(plan_id, _actor_id(), data.get('scheduled_date'), data.get('note'))
    except DevplanError as e:
        return jsonify({'error': str(e)}), e.status
    return jsonify({'checkin': ci}), 201


@eval360_bp.route('/api/checkins/<int:checkin_id>/complete', methods=['POST'])
@login_required
def complete_checkin(checkin_id):
    data = request.get_json() or {}
    try:
        DevplanService().complete_checkin(checkin_id, _actor_id(), data.get('note'))
    except DevplanError as e:
        return jsonify({'error': str(e)}), e.status
    return jsonify({'ok': True})
