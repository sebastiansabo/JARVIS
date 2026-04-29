"""Field Sales task routes — CRUD for visit tasks and follow-ups."""

from ._shared import *  # noqa: F401, F403


@field_sales_bp.route('/api/field-sales/visits/<int:visit_id>/tasks', methods=['GET'])
@jwt_or_login_required
@field_sales_required
def api_visit_tasks(visit_id):
    """List tasks for a visit."""
    try:
        visit = _visit_repo.get_by_id(visit_id)
        if not visit:
            return jsonify({'success': False, 'error': 'Visit not found'}), 404

        if visit['kam_id'] != _get_current_user().id and not _is_manager():
            return jsonify({'success': False, 'error': 'Access denied'}), 403

        tasks = _visit_repo.get_tasks_for_visit(visit_id)
        return jsonify({'success': True, 'tasks': tasks})
    except Exception as e:
        logger.exception('Error fetching tasks for visit %s', visit_id)
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/visits/<int:visit_id>/tasks', methods=['POST'])
@jwt_or_login_required
@field_sales_required
def api_create_task(visit_id):
    """Create a task for a visit."""
    try:
        visit = _visit_repo.get_by_id(visit_id)
        if not visit:
            return jsonify({'success': False, 'error': 'Visit not found'}), 404

        if visit['kam_id'] != _get_current_user().id and not _is_manager():
            return jsonify({'success': False, 'error': 'Access denied'}), 403

        data = request.get_json(silent=True) or {}
        description = (data.get('description') or '').strip()
        if not description:
            return jsonify({'success': False, 'error': 'description is required'}), 400

        due_date = data.get('due_date')
        if due_date:
            try:
                datetime.strptime(due_date, '%Y-%m-%d')
            except ValueError:
                return jsonify({'success': False, 'error': 'Invalid due_date format. Use YYYY-MM-DD'}), 400

        assigned_to = data.get('assigned_to')
        if assigned_to:
            try:
                assigned_to = int(assigned_to)
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': 'assigned_to must be an integer'}), 400

        current_uid = _get_current_user().id
        task = _visit_repo.create_task({
            'visit_id': visit_id,
            'description': description,
            'assigned_to': assigned_to or current_uid,
            'due_date': due_date,
            'created_by': current_uid,
        })

        return jsonify({'success': True, 'task': task}), 201
    except Exception as e:
        logger.exception('Error creating task')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/tasks/<int:task_id>', methods=['PUT'])
@jwt_or_login_required
@field_sales_required
def api_update_task(task_id):
    """Update a task (status, description, due_date, assigned_to)."""
    try:
        task = _visit_repo.get_task_by_id(task_id)
        if not task:
            return jsonify({'success': False, 'error': 'Task not found'}), 404

        # Check access via visit
        visit = _visit_repo.get_by_id(task['visit_id'])
        if not visit:
            return jsonify({'success': False, 'error': 'Visit not found'}), 404
        if visit['kam_id'] != _get_current_user().id and not _is_manager():
            return jsonify({'success': False, 'error': 'Access denied'}), 403

        data = request.get_json(silent=True) or {}
        update = {}

        if 'description' in data:
            desc = (data['description'] or '').strip()
            if not desc:
                return jsonify({'success': False, 'error': 'description cannot be empty'}), 400
            update['description'] = desc

        if 'status' in data:
            allowed = {'pending', 'in_progress', 'completed', 'cancelled'}
            if data['status'] not in allowed:
                return jsonify({'success': False, 'error': f'Invalid status. Allowed: {", ".join(sorted(allowed))}'}), 400
            update['status'] = data['status']

        if 'due_date' in data:
            if data['due_date']:
                try:
                    datetime.strptime(data['due_date'], '%Y-%m-%d')
                except ValueError:
                    return jsonify({'success': False, 'error': 'Invalid due_date format'}), 400
            update['due_date'] = data['due_date'] or None

        if 'assigned_to' in data:
            update['assigned_to'] = int(data['assigned_to']) if data['assigned_to'] else None

        if not update:
            return jsonify({'success': False, 'error': 'No fields to update'}), 400

        updated = _visit_repo.update_task(task_id, update)
        return jsonify({'success': True, 'task': updated})
    except Exception as e:
        logger.exception('Error updating task %s', task_id)
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/tasks/<int:task_id>/follow-ups', methods=['GET'])
@jwt_or_login_required
@field_sales_required
def api_task_follow_ups(task_id):
    """Get follow-up log for a task."""
    try:
        task = _visit_repo.get_task_by_id(task_id)
        if not task:
            return jsonify({'success': False, 'error': 'Task not found'}), 404

        follow_ups = _visit_repo.get_follow_ups(task_id)
        return jsonify({'success': True, 'follow_ups': follow_ups})
    except Exception as e:
        logger.exception('Error fetching follow-ups for task %s', task_id)
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/tasks/<int:task_id>/follow-ups', methods=['POST'])
@jwt_or_login_required
@field_sales_required
def api_create_follow_up(task_id):
    """Add a follow-up note to a task."""
    try:
        task = _visit_repo.get_task_by_id(task_id)
        if not task:
            return jsonify({'success': False, 'error': 'Task not found'}), 404

        data = request.get_json(silent=True) or {}
        note = (data.get('note') or '').strip()
        if not note:
            return jsonify({'success': False, 'error': 'note is required'}), 400

        current_uid = _get_current_user().id
        follow_up = _visit_repo.add_follow_up(task_id, note, current_uid)
        return jsonify({'success': True, 'follow_up': follow_up}), 201
    except Exception as e:
        logger.exception('Error creating follow-up for task %s', task_id)
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/tasks/pending', methods=['GET'])
@jwt_or_login_required
@field_sales_required
def api_pending_tasks():
    """Get all pending tasks for the current user."""
    try:
        current_uid = _get_current_user().id
        tasks = _visit_repo.get_pending_tasks(current_uid)
        return jsonify({'success': True, 'tasks': tasks})
    except Exception as e:
        logger.exception('Error fetching pending tasks')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500
