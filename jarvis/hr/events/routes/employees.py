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
    """API: Get absence status for all active employees on a given date."""
    from datetime import date as dt_date
    from ..repositories import EmployeeOverviewRepository
    date_str = request.args.get('date')
    check_date = dt_date.fromisoformat(date_str) if date_str else dt_date.today()
    rows = EmployeeOverviewRepository().get_absence_status_for_date(check_date)
    result = {}
    for r in rows:
        result[r['user_id']] = {
            'status': r['status'],
            'leave_code': r.get('leave_code'),
            'first_punch': r.get('first_punch'),
            'last_punch': r.get('last_punch'),
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

    # Bulk fetch per-company norms from Sincron
    from core.connectors.sincron.repositories.sincron_repository import SincronRepository
    sincron_repo = SincronRepository()
    company_norms_raw = sincron_repo.get_all_company_norms()
    # Group by jarvis_user_id → list of {company, norma, start, end, lunch}
    company_norms_map = {}
    for cn in company_norms_raw:
        uid = cn['mapped_jarvis_user_id']
        if uid not in company_norms_map:
            company_norms_map[uid] = []
        company_norms_map[uid].append({
            'company': cn['company_name'],
            'norma': float(cn['norma_lucru']),
            'start': str(cn['schedule_start'])[:5] if cn.get('schedule_start') else None,
            'end': str(cn['schedule_end'])[:5] if cn.get('schedule_end') else None,
            'lunch': int(cn['lunch_break_minutes'] or 0),
        })

    # Bulk fetch motivated absences from all sources
    from core.base_repository import BaseRepository
    _base = BaseRepository()

    # 1. Sincron timesheets — motivated absence codes (leave + absence categories, from DB)
    from core.connectors.sincron.repositories.sincron_repository import SincronRepository
    _sincron_repo = SincronRepository()
    LEAVE_CODES = _sincron_repo.get_absence_codes() or ('CO', 'CIC', 'CES', 'CM', 'CMS', 'DLG', 'ZLS')
    sincron_leave = _base.query_all('''
        SELECT se.mapped_jarvis_user_id,
               COUNT(DISTINCT st.day) AS leave_days,
               STRING_AGG(DISTINCT st.short_code, ', ' ORDER BY st.short_code) AS leave_types
        FROM sincron_timesheets st
        JOIN sincron_employees se
          ON se.sincron_employee_id = st.sincron_employee_id
          AND se.company_name = st.company_name
        WHERE se.mapped_jarvis_user_id IS NOT NULL
          AND se.count_for_leave = TRUE
          AND st.short_code = ANY(%s)
          AND st.day BETWEEN %s AND %s
        GROUP BY se.mapped_jarvis_user_id
    ''', (list(LEAVE_CODES), start.isoformat(), end.isoformat()))
    sincron_map = {r['mapped_jarvis_user_id']: r for r in sincron_leave}

    # 1b. Per-company leave breakdown (for multi-company sub-rows)
    sincron_leave_by_company = _base.query_all('''
        SELECT se.mapped_jarvis_user_id, se.company_name,
               COUNT(DISTINCT st.day) AS leave_days,
               STRING_AGG(DISTINCT st.short_code, ', ' ORDER BY st.short_code) AS leave_types
        FROM sincron_timesheets st
        JOIN sincron_employees se
          ON se.sincron_employee_id = st.sincron_employee_id
          AND se.company_name = st.company_name
        WHERE se.mapped_jarvis_user_id IS NOT NULL
          AND se.count_for_leave = TRUE
          AND st.short_code = ANY(%s)
          AND st.day BETWEEN %s AND %s
        GROUP BY se.mapped_jarvis_user_id, se.company_name
    ''', (list(LEAVE_CODES), start.isoformat(), end.isoformat()))
    # {user_id: {company_name: {leave_days, leave_types}}}
    sincron_leave_company_map = {}
    for r in sincron_leave_by_company:
        sincron_leave_company_map.setdefault(
            r['mapped_jarvis_user_id'], {}
        )[r['company_name']] = r

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

    # 3. JARVIS forms — Bilet de Invoire (partial-day, in hours)
    jarvis_form_leave = _base.query_all('''
        SELECT fs.respondent_user_id AS user_id,
               COUNT(*) AS form_permit_count,
               COALESCE(SUM((fs.answers->>'f_bi_hours')::numeric), 0) AS form_permit_hours
        FROM form_submissions fs
        JOIN forms f ON f.id = fs.form_id
        WHERE f.slug = 'bilet-de-invoire'
          AND fs.respondent_user_id IS NOT NULL
          AND (fs.answers->>'f_bi_leave_date') IS NOT NULL
          AND (fs.answers->>'f_bi_leave_date') ~ %s
          AND (fs.answers->>'f_bi_leave_date')::date BETWEEN %s AND %s
        GROUP BY fs.respondent_user_id
    ''', (r'^\d{4}-\d{2}-\d{2}$', start.isoformat(), end.isoformat()))
    jarvis_form_map = {r['user_id']: r for r in jarvis_form_leave}

    # 4. CO balance (imported from HR xlsx) — annual snapshot + used YTD
    from hr.co_balance.repository import CoBalanceRepository
    _co_repo = CoBalanceRepository()
    _co_year = end.year
    _co_map = _co_repo.get_for_year(_co_year)
    _co_used_map = _co_repo.get_used_ytd_by_user(_co_year)
    # 4b. Per-company CO data (for multi-company sub-rows)
    _co_company_map = _co_repo.get_for_year_by_company(_co_year)
    _co_used_company_map = _co_repo.get_used_ytd_by_user_company(_co_year)

    def _norm_company(name):
        """Normalize company name for matching (strip S.R.L. / SRL suffixes)."""
        if not name:
            return ''
        return name.upper().replace(' S.R.L.', '').replace(' SRL', '').strip()

    def _co_payload(uid, enriched_companies=None):
        """Build main-row CO from enriched sub-rows so totals always match."""
        if enriched_companies:
            vals = [c for c in enriched_companies if c.get('co_total') is not None]
            if vals:
                total = sum(c['co_total'] for c in vals)
                carry = sum(c.get('co_carry_over') or 0 for c in vals)
                used = sum(c.get('co_used_ytd') or 0 for c in vals)
                return {
                    'co_total': total,
                    'co_carry_over': carry,
                    'co_used_ytd': used,
                    'co_balance': total - used,
                    'co_year': _co_year,
                }
        # Fallback for employees without sub-rows
        co = _co_map.get(uid)
        if not co:
            return {
                'co_total': None,
                'co_carry_over': None,
                'co_used_ytd': None,
                'co_balance': None,
                'co_year': None,
            }
        total = int(co.get('total_available') or 0)
        used = int(round(_co_used_map.get(uid, 0)))
        return {
            'co_total': total,
            'co_carry_over': int(co.get('carry_prev_year') or 0),
            'co_used_ytd': used,
            'co_balance': total - used,
            'co_year': _co_year,
        }

    def _enrich_companies(uid, companies):
        """Enrich schedule_companies entries with per-company CO + leave data."""
        if not companies:
            return companies
        user_co_raw = _co_company_map.get(uid, {})
        # Build normalized lookup: norm_name → co_balance_row
        co_norm = {_norm_company(k): v for k, v in user_co_raw.items()}
        user_co_used_raw = _co_used_company_map.get(uid, {})
        user_leave = sincron_leave_company_map.get(uid, {})
        enriched = []
        for comp in companies:
            cname = comp['company']
            co = co_norm.get(_norm_company(cname))
            co_total = int(co.get('total_available') or 0) if co else None
            co_used = int(round(user_co_used_raw.get(cname, 0))) if cname in user_co_used_raw else None
            leave = user_leave.get(cname)
            enriched.append({
                **comp,
                'co_total': co_total,
                'co_carry_over': int(co.get('carry_prev_year') or 0) if co else None,
                'co_used_ytd': co_used,
                'co_remaining': (co_total - co_used) if co_total is not None and co_used is not None else None,
                'leave_days': int(leave.get('leave_days', 0)) if leave else 0,
                'leave_types': leave.get('leave_types', '') if leave else '',
            })
        return enriched

    result = {}
    for row in range_data:
        uid = row.get('mapped_jarvis_user_id')
        if not uid:
            continue

        raw_days_present = int(row.get('days_present') or 0)
        single_punch_days = int(row.get('single_punch_days') or 0)
        # Single-punch days don't count as present for stats (no measurable work time)
        days_present = raw_days_present - single_punch_days
        # Skip employees with only single-punch days (no measurable hours)
        if days_present <= 0 and single_punch_days > 0:
            continue
        raw_duration = float(row.get('total_duration_seconds') or 0)
        lunch_mins = int(row.get('lunch_break_minutes') or 0)
        working_h = float(row.get('working_hours') or 8)

        # Total hours: raw punch duration (last-first per day) minus lunch for each REAL present day
        total_hours = max(0, (raw_duration - (lunch_mins * 60 * days_present)) / 3600)
        total_hours = round(total_hours, 1)

        # Avg daily hours (only days with proper in/out)
        avg_daily = round(total_hours / days_present, 1) if days_present > 0 else 0

        # Average check-in/out times (epoch seconds → "HH:MM")
        avg_in_epoch = float(row.get('avg_check_in_epoch') or 0)
        avg_out_epoch = float(row.get('avg_check_out_epoch') or 0)
        avg_check_in = f"{int(avg_in_epoch // 3600):02d}:{int((avg_in_epoch % 3600) // 60):02d}" if avg_in_epoch > 0 else None
        avg_check_out = f"{int(avg_out_epoch // 3600):02d}:{int((avg_out_epoch % 3600) // 60):02d}" if avg_out_epoch > 0 else None

        # Schedule variance (STDDEV of check-in/out times → average → minutes)
        stddev_in = float(row.get('stddev_check_in_epoch') or 0)
        stddev_out = float(row.get('stddev_check_out_epoch') or 0)
        count = sum(1 for v in [stddev_in, stddev_out] if v > 0)
        avg_stddev = ((stddev_in + stddev_out) / count) if count > 0 else 0
        variance_minutes = round(avg_stddev / 60)

        # Motivated absences reduce working potential
        s_leave = sincron_map.get(uid, {})
        c_leave = connecteam_map.get(uid, {})
        j_leave = jarvis_form_map.get(uid, {})
        # Distinct calendar days for utilization calculation
        distinct_leave_days = int(s_leave.get('leave_days', 0))
        permit_count = int(c_leave.get('permit_count', 0)) + int(j_leave.get('form_permit_count', 0))
        permit_hours = round(float(c_leave.get('permit_hours', 0)) + float(j_leave.get('form_permit_hours', 0)), 1)
        # Sincron = full days, Connecteam + JARVIS forms = partial hours
        effective_days = max(1, working_days - distinct_leave_days)
        # Sum per-company leave data for display (matches sub-row totals)
        user_leave_co = sincron_leave_company_map.get(uid, {})
        if user_leave_co:
            leave_days = sum(int(lc.get('leave_days', 0)) for lc in user_leave_co.values())
            sincron_leave_types = ', '.join(sorted({
                t.strip() for lc in user_leave_co.values()
                for t in (lc.get('leave_types', '') or '').split(',') if t.strip()
            }))
        else:
            leave_days = distinct_leave_days
            sincron_leave_types = s_leave.get('leave_types', '')

        # Expected hours: schedule × effective days minus all permit hours (Connecteam + JARVIS forms)
        expected_hours = max(0, working_h * effective_days - permit_hours)
        utilization = min((total_hours / expected_hours * 100), 100) if expected_hours > 0 else 0
        attendance = min((days_present / effective_days * 100), 100) if effective_days > 0 else 0
        punctuality = max(0, 100 - (variance_minutes * 1.5))

        score = round(utilization * 0.5 + attendance * 0.3 + punctuality * 0.2, 1)

        enriched_cos = _enrich_companies(uid, company_norms_map.get(uid, []))

        result[uid] = {
            'total_hours': total_hours,
            'avg_daily_hours': avg_daily,
            'variance_minutes': int(variance_minutes),
            'productivity_score': score,
            'days_present': days_present,
            'single_punch_days': single_punch_days,
            'working_days': working_days,
            'effective_days': effective_days,
            'expected_hours': round(expected_hours, 1),
            'hours_per_day': round(working_h, 1),
            'lunch_break_minutes': lunch_mins,
            'schedule_start': str(row['schedule_start'])[:5] if row.get('schedule_start') else None,
            'schedule_end': str(row['schedule_end'])[:5] if row.get('schedule_end') else None,
            'leave_days': leave_days,
            'leave_hours': round(leave_days * working_h, 1),
            'leave_types': sincron_leave_types,
            'permit_count': permit_count,
            'permit_hours': permit_hours,
            'avg_check_in': avg_check_in,
            'avg_check_out': avg_check_out,
            'schedule_companies': enriched_cos,
            **_co_payload(uid, enriched_cos),
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
        j_leave = jarvis_form_map.get(uid, {})
        distinct_leave_days = int(s_leave.get('leave_days', 0))
        permit_count = int(c_leave.get('permit_count', 0)) + int(j_leave.get('form_permit_count', 0))
        permit_hours = round(float(c_leave.get('permit_hours', 0)) + float(j_leave.get('form_permit_hours', 0)), 1)
        effective_days = max(1, working_days - distinct_leave_days)
        expected_hours = max(0, working_h * effective_days - permit_hours)
        # Sum per-company leave for display
        user_leave_co = sincron_leave_company_map.get(uid, {})
        if user_leave_co:
            leave_days = sum(int(lc.get('leave_days', 0)) for lc in user_leave_co.values())
            sincron_leave_types = ', '.join(sorted({
                t.strip() for lc in user_leave_co.values()
                for t in (lc.get('leave_types', '') or '').split(',') if t.strip()
            }))
        else:
            leave_days = distinct_leave_days
            sincron_leave_types = s_leave.get('leave_types', '')

        # If fully on leave, skip — they're accounted for
        if distinct_leave_days >= working_days:
            continue

        score = 0  # Absent without motive: 0 utilization, 0 attendance, 0 punctuality

        enriched_cos = _enrich_companies(uid, company_norms_map.get(uid, []))

        result[uid] = {
            'total_hours': 0,
            'avg_daily_hours': 0,
            'variance_minutes': 0,
            'productivity_score': score,
            'days_present': 0,
            'single_punch_days': 0,
            'working_days': working_days,
            'effective_days': effective_days,
            'expected_hours': round(expected_hours, 1),
            'hours_per_day': round(working_h, 1),
            'lunch_break_minutes': lunch_mins,
            'schedule_start': str(emp['schedule_start'])[:5] if emp.get('schedule_start') else None,
            'schedule_end': str(emp['schedule_end'])[:5] if emp.get('schedule_end') else None,
            'leave_days': leave_days,
            'leave_hours': round(leave_days * working_h, 1),
            'leave_types': sincron_leave_types,
            'permit_count': permit_count,
            'permit_hours': permit_hours,
            'avg_check_in': None,
            'avg_check_out': None,
            'schedule_companies': enriched_cos,
            **_co_payload(uid, enriched_cos),
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
