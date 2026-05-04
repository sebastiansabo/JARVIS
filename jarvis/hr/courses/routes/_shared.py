"""Shared imports, blueprint reference, decorators for HR Courses routes."""

from datetime import date
from functools import wraps
from flask import request, jsonify, g
from flask_login import login_required, current_user
from .. import courses_bp
from core.utils.api_helpers import error_response, safe_error_response
from core.roles.decorators import v2_permission_required
from core.roles.repositories import PermissionRepository

check_permission_v2 = PermissionRepository().check_permission_v2


def courses_permission_required(action: str):
    """HR Courses V2 permission check. Sets g.permission_scope and g.user_context.

    Falls back to is_hr_manager for write operations.
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            g.user_context = {
                'user_id': current_user.id,
                'company': getattr(current_user, 'company', None),
                'department': getattr(current_user, 'department', None),
                'org_unit_id': getattr(current_user, 'org_unit_id', None)
            }

            role_id = getattr(current_user, 'role_id', None)
            if role_id:
                perm = check_permission_v2(role_id, 'hr', 'courses', action)
                if perm['has_permission']:
                    g.permission_scope = perm.get('scope', 'all')
                    return f(*args, **kwargs)

            # Fallback: is_hr_manager covers write ops
            if action in ('add', 'edit', 'delete') and getattr(current_user, 'is_hr_manager', False):
                g.permission_scope = 'all'
                return f(*args, **kwargs)

            # Fallback: can_access_hr covers view
            if action == 'view' and getattr(current_user, 'can_access_hr', False):
                g.permission_scope = 'all'
                return f(*args, **kwargs)

            return jsonify({'success': False, 'error': f'Permission denied: hr.courses.{action}'}), 403
        return decorated
    return decorator
