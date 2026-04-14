"""Shared imports, singletons, helpers, and decorators for field_sales routes."""

import logging
import threading
from datetime import date, datetime
from functools import wraps

from flask import jsonify, request, g, current_app
from flask_login import current_user

from field_sales import field_sales_bp
from field_sales.repositories.visit_repository import VisitRepository
from field_sales.repositories.client_fs_repository import ClientFSRepository
from field_sales.services import ai_service, segmentation_service
from field_sales.notifications import (
    notify_visit_planned, notify_high_value_opportunity,
    notify_risk_flags, notify_high_renewal_score,
    notify_business_client_detected,
)
from core.roles.repositories import PermissionRepository

logger = logging.getLogger('jarvis.field_sales.routes')

_visit_repo = VisitRepository()
_client_repo = ClientFSRepository()
_perm_repo = PermissionRepository()


def _get_current_user():
    """Return the authenticated user from JWT (mobile) or Flask-Login (web)."""
    jwt_user = getattr(request, '_jwt_user', None)
    if jwt_user:
        return jwt_user
    if current_user and current_user.is_authenticated:
        return current_user
    return None


def jwt_or_login_required(f):
    """Accept either JWT Bearer token (mobile) or Flask-Login session (web)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Try JWT first (mobile app sends Authorization: Bearer ...)
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            from core.mobile.routes import _decode_token, _JWT_SECRET
            from core.auth.repositories import UserRepository
            from core.auth.models import User
            token = auth_header[7:]
            payload = _decode_token(token, _JWT_SECRET)
            if not payload or payload.get('type') != 'access':
                return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401
            _user_repo = UserRepository()
            user_data = _user_repo.get_by_id(payload['sub'])
            if not user_data or not user_data.get('is_active', True):
                return jsonify({'success': False, 'error': 'User not found or inactive'}), 401
            request._jwt_user = User(user_data)
            return f(*args, **kwargs)
        # Fall back to Flask-Login session
        if current_user and current_user.is_authenticated:
            return f(*args, **kwargs)
        return jsonify({'success': False, 'error': 'Authentication required'}), 401
    return decorated


ALLOWED_VISIT_TYPES = frozenset({
    'fleet_review', 'renewal_discussion', 'test_drive_followup',
    'service_followup', 'new_acquisition', 'contract_negotiation',
    'prospecting', 'general',
})
ALLOWED_OUTCOMES = frozenset({
    'completed', 'no_show', 'rescheduled', 'partial',
})


def _safe_error(e):
    """Return a safe error message, never leaking internals."""
    if isinstance(e, (ValueError, KeyError, TypeError)):
        return str(e)
    return 'An internal error occurred'


def _has_permission(module, entity, action):
    """Check if current user has a specific V2 permission. Returns False if no role_id."""
    user = _get_current_user()
    role_id = getattr(user, 'role_id', None) if user else None
    if not role_id:
        return False
    perm = _perm_repo.check_permission_v2(role_id, module, entity, action)
    return bool(perm.get('has_permission'))


def _is_manager():
    """Check if current user has field_sales.team.view permission."""
    return _has_permission('field_sales', 'team', 'view')


# ════════════════════════════════════════════════════════════════
# Permission decorators
# ════════════════════════════════════════════════════════════════

def field_sales_required(f):
    """Require field_sales.module.access V2 permission. Sets g.permission_scope."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = _get_current_user()
        if not user:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        role_id = getattr(user, 'role_id', None)
        if not role_id:
            return jsonify({'success': False, 'error': 'Field Sales access denied'}), 403
        perm = _perm_repo.check_permission_v2(role_id, 'field_sales', 'module', 'access')
        if not perm.get('has_permission'):
            return jsonify({'success': False, 'error': 'Field Sales access denied'}), 403
        g.permission_scope = perm.get('scope', 'all')
        return f(*args, **kwargs)
    return decorated


def field_sales_manager_required(f):
    """Require field_sales.team.view V2 permission for manager endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        user = _get_current_user()
        if not user:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        role_id = getattr(user, 'role_id', None)
        if not role_id:
            return jsonify({'success': False, 'error': 'Manager access denied'}), 403
        perm = _perm_repo.check_permission_v2(role_id, 'field_sales', 'team', 'view')
        if not perm.get('has_permission'):
            return jsonify({'success': False, 'error': 'Manager access denied'}), 403
        g.permission_scope = perm.get('scope', 'all')
        return f(*args, **kwargs)
    return decorated


def _require_fleet_permission():
    """Check field_sales.fleet.manage. Returns error response tuple or None."""
    if not _has_permission('field_sales', 'fleet', 'manage'):
        return jsonify({'success': False, 'error': 'Fleet management access denied'}), 403
    return None


# ════════════════════════════════════════════════════════════════
# Background task helper
# ════════════════════════════════════════════════════════════════

def _run_background(app, fn):
    """Run fn in a daemon thread with proper Flask app context."""
    def _wrapper():
        with app.app_context():
            try:
                fn()
            except Exception:
                logger.exception('Background task failed')
    threading.Thread(target=_wrapper, daemon=True).start()
