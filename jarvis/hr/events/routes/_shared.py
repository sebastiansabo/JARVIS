"""Shared imports, blueprint reference, decorators, and helpers for HR Events routes."""

__all__ = [
    # stdlib / flask
    'date', 'wraps',
    'render_template', 'request', 'jsonify', 'redirect', 'url_for', 'flash',
    'g', 'current_app', 'login_required', 'current_user',
    # app imports
    'events_bp', 'can_edit_bonus', 'get_lock_status',
    'error_response', 'handle_api_errors',
    'v2_permission_required', 'PermissionRepository', 'check_permission_v2',
    # database functions
    'get_all_hr_employees', 'get_hr_employee', 'save_hr_employee',
    'update_hr_employee', 'delete_hr_employee', 'search_hr_employees',
    'get_all_hr_events', 'get_hr_event', 'save_hr_event', 'update_hr_event',
    'delete_hr_event', 'delete_hr_events_bulk',
    'get_all_event_bonuses', 'get_event_bonus', 'save_event_bonus',
    'save_event_bonuses_bulk', 'update_event_bonus', 'delete_event_bonus',
    'delete_event_bonuses_bulk', 'delete_event_bonuses_by_employee',
    'delete_event_bonuses_by_event',
    'get_event_bonuses_summary', 'get_bonuses_by_month',
    'get_bonuses_by_employee', 'get_bonuses_by_event',
    'get_all_bonus_types', 'get_bonus_type', 'save_bonus_type',
    'update_bonus_type', 'delete_bonus_type',
    'can_access_bonus', 'can_access_employee',
    'get_all_companies_with_brands', 'create_company', 'update_company', 'delete_company',
    'get_all_company_brands', 'create_company_brand', 'update_company_brand', 'delete_company_brand',
    'get_all_department_structures', 'create_department_structure',
    'update_department_structure', 'delete_department_structure', 'get_name_by_id',
    'get_all_master_brands', 'create_master_brand', 'update_master_brand', 'delete_master_brand',
    'get_all_master_departments', 'create_master_department',
    'update_master_department', 'delete_master_department',
    'get_all_master_subdepartments', 'create_master_subdepartment',
    'update_master_subdepartment', 'delete_master_subdepartment',
    'get_managed_employee_ids', 'is_manager',
    # models
    'get_companies', 'get_brands_for_company', 'get_departments_for_company',
    'clear_structure_cache',
    # decorators & helpers
    'hr_required', 'hr_manager_required', 'hr_permission_required',
    'MONTH_NAMES',
    '_compute_bonus_net', 'resolve_presence_days', 'check_presence_months_editable',
]

from datetime import date
from functools import wraps
from flask import render_template, request, jsonify, redirect, url_for, flash, g, current_app
from flask_login import login_required, current_user
from .. import events_bp
from ..utils import can_edit_bonus, get_lock_status
from core.utils.api_helpers import error_response, handle_api_errors
from core.roles.decorators import v2_permission_required
from core.roles.repositories import PermissionRepository
check_permission_v2 = PermissionRepository().check_permission_v2
from ..database import (
    get_all_hr_employees, get_hr_employee, save_hr_employee,
    update_hr_employee, delete_hr_employee, search_hr_employees,
    get_all_hr_events, get_hr_event, save_hr_event, update_hr_event, delete_hr_event, delete_hr_events_bulk,
    get_all_event_bonuses, get_event_bonus, save_event_bonus,
    save_event_bonuses_bulk, update_event_bonus, delete_event_bonus, delete_event_bonuses_bulk,
    delete_event_bonuses_by_employee, delete_event_bonuses_by_event,
    get_event_bonuses_summary, get_bonuses_by_month, get_bonuses_by_employee, get_bonuses_by_event,
    get_all_bonus_types, get_bonus_type, save_bonus_type, update_bonus_type, delete_bonus_type,
    # Scope access helpers
    can_access_bonus, can_access_employee,
    # Company CRUD
    get_all_companies_with_brands, create_company, update_company, delete_company,
    # Company Brands CRUD
    get_all_company_brands, create_company_brand, update_company_brand, delete_company_brand,
    # Department Structure CRUD
    get_all_department_structures, create_department_structure, update_department_structure,
    delete_department_structure, get_name_by_id,
    # Master tables CRUD
    get_all_master_brands, create_master_brand, update_master_brand, delete_master_brand,
    get_all_master_departments, create_master_department, update_master_department, delete_master_department,
    get_all_master_subdepartments, create_master_subdepartment, update_master_subdepartment, delete_master_subdepartment,
    # Organigram helpers
    get_managed_employee_ids, is_manager
)

from models import get_companies, get_brands_for_company, get_departments_for_company, clear_structure_cache


