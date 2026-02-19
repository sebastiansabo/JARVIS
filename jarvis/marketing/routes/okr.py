"""Marketing OKR routes — objectives and key results."""

import logging
from flask import jsonify, request
from flask_login import login_required, current_user

from marketing import marketing_bp
from marketing.repositories import OkrRepository, ActivityRepository
from marketing.routes.projects import mkt_permission_required
from core.utils.api_helpers import get_json_or_error, safe_error_response

logger = logging.getLogger('jarvis.marketing.routes.okr')

_okr_repo = OkrRepository()
_activity_repo = ActivityRepository()


# ---- Objectives ----

@marketing_bp.route('/api/projects/<int:project_id>/objectives', methods=['GET'])
@login_required
@mkt_permission_required('okr', 'view')
def api_get_objectives(project_id):
    """Get all objectives with nested key results for a project."""
    objectives = _okr_repo.get_by_project(project_id)
    return jsonify({'objectives': objectives})


@marketing_bp.route('/api/projects/<int:project_id>/objectives', methods=['POST'])
@login_required
@mkt_permission_required('okr', 'edit')
def api_create_objective(project_id):
    """Create a new objective."""
    data, error = get_json_or_error()
    if error:
        return error

    title = data.get('title', '').strip()
    if not title:
        return jsonify({'success': False, 'error': 'title is required'}), 400

    try:
        obj_id = _okr_repo.create_objective(
            project_id, title, current_user.id,
            description=data.get('description'),
            sort_order=data.get('sort_order', 0),
        )
        _activity_repo.log(project_id, 'okr_updated', actor_id=current_user.id,
                           details={'action': 'objective_created', 'objective_id': obj_id})
        return jsonify({'success': True, 'id': obj_id}), 201
    except Exception as e:
        return safe_error_response(e)


@marketing_bp.route('/api/objectives/<int:objective_id>', methods=['PUT'])
@login_required
@mkt_permission_required('okr', 'edit')
def api_update_objective(objective_id):
    """Update an objective."""
    data, error = get_json_or_error()
    if error:
        return error

    try:
        updated = _okr_repo.update_objective(objective_id, **data)
        if updated:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Objective not found'}), 404
    except Exception as e:
        return safe_error_response(e)


@marketing_bp.route('/api/objectives/<int:objective_id>', methods=['DELETE'])
@login_required
@mkt_permission_required('okr', 'edit')
def api_delete_objective(objective_id):
    """Delete an objective and its key results."""
    try:
        deleted = _okr_repo.delete_objective(objective_id)
        if deleted:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Objective not found'}), 404
    except Exception as e:
        return safe_error_response(e)


# ---- Key Results ----

@marketing_bp.route('/api/objectives/<int:objective_id>/key-results', methods=['POST'])
@login_required
@mkt_permission_required('okr', 'edit')
def api_create_key_result(objective_id):
    """Create a key result under an objective."""
    data, error = get_json_or_error()
    if error:
        return error

    title = data.get('title', '').strip()
    if not title:
        return jsonify({'success': False, 'error': 'title is required'}), 400

    try:
        kr_id = _okr_repo.create_key_result(
            objective_id, title,
            target_value=data.get('target_value', 100),
            unit=data.get('unit', 'number'),
            linked_kpi_id=data.get('linked_kpi_id'),
            sort_order=data.get('sort_order', 0),
        )
        return jsonify({'success': True, 'id': kr_id}), 201
    except Exception as e:
        return safe_error_response(e)


@marketing_bp.route('/api/key-results/<int:kr_id>', methods=['PUT'])
@login_required
@mkt_permission_required('okr', 'edit')
def api_update_key_result(kr_id):
    """Update a key result."""
    data, error = get_json_or_error()
    if error:
        return error

    try:
        updated = _okr_repo.update_key_result(kr_id, **data)
        if updated:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Key result not found'}), 404
    except Exception as e:
        return safe_error_response(e)


@marketing_bp.route('/api/key-results/<int:kr_id>', methods=['DELETE'])
@login_required
@mkt_permission_required('okr', 'edit')
def api_delete_key_result(kr_id):
    """Delete a key result."""
    try:
        deleted = _okr_repo.delete_key_result(kr_id)
        if deleted:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Key result not found'}), 404
    except Exception as e:
        return safe_error_response(e)


# ---- KPI Sync ----

@marketing_bp.route('/api/projects/<int:project_id>/objectives/<int:objective_id>/suggest-krs', methods=['POST'])
@login_required
@mkt_permission_required('okr', 'edit')
def api_suggest_key_results(project_id, objective_id):
    """Use AI to suggest key results for an objective based on its title and available KPIs."""
    from marketing.services.project_service import ProjectService

    result = ProjectService().suggest_key_results(project_id, objective_id)
    if result.success:
        return jsonify(result.data)
    return jsonify({'success': False, 'error': result.error}), result.status_code


@marketing_bp.route('/api/projects/<int:project_id>/objectives/sync-kpis', methods=['POST'])
@login_required
@mkt_permission_required('okr', 'edit')
def api_sync_okr_kpis(project_id):
    """Sync linked KPI values to key results."""
    try:
        count = _okr_repo.sync_linked_kpis(project_id)
        return jsonify({'success': True, 'synced': count})
    except Exception as e:
        return safe_error_response(e)
