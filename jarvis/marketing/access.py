"""Shared project-scope access guard for marketing child routes.

`mkt_permission_required(entity, action)` only proves the caller holds the
permission with *some* scope ('own' | 'department' | 'all') and sets
`g.permission_scope`. It does NOT restrict *which* project the caller may touch.
Routes that act on a specific project must additionally call this guard to
enforce per-row scope — the same check projects.py applies on detail/update/
delete. (JAR-2234)
"""

from functools import wraps

from flask import g, jsonify
from flask_login import current_user

from marketing.repositories import ProjectRepository
from marketing.services.project_service import ProjectService

_project_repo = ProjectRepository()
_service = ProjectService()


def require_project_access(project_id, include_deleted=False):
    """Return an (response, status) error tuple if the caller may NOT access the
    project, or None when access is granted.

    Usage in a route:
        denied = require_project_access(project_id)
        if denied:
            return denied
    """
    project = _project_repo.get_by_id(project_id, include_deleted=include_deleted)
    if not project:
        return jsonify({'success': False, 'error': 'Project not found'}), 404
    scope = getattr(g, 'permission_scope', 'all')
    if not _service.can_access_project(project, current_user.id, scope,
                                       getattr(current_user, 'company', None)):
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    return None


def scoped_project(f):
    """Route decorator: enforce per-row project scope using the `project_id` URL
    kwarg. Place it BELOW @mkt_permission_required (innermost) so g.permission_scope
    is already set. No-op if the route has no `project_id` kwarg.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        project_id = kwargs.get('project_id')
        if project_id is not None:
            denied = require_project_access(project_id)
            if denied:
                return denied
        return f(*args, **kwargs)
    return wrapper
