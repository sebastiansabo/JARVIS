"""Marketing OKR routes — objectives and key results."""

import json as json_module
import logging
from flask import jsonify, request
from flask_login import login_required, current_user

from marketing import marketing_bp
from marketing.repositories import OkrRepository, ActivityRepository
from marketing.routes.projects import mkt_permission_required
from core.utils.api_helpers import get_json_or_error, safe_error_response
from database import get_db, get_cursor, release_db

logger = logging.getLogger('jarvis.marketing.routes.okr')

_okr_repo = OkrRepository()
_activity_repo = ActivityRepository()


# ---- Objectives ----

@marketing_bp.route('/api/projects/<int:project_id>/objectives', methods=['GET'])
@login_required
@mkt_permission_required('kpi', 'view')
def api_get_objectives(project_id):
    """Get all objectives with nested key results for a project."""
    objectives = _okr_repo.get_by_project(project_id)
    return jsonify({'objectives': objectives})


@marketing_bp.route('/api/projects/<int:project_id>/objectives', methods=['POST'])
@login_required
@mkt_permission_required('kpi', 'edit')
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
@mkt_permission_required('kpi', 'edit')
def api_suggest_key_results(project_id, objective_id):
    """Use AI to suggest key results for an objective based on its title and available KPIs."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        # 1. Get objective title
        cursor.execute('SELECT title FROM mkt_objectives WHERE id = %s AND project_id = %s',
                        (objective_id, project_id))
        obj_row = cursor.fetchone()
        if not obj_row:
            return jsonify({'success': False, 'error': 'Objective not found'}), 404
        obj_title = obj_row['title']

        # 2. Get project KPIs
        cursor.execute('''
            SELECT pk.id, kd.name, pk.current_value, pk.target_value, pk.unit
            FROM mkt_project_kpis pk
            JOIN mkt_kpi_definitions kd ON pk.kpi_definition_id = kd.id
            WHERE pk.project_id = %s
        ''', (project_id,))
        kpis = [dict(r) for r in cursor.fetchall()]
    finally:
        release_db(conn)

    # 3. Build prompt
    kpi_list = ''
    if kpis:
        kpi_lines = []
        for k in kpis:
            kpi_lines.append(
                f'- ID:{k["id"]} "{k["name"]}" '
                f'(current: {k["current_value"]}, target: {k["target_value"]}, unit: {k["unit"]})'
            )
        kpi_list = '\n\nAvailable project KPIs that can be linked:\n' + '\n'.join(kpi_lines)

    prompt = f'''Given this marketing objective: "{obj_title}"{kpi_list}

Suggest 3-5 measurable key results. For each provide:
- title: concise measurable outcome
- target_value: realistic target number
- unit: "number" or "currency" or "percentage"
- linked_kpi_id: ID from the KPI list above if one matches, else null

Return ONLY a JSON array:
[{{"title": "...", "target_value": 100, "unit": "number", "linked_kpi_id": null}}]'''

    try:
        from ai_agent.services.ai_agent_service import AIAgentService
        svc = AIAgentService()
        model_config = svc.model_config_repo.get_default()
        if not model_config:
            return jsonify({'success': False, 'error': 'No AI model configured'}), 503

        provider = svc.get_provider(model_config.provider.value)
        response = provider.generate(
            model_name=model_config.model_name,
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=1024,
            temperature=0.7,
            system='You are a marketing OKR assistant. Return ONLY valid JSON arrays.',
        )

        # Parse JSON
        text = response.content.strip()
        if '```' in text:
            text = text.split('```')[1].split('```')[0]
            if text.startswith('json'):
                text = text[4:]
        suggestions = json_module.loads(text.strip())
        if not isinstance(suggestions, list):
            suggestions = []

        # Validate
        valid_kpi_ids = {k['id'] for k in kpis}
        validated = []
        for s in suggestions[:5]:
            if not isinstance(s, dict) or not s.get('title'):
                continue
            kpi_id = s.get('linked_kpi_id')
            if kpi_id and kpi_id not in valid_kpi_ids:
                kpi_id = None
            validated.append({
                'title': str(s['title']),
                'target_value': float(s.get('target_value', 100)),
                'unit': s.get('unit', 'number') if s.get('unit') in ('number', 'currency', 'percentage') else 'number',
                'linked_kpi_id': kpi_id,
            })

        return jsonify({'suggestions': validated})
    except Exception as e:
        logger.warning(f'AI suggest KRs failed: {e}')
        return safe_error_response(e)


@marketing_bp.route('/api/projects/<int:project_id>/objectives/sync-kpis', methods=['POST'])
@login_required
@mkt_permission_required('kpi', 'edit')
def api_sync_okr_kpis(project_id):
    """Sync linked KPI values to key results."""
    try:
        count = _okr_repo.sync_linked_kpis(project_id)
        return jsonify({'success': True, 'synced': count})
    except Exception as e:
        return safe_error_response(e)
