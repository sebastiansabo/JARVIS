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
    contract_status = request.args.get('contract_status')  # 'active', 'suspended', 'closed'

    # Get scope from decorator
    scope = getattr(g, 'permission_scope', 'all')
    user_context = getattr(g, 'user_context', None)

    employees = get_all_hr_employees(
        active_only=active_only,
        scope=scope, user_context=user_context,
        contract_status=contract_status,
    )
    return jsonify(employees)


@events_bp.route('/api/employees/absent-today', methods=['GET'])
@login_required
@hr_required
def api_absent_today():
    """API: Get today's absence status for all active employees."""
    from datetime import date
    from ..repositories import EmployeeOverviewRepository
    rows = EmployeeOverviewRepository().get_absence_status_for_date(date.today())
    result = {}
    for r in rows:
        result[r['user_id']] = {
            'status': r['status'],
            'leave_code': r.get('leave_code'),
        }
    return jsonify(result)


@events_bp.route('/api/employees/work-stats', methods=['GET'])
@login_required
@hr_required
def api_employee_work_stats():
    """API: Get work stats for all employees over an arbitrary date range."""
    from datetime import date as dt_date, timedelta
    from core.connectors.biostar.repositories.biostar_repository import BioStarRepository
    from core.utils.work_calendar import get_working_days_range

    today = dt_date.today()

    # Accept start_date / end_date for arbitrary ranges
    start_str = request.args.get('start_date')
    end_str = request.args.get('end_date')

    if start_str and end_str:
        start = dt_date.fromisoformat(start_str)
        end = dt_date.fromisoformat(end_str)
        # Clamp end to today (can't have future punch data)
        if end > today:
            end = today
    else:
        # Fallback: current month (backwards compatible)
        year = request.args.get('year', today.year, type=int)
        month = request.args.get('month', today.month, type=int)
        start = dt_date(year, month, 1)
        if month == 12:
            end = dt_date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end = dt_date(year, month + 1, 1) - timedelta(days=1)
        if end > today:
            end = today

    working_days = get_working_days_range(start, end)
    if working_days == 0:
        return jsonify({})

    bio_repo = BioStarRepository()
    range_data = bio_repo.get_range_summary(start.isoformat(), end.isoformat())

    # Bulk fetch motivated absences from all sources
    from core.base_repository import BaseRepository
    _base = BaseRepository()

    # 1. Sincron timesheets — full-day leave codes
    LEAVE_CODES = ('CO', 'CIC', 'CES', 'CM', 'CMS', 'DLG', 'ZLS')
    sincron_leave = _base.query_all('''
        SELECT se.mapped_jarvis_user_id,
               COUNT(DISTINCT st.day) AS leave_days,
               STRING_AGG(DISTINCT st.short_code, ', ' ORDER BY st.short_code) AS leave_types
        FROM sincron_timesheets st
        JOIN sincron_employees se
          ON se.sincron_employee_id = st.sincron_employee_id
          AND se.company_name = st.company_name
        WHERE se.mapped_jarvis_user_id IS NOT NULL
          AND st.short_code = ANY(%s)
          AND st.day BETWEEN %s AND %s
        GROUP BY se.mapped_jarvis_user_id
    ''', (list(LEAVE_CODES), start.isoformat(), end.isoformat()))
    sincron_map = {r['mapped_jarvis_user_id']: r for r in sincron_leave}

    # 2. Connecteam — leave permits (partial-day, in hours)
    connecteam_leave = _base.query_all('''
        SELECT mapped_jarvis_user_id,
               COUNT(*) AS permit_count,
               COALESCE(SUM(leave_hours), 0) AS permit_hours
        FROM connecteam_form_submissions
        WHERE mapped_jarvis_user_id IS NOT NULL
          AND leave_date BETWEEN %s AND %s
          AND COALESCE(status, 'submitted') NOT IN ('rejected', 'cancelled')
        GROUP BY mapped_jarvis_user_id
    ''', (start.isoformat(), end.isoformat()))
    connecteam_map = {r['mapped_jarvis_user_id']: r for r in connecteam_leave}

    result = {}
    for row in range_data:
        uid = row.get('mapped_jarvis_user_id')
        if not uid:
            continue

        days_present = int(row.get('days_present') or 0)
        adjusted_total = float(row.get('adjusted_total_duration_seconds') or 0)
        lunch_mins = int(row.get('lunch_break_minutes') or 0)
        working_h = float(row.get('working_hours') or 8)

        # Total hours: adjusted duration minus lunch for each present day
        total_hours = max(0, (adjusted_total - (lunch_mins * 60 * days_present)) / 3600)
        total_hours = round(total_hours, 1)

        # Avg daily hours (only days they punched in)
        avg_daily = round(total_hours / days_present, 1) if days_present > 0 else 0

        # Schedule variance (STDDEV of check-in/out times → average → minutes)
        stddev_in = float(row.get('stddev_check_in_epoch') or 0)
        stddev_out = float(row.get('stddev_check_out_epoch') or 0)
        count = sum(1 for v in [stddev_in, stddev_out] if v > 0)
        avg_stddev = ((stddev_in + stddev_out) / count) if count > 0 else 0
        variance_minutes = round(avg_stddev / 60)

        # Motivated absences reduce working potential
        s_leave = sincron_map.get(uid, {})
        c_leave = connecteam_map.get(uid, {})
        sincron_leave_days = int(s_leave.get('leave_days', 0))
        sincron_leave_types = s_leave.get('leave_types', '')
        permit_count = int(c_leave.get('permit_count', 0))
        permit_hours = round(float(c_leave.get('permit_hours', 0)), 1)
        # Sincron = full days, Connecteam = hours (convert to fractional days)
        leave_days = sincron_leave_days
        leave_hours = permit_hours
        effective_days = max(1, working_days - leave_days)

        # Efficiency score (100-point scale) — based on effective working days
        expected_hours = working_h * effective_days
        utilization = min((total_hours / expected_hours * 100), 100) if expected_hours > 0 else 0
        attendance = min((days_present / effective_days * 100), 100) if effective_days > 0 else 0
        punctuality = max(0, 100 - (variance_minutes * 1.5))

        score = round(utilization * 0.5 + attendance * 0.3 + punctuality * 0.2, 1)

        result[uid] = {
            'total_hours': total_hours,
            'avg_daily_hours': avg_daily,
            'variance_minutes': int(variance_minutes),
            'productivity_score': score,
            'days_present': days_present,
            'working_days': working_days,
            'effective_days': effective_days,
            'expected_hours': round(expected_hours, 1),
            'hours_per_day': round(working_h, 1),
            'lunch_break_minutes': lunch_mins,
            'schedule_start': str(row['schedule_start'])[:5] if row.get('schedule_start') else None,
            'schedule_end': str(row['schedule_end'])[:5] if row.get('schedule_end') else None,
            'leave_days': leave_days,
            'leave_types': sincron_leave_types,
            'permit_count': permit_count,
            'permit_hours': permit_hours,
        }

    # Backfill: active BioStar-mapped employees with NO punch data
    # so absent employees show 0h stats and are included in averages
    all_bio = bio_repo.get_all_employees(active_only=True)
    for emp in all_bio:
        uid = emp.get('mapped_jarvis_user_id')
        if not uid or uid in result:
            continue
        working_h = float(emp.get('working_hours') or 8)
        lunch_mins = int(emp.get('lunch_break_minutes') or 0)
        s_leave = sincron_map.get(uid, {})
        c_leave = connecteam_map.get(uid, {})
        sincron_leave_days = int(s_leave.get('leave_days', 0))
        sincron_leave_types = s_leave.get('leave_types', '')
        permit_count = int(c_leave.get('permit_count', 0))
        permit_hours = round(float(c_leave.get('permit_hours', 0)), 1)
        leave_days = sincron_leave_days
        effective_days = max(1, working_days - leave_days)
        expected_hours = working_h * effective_days

        # If fully on leave, skip — they're accounted for
        if leave_days >= working_days:
            continue

        score = 0  # Absent without motive: 0 utilization, 0 attendance, 0 punctuality

        result[uid] = {
            'total_hours': 0,
            'avg_daily_hours': 0,
            'variance_minutes': 0,
            'productivity_score': score,
            'days_present': 0,
            'working_days': working_days,
            'effective_days': effective_days,
            'expected_hours': round(expected_hours, 1),
            'hours_per_day': round(working_h, 1),
            'lunch_break_minutes': lunch_mins,
            'schedule_start': str(emp['schedule_start'])[:5] if emp.get('schedule_start') else None,
            'schedule_end': str(emp['schedule_end'])[:5] if emp.get('schedule_end') else None,
            'leave_days': leave_days,
            'leave_types': sincron_leave_types,
            'permit_count': permit_count,
            'permit_hours': permit_hours,
        }

    return jsonify(result)


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

    # Support partial updates (e.g. toggling only notify_missing_punch)
    kwargs = {}
    if 'name' in data:
        kwargs['name'] = data['name']
    if 'departments' in data:
        kwargs['department'] = data['departments']
    if 'subdepartment' in data:
        kwargs['subdepartment'] = data['subdepartment']
    if 'brand' in data:
        kwargs['brand'] = data['brand']
    if 'company' in data:
        kwargs['company'] = data['company']
    if 'email' in data:
        kwargs['email'] = data['email']
    if 'phone' in data:
        kwargs['phone'] = data['phone']
    if 'notify_on_allocation' in data:
        kwargs['notify_on_allocation'] = data['notify_on_allocation']
    if 'is_active' in data:
        kwargs['is_active'] = data['is_active']
    if 'contract_status' in data:
        kwargs['contract_status'] = data['contract_status']
    if 'notify_missing_punch' in data:
        kwargs['notify_missing_punch'] = data['notify_missing_punch']

    update_hr_employee(employee_id=employee_id, **kwargs)

    return jsonify({'success': True})


@events_bp.route('/api/employees/bulk-toggle-missing-punch', methods=['POST'])
@login_required
@hr_permission_required('employees', 'edit')
def api_bulk_toggle_missing_punch():
    """API: Bulk toggle notify_missing_punch for employees."""
    data = request.get_json()
    enabled = data.get('enabled', True)
    user_ids = data.get('user_ids')  # None means all active employees

    scope = getattr(g, 'permission_scope', 'all')
    user_context = getattr(g, 'user_context', None)

    from hr.events.repositories.employee_repository import EmployeeRepository
    repo = EmployeeRepository()
    updated = repo.bulk_toggle_missing_punch(
        user_ids=user_ids, enabled=enabled,
        scope=scope, user_context=user_context,
    )

    return jsonify({'success': True, 'updated': updated})


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
