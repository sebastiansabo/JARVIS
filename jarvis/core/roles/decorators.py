"""Permission decorators for V2 role-based access control."""
from functools import wraps

from flask import jsonify, g
from flask_login import current_user


def v2_permission_required(module: str, entity: str, action: str):
    """Unified V2 permission decorator. Checks permissions_v2, sets g.permission_scope.

    Replaces the three identical module-specific decorators:
        mkt_permission_required (marketing/routes/projects.py)
        dms_permission_required (dms/routes/documents.py)
        hr_permission_required  (hr/events/routes.py)

    Usage:
        @v2_permission_required('marketing', 'project', 'create')
        def api_create_project():
            scope = g.permission_scope  # 'own' | 'department' | 'all'
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({'success': False, 'error': 'Authentication required'}), 401
            # Admin bypass — admins always get full scope
            if getattr(current_user, 'is_admin', False) or getattr(current_user, 'can_access_settings', False):
                g.permission_scope = 'all'
                return f(*args, **kwargs)
            role_id = getattr(current_user, 'role_id', None)
            if role_id:
                from core.roles.repositories import PermissionRepository
                perm = PermissionRepository().check_permission_v2(role_id, module, entity, action)
                if perm.get('has_permission'):
                    g.permission_scope = perm.get('scope', 'all')
                    return f(*args, **kwargs)
            return jsonify({'success': False, 'error': f'Permission denied: {module}.{entity}.{action}'}), 403
        return decorated
    return decorator
