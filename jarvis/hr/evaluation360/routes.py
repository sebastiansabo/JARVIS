"""HR-admin API for the 360 module — status & orchestration only.

Every read here is aggregate/status; no endpoint returns individual response
content (spec §2.2). Reads require HR access; writes require HR-manager rights.
Responses use the platform's wrapped-envelope convention ({cycle: ...}).
"""
from flask import request, jsonify
from flask_login import current_user

from hr.events.routes._shared import hr_required, hr_manager_required
from hr.evaluation360 import eval360_bp
from hr.evaluation360.domain.state_machine import InvalidTransition
from hr.evaluation360.services.cycle_service import CycleService, CycleError
from hr.evaluation360.services.nomination_service import NominationService
from hr.evaluation360.services.nudge_service import NudgeService, NudgeRateLimited


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
