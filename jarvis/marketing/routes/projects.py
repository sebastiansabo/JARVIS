"""Marketing project CRUD + status transitions + approval submission."""

import logging
from functools import wraps

from flask import jsonify, request, g
from flask_login import login_required, current_user

from marketing import marketing_bp
from marketing.repositories import (
    ProjectRepository, MemberRepository, BudgetRepository,
    ActivityRepository,
)
from marketing.services.project_service import ProjectService, UserContext
from core.roles.repositories import PermissionRepository
from core.utils.api_helpers import get_json_or_error, handle_api_errors

logger = logging.getLogger('jarvis.marketing.routes.projects')

_project_repo = ProjectRepository()
_member_repo = MemberRepository()
_budget_repo = BudgetRepository()
_activity_repo = ActivityRepository()
_perm_repo = PermissionRepository()
_service = ProjectService()


# ---- Permission decorator ----

def mkt_permission_required(entity, action):
    """Check marketing permissions_v2 with scope. Sets g.permission_scope."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({'success': False, 'error': 'Authentication required'}), 401
            role_id = getattr(current_user, 'role_id', None)
            if role_id:
                perm = _perm_repo.check_permission_v2(role_id, 'marketing', entity, action)
                if perm.get('has_permission'):
                    g.permission_scope = perm.get('scope', 'all')
                    return f(*args, **kwargs)
            return jsonify({'success': False, 'error': f'Permission denied: marketing.{entity}.{action}'}), 403
        return decorated
    return decorator


# ---- Projects CRUD ----

@marketing_bp.route('/api/projects', methods=['GET'])
@login_required
@mkt_permission_required('project', 'view')
def api_list_projects():
    """List projects with optional filters."""
    filters = {
        'status': request.args.get('status'),
        'company_id': request.args.get('company_id'),
        'brand_id': request.args.get('brand_id'),
        'owner_id': request.args.get('owner_id'),
        'project_type': request.args.get('project_type'),
        'date_from': request.args.get('date_from'),
        'date_to': request.args.get('date_to'),
        'search': request.args.get('search'),
        'limit': request.args.get('limit', 100),
        'offset': request.args.get('offset', 0),
    }
    # Strip None values
    filters = {k: v for k, v in filters.items() if v is not None}

    # Scope filtering — always include projects where user is approver/member
    scope = getattr(g, 'permission_scope', 'all')
    if scope == 'own':
        filters['visible_to_user_id'] = current_user.id
    elif scope == 'department':
        filters['visible_to_user_id'] = current_user.id
        filters['department_company_id'] = getattr(current_user, 'company', None)

    result = _project_repo.list_projects(filters)
    return jsonify(result)


@marketing_bp.route('/api/projects', methods=['POST'])
@login_required
@mkt_permission_required('project', 'create')
@handle_api_errors
def api_create_project():
    """Create a new marketing project."""
    data, error = get_json_or_error()
    if error:
        return error

    name = data.get('name')
    company_id = data.get('company_id')
    if not name or not company_id:
        return jsonify({'success': False, 'error': 'name and company_id are required'}), 400

    project_id = _project_repo.create(
        name=name,
        company_id=company_id,
        owner_id=data.get('owner_id', current_user.id),
        created_by=current_user.id,
        description=data.get('description'),
        company_ids=data.get('company_ids', []),
        brand_id=data.get('brand_id'),
        brand_ids=data.get('brand_ids', []),
        department_structure_id=data.get('department_structure_id'),
        department_ids=data.get('department_ids', []),
        project_type=data.get('project_type', 'campaign'),
        channel_mix=data.get('channel_mix', []),
        start_date=data.get('start_date'),
        end_date=data.get('end_date'),
        total_budget=data.get('total_budget', 0),
        currency=data.get('currency', 'RON'),
        objective=data.get('objective'),
        target_audience=data.get('target_audience'),
        brief=data.get('brief', {}),
        external_ref=data.get('external_ref'),
        metadata=data.get('metadata', {}),
    )
    # Add creator as owner member
    _member_repo.add(project_id, current_user.id, 'owner', current_user.id)
    # Log activity
    _activity_repo.log(project_id, 'created', actor_id=current_user.id, details={'name': name})
    return jsonify({'success': True, 'id': project_id}), 201


@marketing_bp.route('/api/projects/<int:project_id>', methods=['GET'])
@login_required
@mkt_permission_required('project', 'view')
def api_get_project(project_id):
    """Get project detail with budget lines, KPIs, members, recent activity."""
    project = _project_repo.get_by_id(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'}), 404

    scope = getattr(g, 'permission_scope', 'all')
    if not _service.can_access_project(project, current_user.id, scope,
                                       getattr(current_user, 'company', None)):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    project['members'] = _member_repo.get_by_project(project_id)
    project['budget_lines'] = _budget_repo.get_lines_by_project(project_id)
    project['activity'] = _activity_repo.get_by_project(project_id, limit=20)
    return jsonify(project)


@marketing_bp.route('/api/projects/<int:project_id>', methods=['PUT'])
@login_required
@mkt_permission_required('project', 'edit')
@handle_api_errors
def api_update_project(project_id):
    """Update project fields."""
    data, error = get_json_or_error()
    if error:
        return error

    project = _project_repo.get_by_id(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'}), 404

    scope = getattr(g, 'permission_scope', 'all')
    if not _service.can_access_project(project, current_user.id, scope,
                                       getattr(current_user, 'company', None)):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    updated = _project_repo.update(project_id, **data)
    if updated:
        _activity_repo.log(project_id, 'updated', actor_id=current_user.id,
                           details={'fields': list(data.keys())})
    return jsonify({'success': True})


@marketing_bp.route('/api/projects/<int:project_id>', methods=['DELETE'])
@login_required
@mkt_permission_required('project', 'delete')
def api_delete_project(project_id):
    """Soft delete a project (move to trash)."""
    project = _project_repo.get_by_id(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'}), 404

    scope = getattr(g, 'permission_scope', 'all')
    if not _service.can_access_project(project, current_user.id, scope,
                                       getattr(current_user, 'company', None)):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    if _project_repo.soft_delete(project_id):
        _activity_repo.log(project_id, 'deleted', actor_id=current_user.id)
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Delete failed'}), 500


@marketing_bp.route('/api/projects/<int:project_id>/archive', methods=['POST'])
@login_required
@mkt_permission_required('project', 'edit')
def api_archive_project(project_id):
    """Archive a project."""
    project = _project_repo.get_by_id(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'}), 404

    scope = getattr(g, 'permission_scope', 'all')
    if not _service.can_access_project(project, current_user.id, scope,
                                       getattr(current_user, 'company', None)):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    _project_repo.archive(project_id)
    _activity_repo.log(project_id, 'status_changed', actor_id=current_user.id,
                       details={'from': project['status'], 'to': 'archived'})
    return jsonify({'success': True})


@marketing_bp.route('/api/projects/<int:project_id>/restore', methods=['POST'])
@login_required
@mkt_permission_required('project', 'edit')
def api_restore_project(project_id):
    """Restore a project from archived or trash back to draft."""
    project = _project_repo.get_by_id(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'}), 404

    scope = getattr(g, 'permission_scope', 'all')
    if not _service.can_access_project(project, current_user.id, scope,
                                       getattr(current_user, 'company', None)):
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    if _project_repo.restore(project_id):
        _activity_repo.log(project_id, 'restored', actor_id=current_user.id)
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Restore failed'}), 500


@marketing_bp.route('/api/projects/archived', methods=['GET'])
@login_required
@mkt_permission_required('project', 'view')
def api_list_archived():
    """List archived projects."""
    limit = min(int(request.args.get('limit', 100)), 500)
    offset = int(request.args.get('offset', 0))
    projects = _project_repo.list_archived(limit, offset)
    return jsonify({'projects': projects, 'total': len(projects)})


@marketing_bp.route('/api/projects/trash', methods=['GET'])
@login_required
@mkt_permission_required('project', 'view')
def api_list_trash():
    """List soft-deleted projects (trash)."""
    limit = min(int(request.args.get('limit', 100)), 500)
    offset = int(request.args.get('offset', 0))
    projects = _project_repo.list_deleted(limit, offset)
    return jsonify({'projects': projects, 'total': len(projects)})


@marketing_bp.route('/api/projects/<int:project_id>/permanent', methods=['DELETE'])
@login_required
@mkt_permission_required('project', 'delete')
def api_permanent_delete_project(project_id):
    """Permanently delete a project from trash."""
    if _project_repo.permanent_delete(project_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Project not found or not in trash'}), 404


# ---- Status Transitions ----

@marketing_bp.route('/api/projects/<int:project_id>/submit-approval', methods=['POST'])
@login_required
@mkt_permission_required('project', 'approve')
@handle_api_errors
def api_submit_approval(project_id):
    """Submit project for approval via approval engine."""
    body = request.get_json(silent=True) or {}
    user = UserContext(user_id=current_user.id)
    result = _service.submit_approval(project_id, user, approver_id=body.get('approver_id'))
    if result.success:
        return jsonify(result.data)
    return jsonify({'success': False, 'error': result.error}), result.status_code


@marketing_bp.route('/api/projects/<int:project_id>/activate', methods=['POST'])
@login_required
@mkt_permission_required('project', 'edit')
def api_activate_project(project_id):
    """Move approved project to active."""
    project = _project_repo.get_by_id(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'}), 404
    if project['status'] != 'approved':
        return jsonify({'success': False, 'error': 'Project must be approved before activating'}), 400

    _project_repo.update_status(project_id, 'active')
    _activity_repo.log(project_id, 'status_changed', actor_id=current_user.id,
                       details={'from': 'approved', 'to': 'active'})
    return jsonify({'success': True})


@marketing_bp.route('/api/projects/<int:project_id>/pause', methods=['POST'])
@login_required
@mkt_permission_required('project', 'edit')
def api_pause_project(project_id):
    """Pause an active project."""
    project = _project_repo.get_by_id(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'}), 404
    if project['status'] != 'active':
        return jsonify({'success': False, 'error': 'Only active projects can be paused'}), 400

    _project_repo.update_status(project_id, 'paused')
    _activity_repo.log(project_id, 'status_changed', actor_id=current_user.id,
                       details={'from': 'active', 'to': 'paused'})
    return jsonify({'success': True})


@marketing_bp.route('/api/projects/<int:project_id>/complete', methods=['POST'])
@login_required
@mkt_permission_required('project', 'edit')
def api_complete_project(project_id):
    """Mark project as completed."""
    project = _project_repo.get_by_id(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'}), 404
    if project['status'] not in ('active', 'paused'):
        return jsonify({'success': False, 'error': 'Only active/paused projects can be completed'}), 400

    _project_repo.update_status(project_id, 'completed')
    _activity_repo.log(project_id, 'status_changed', actor_id=current_user.id,
                       details={'from': project['status'], 'to': 'completed'})
    return jsonify({'success': True})


@marketing_bp.route('/api/projects/<int:project_id>/duplicate', methods=['POST'])
@login_required
@mkt_permission_required('project', 'create')
@handle_api_errors
def api_duplicate_project(project_id):
    """Clone project as new draft."""
    data = request.get_json() or {}
    new_name = data.get('name')
    if not new_name:
        project = _project_repo.get_by_id(project_id)
        if not project:
            return jsonify({'success': False, 'error': 'Project not found'}), 404
        new_name = f"{project['name']} (Copy)"

    new_id = _project_repo.duplicate(project_id, new_name, current_user.id)
    if not new_id:
        return jsonify({'success': False, 'error': 'Original project not found'}), 404
    _member_repo.add(new_id, current_user.id, 'owner', current_user.id)
    _activity_repo.log(new_id, 'created', actor_id=current_user.id,
                       details={'duplicated_from': project_id})
    return jsonify({'success': True, 'id': new_id}), 201


# ---- Activity ----

@marketing_bp.route('/api/projects/<int:project_id>/activity', methods=['GET'])
@login_required
@mkt_permission_required('project', 'view')
def api_get_activity(project_id):
    """Paginated activity feed for a project."""
    limit = min(int(request.args.get('limit', 50)), 200)
    offset = int(request.args.get('offset', 0))
    activity = _activity_repo.get_by_project(project_id, limit=limit, offset=offset)
    return jsonify({'activity': activity})