def hr_required(f):
    """Decorator to require HR access permission (view only).

    Sets on Flask g object:
        g.permission_scope: Default to 'all' for view access, or check permissions_v2
        g.user_context: Dict with user_id, company, department, org_unit_id
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not getattr(current_user, 'can_access_hr', False):
            flash('HR access required.', 'error')
            return redirect(url_for('index'))

        # Set user context for scope filtering
        g.user_context = {
            'user_id': current_user.id,
            'company': getattr(current_user, 'company', None),
            'department': getattr(current_user, 'department', None),
            'org_unit_id': getattr(current_user, 'org_unit_id', None)
        }

        # Check view permission scope using permissions_v2
        role_id = getattr(current_user, 'role_id', None)
        if role_id:
            # Check the most relevant view permission for the endpoint
            # Default to checking bonuses.view as it's most common
            perm = check_permission_v2(role_id, 'hr', 'bonuses', 'view')
            g.permission_scope = perm.get('scope', 'all') if perm['has_permission'] else 'all'
        else:
            # Fallback: HR managers get 'all' scope, others get 'all' too (view only)
            g.permission_scope = 'all'

        return f(*args, **kwargs)
    return decorated


def hr_manager_required(f):
    """Decorator to require HR Manager permission for write operations.
    Uses is_hr_manager flag as fallback if permissions_v2 not configured.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not getattr(current_user, 'can_access_hr', False):
            flash('HR access required.', 'error')
            return redirect(url_for('index'))
        if not getattr(current_user, 'is_hr_manager', False):
            # For API calls, return JSON error
            if request.path.startswith('/hr/events/api/'):
                return jsonify({'success': False, 'error': 'HR Manager permission required'}), 403
            flash('HR Manager permission required.', 'error')
            return redirect(url_for('hr.events.event_bonuses'))
        return f(*args, **kwargs)
    return decorated


def hr_permission_required(entity: str, action: str):
    """HR V2 permission check. Sets g.permission_scope and g.user_context.

    All callers already have @login_required. Falls back to is_hr_manager
    for write operations when no explicit V2 entry exists.
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            # Set user context for scope filtering in route handlers
            g.user_context = {
                'user_id': current_user.id,
                'company': getattr(current_user, 'company', None),
                'department': getattr(current_user, 'department', None),
                'org_unit_id': getattr(current_user, 'org_unit_id', None)
            }

            role_id = getattr(current_user, 'role_id', None)
            if role_id:
                perm = check_permission_v2(role_id, 'hr', entity, action)
                if perm['has_permission']:
                    g.permission_scope = perm.get('scope', 'all')
                    return f(*args, **kwargs)

            # Fallback: is_hr_manager covers write ops when V2 has no explicit entry
            if action in ('add', 'edit', 'delete', 'export') and getattr(current_user, 'is_hr_manager', False):
                g.permission_scope = 'all'
                return f(*args, **kwargs)

            return jsonify({'success': False, 'error': f'Permission denied: hr.{entity}.{action}'}), 403
        return decorated
    return decorator


# Romanian month names for display
MONTH_NAMES = {
    1: 'Ianuarie', 2: 'Februarie', 3: 'Martie', 4: 'Aprilie',
    5: 'Mai', 6: 'Iunie', 7: 'Iulie', 8: 'August',
    9: 'Septembrie', 10: 'Octombrie', 11: 'Noiembrie', 12: 'Decembrie'
}


def _compute_bonus_net(data):
    """Compute bonus_net from bonus_type_id and bonus_days if not provided."""
    bonus_net = data.get('bonus_net')
    if bonus_net:
        return bonus_net
    bonus_type_id = data.get('bonus_type_id')
    bonus_days = data.get('bonus_days')
    if bonus_type_id and bonus_days:
        bt = get_bonus_type(int(bonus_type_id))
        if bt:
            rate = bt['amount'] / (bt.get('days_per_amount') or 1)
            return round(rate * float(bonus_days), 2)
    return bonus_net


def resolve_presence_days(data):
    """Normalise ``data['presence_days']`` (ISO date strings) against the event's
    date range. Returns a sorted ``list[date]``, or ``None`` when not supplied.
    Raises ``ValueError`` (message safe to surface) when a day is out of range.
    """
    raw = data.get('presence_days')
    if not raw:
        return None
    from ..presence import normalize_presence_days
    event = get_hr_event(data.get('event_id'))
    if not event:
        raise ValueError('Event not found')
    return normalize_presence_days(raw, event['start_date'], event['end_date'])


def check_presence_months_editable(presence_days, user_role):
    """Return ``(True, '')`` only if every month the presence days touch is
    editable; otherwise ``(False, reason)`` for the first locked month. Admin
    bypass is handled inside ``can_edit_bonus``.
    """
    from ..presence import months_touched
    for (yr, mo) in months_touched(presence_days):
        ok, reason = can_edit_bonus(yr, mo, user_role)
        if not ok:
            return False, reason
    return True, ''
