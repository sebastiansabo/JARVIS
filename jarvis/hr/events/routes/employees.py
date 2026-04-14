from ._shared import *


# ============== Employees API Routes ==============
# Note: Employee management page is now in core Settings (Settings → HR → Employees)
# These API routes are kept for HR Events module to fetch employees for bonuses

@events_bp.route('/api/employees', methods=['GET'])
@login_required
@hr_required
def api_get_employees():
    """API: Get all employees with scope-based access control."""
    active_only = request.args.get('active_only', 'true').lower() == 'true'

    # Get scope from decorator
    scope = getattr(g, 'permission_scope', 'all')
    user_context = getattr(g, 'user_context', None)

    employees = get_all_hr_employees(
        active_only=active_only,
        scope=scope, user_context=user_context
    )
    return jsonify(employees)


@events_bp.route('/api/employees/search', methods=['GET'])
@login_required
@hr_required
def api_search_employees():
    """API: Search employees by name."""
    query = request.args.get('q', '')
    if len(query) < 2:
        return jsonify([])
    employees = search_hr_employees(query)
    return jsonify(employees)


@events_bp.route('/api/employees', methods=['POST'])
@login_required
@hr_permission_required('employees', 'add')
def api_create_employee():
    """API: Create a new employee."""
    data = request.get_json()

    employee_id = save_hr_employee(
        name=data['name'],
        department=data.get('departments'),  # frontend sends 'departments'
        subdepartment=data.get('subdepartment'),
        brand=data.get('brand'),
        company=data.get('company'),
        email=data.get('email'),
        phone=data.get('phone'),
        notify_on_allocation=data.get('notify_on_allocation', True)
    )

    return jsonify({'success': True, 'id': employee_id})


@events_bp.route('/api/employees/<int:employee_id>', methods=['GET'])
@login_required
@hr_required
def api_get_employee(employee_id):
    """API: Get a single employee."""
    employee = get_hr_employee(employee_id)
    if not employee:
        return error_response('Employee not found', 404)
    return jsonify(employee)


@events_bp.route('/api/employees/<int:employee_id>', methods=['PUT'])
@login_required
@hr_permission_required('employees', 'edit')
def api_update_employee(employee_id):
    """API: Update an employee with scope validation."""
    # Validate scope access
    scope = getattr(g, 'permission_scope', 'all')
    user_context = getattr(g, 'user_context', None)

    if not can_access_employee(employee_id, scope, user_context):
        return jsonify({'success': False, 'error': 'Access denied: employee outside your scope'}), 403

    data = request.get_json()

    update_hr_employee(
        employee_id=employee_id,
        name=data['name'],
        department=data.get('departments'),  # frontend sends 'departments'
        subdepartment=data.get('subdepartment'),
        brand=data.get('brand'),
        company=data.get('company'),
        email=data.get('email'),
        phone=data.get('phone'),
        notify_on_allocation=data.get('notify_on_allocation', True),
        is_active=data.get('is_active', True)
    )

    return jsonify({'success': True})


@events_bp.route('/api/employees/<int:employee_id>', methods=['DELETE'])
@login_required
@hr_permission_required('employees', 'delete')
def api_delete_employee(employee_id):
    """API: Soft delete an employee with scope validation."""
    # Validate scope access
    scope = getattr(g, 'permission_scope', 'all')
    user_context = getattr(g, 'user_context', None)

    if not can_access_employee(employee_id, scope, user_context):
        return jsonify({'success': False, 'error': 'Access denied: employee outside your scope'}), 403

    delete_hr_employee(employee_id)
    return jsonify({'success': True})


# ============== Permissions API ==============

@events_bp.route('/api/permissions', methods=['GET'])
@login_required
def api_permissions():
    """Return current user's HR permissions for frontend.

    Returns a dict of permission names with their allowed status and scope.
    This enables the frontend to show/hide UI elements based on granular permissions.
    """
    permissions = {}

    role_id = getattr(current_user, 'role_id', None)
    is_hr_manager = getattr(current_user, 'is_hr_manager', False)
    can_access_hr = getattr(current_user, 'can_access_hr', False)

    # Load all HR permissions dynamically from v2 schema — single query for this role
    from core.roles.repositories.permission_repository import PermissionRepository as _PermRepo
    _perm_repo_local = _PermRepo()
    role_perms_map = _perm_repo_local.get_role_permissions_for_module(role_id, 'hr') if role_id else {}

    for perm_key, perm_data in role_perms_map.items():
        entity, action = perm_key.split('.', 1)
        allowed = False
        scope = 'deny'

        if can_access_hr:
            allowed = perm_data['has_permission']
            scope = perm_data.get('scope', 'deny') if allowed else 'deny'

        permissions[f'hr.{perm_key}'] = {
            'allowed': allowed,
            'scope': scope
        }

    return jsonify({
        'permissions': permissions,
        'user_context': {
            'user_id': current_user.id,
            'company': getattr(current_user, 'company', None),
            'department': getattr(current_user, 'department', None),
            'is_hr_manager': is_hr_manager,
            'can_access_hr': can_access_hr,
        }
    })
