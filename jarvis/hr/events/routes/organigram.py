from ._shared import *


# ============== Organigram API ==============

@events_bp.route('/api/organigram', methods=['GET'])
@login_required
@hr_required
def api_get_organigram():
    """API: Get organigram data — employees + department structures with manager mappings."""
    role_id = getattr(current_user, 'role_id', None)
    if role_id:
        from core.roles.repositories.permission_repository import PermissionRepository
        perm = PermissionRepository().check_permission_v2(role_id, 'hr', 'structure', 'view')
        if not perm.get('has_permission') and not getattr(current_user, 'can_access_settings', False):
            from flask import abort
            abort(403)
    employees = get_all_hr_employees(active_only=True)
    structures = get_all_department_structures()
    companies = get_all_companies_with_brands()
    user_is_manager = is_manager(current_user.id)

    # Serialize companies for JSON
    for company in companies:
        if company.get('created_at'):
            company['created_at'] = company['created_at'].isoformat() if hasattr(company['created_at'], 'isoformat') else company['created_at']
        brand_list = company.get('brands', [])
        company['brands'] = ', '.join(brand_list) if isinstance(brand_list, list) else brand_list
        company['brands_list'] = [{'brand': b} for b in (brand_list if isinstance(brand_list, list) else [])]

    return jsonify({
        'employees': employees,
        'structures': structures,
        'companies': companies,
        'current_user_id': current_user.id,
        'is_manager': user_is_manager,
    })


# ============== Employee 360 Overview ==============

@events_bp.route('/api/employees/<int:user_id>/overview', methods=['GET'])
@login_required
@hr_required
def api_get_employee_overview(user_id):
    """Get aggregated overview for Employee 360 page."""
    import traceback as _tb
    from ..repositories import EmployeeOverviewRepository

    _overview_repo = EmployeeOverviewRepository()

    try:
        employee = get_hr_employee(user_id)
        if not employee:
            return jsonify({'success': False, 'error': 'Employee not found'}), 404

        biostar = _overview_repo.get_biostar_mapping(user_id)
        sincron = _overview_repo.get_sincron_mapping(user_id)
        connecteam = _overview_repo.get_connecteam_mapping(user_id)
        org = _overview_repo.get_org_path(user_id) or {}
        bonus_row = _overview_repo.get_bonus_summary(user_id)
        bonuses = bonus_row if bonus_row else {'bonus_count': 0, 'total_bonus_days': 0, 'total_bonus_net': 0}
        forms_count = _overview_repo.get_form_submissions_count(user_id)

        # ── Monthly work statistics (supports year/month query params) ──
        from datetime import date as _date
        _today = _date.today()
        _year = request.args.get('year', _today.year, type=int)
        _month = request.args.get('month', _today.month, type=int)

        # BioStar attendance this month
        attendance = {'days_present': 0, 'total_hours': 0.0, 'avg_daily_hours': 0.0}
        lunch_h = 0.0
        if biostar:
            lunch_h = float(biostar.get('lunch_break_minutes', 0)) / 60.0
            attendance['days_present'] = _overview_repo.get_monthly_attendance_days(
                biostar['biostar_user_id'], _year, _month)
            raw_total_h, days_with_punches = _overview_repo.get_monthly_hours_aggregate(
                biostar['biostar_user_id'], _year, _month)
            total_h = max(0, raw_total_h - (lunch_h * days_with_punches))
            attendance['total_hours'] = round(total_h, 1)
            if attendance['days_present'] > 0:
                attendance['avg_daily_hours'] = round(total_h / attendance['days_present'], 1)

        timesheet_summary = _overview_repo.get_monthly_sincron_summary(
            sincron['sincron_employee_id'], sincron['company_name'], _year, _month
        ) if sincron else {}

        lp_count, lp_hours = _overview_repo.get_monthly_leave_permits(user_id, _year, _month)
        leave_stats = {'count': lp_count, 'total_hours': lp_hours}

        ytd_leave = _overview_repo.get_ytd_sincron_leave(
            sincron['sincron_employee_id'], sincron['company_name'], _year
        ) if sincron else {}

        ytd_count, ytd_hours = _overview_repo.get_ytd_leave_permits(user_id, _year)
        ytd_permits = {'count': ytd_count, 'total_hours': ytd_hours}

        # ── Daily attendance for bar chart ──
        import calendar
        daily_hours = []
        days_in_month = calendar.monthrange(_year, _month)[1]
        working_h = float(biostar.get('working_hours', 8)) if biostar else 8.0

        if biostar:
            daily_rows = _overview_repo.get_daily_punch_hours(biostar['biostar_user_id'], _year, _month)
            day_map = {}
            for row in daily_rows:
                d = row['day']
                h = float(row['span_h'])
                net_h = max(0, h - lunch_h) if h > 0 else 0
                day_map[d.day if hasattr(d, 'day') else int(str(d).split('-')[2])] = round(net_h, 1)
            for d in range(1, days_in_month + 1):
                dt = _date(_year, _month, d)
                wd = dt.weekday()
                daily_hours.append({
                    'day': d,
                    'date': dt.isoformat(),
                    'hours': day_map.get(d, 0),
                    'expected': working_h if wd < 5 else 0,
                    'weekend': wd >= 5,
                })

        # Missing punch detection
        missing_punch_days = []
        if biostar:
            missing_punch_days = _overview_repo.get_missing_punch_days(
                user_id=user_id,
                biostar_user_id=biostar['biostar_user_id'],
                sincron_employee_id=sincron['sincron_employee_id'] if sincron else None,
                sincron_company=sincron['company_name'] if sincron else None,
                year=_year, month=_month,
            )

        # Daily Sincron activity codes for timeline
        daily_codes = []
        if sincron:
            code_rows = _overview_repo.get_daily_sincron_codes(
                sincron['sincron_employee_id'], sincron['company_name'], _year, _month)
            code_map: dict = {}
            for row in code_rows:
                day_num = int(row['day'])
                code_map.setdefault(day_num, {})[row['short_code']] = float(row['value'])
            for d in range(1, days_in_month + 1):
                if d in code_map:
                    daily_codes.append({'day': d, 'codes': code_map[d]})

        return jsonify({
            'success': True,
            'data': {
                'employee': employee,
                'biostar': biostar,
                'sincron': sincron,
                'connecteam': connecteam,
                'org': org,
                'bonuses': {
                    'count': bonuses.get('bonus_count', 0),
                    'total_days': float(bonuses.get('total_bonus_days', 0)),
                    'total_net': float(bonuses.get('total_bonus_net', 0)),
                },
                'forms_count': forms_count,
                'month_stats': {
                    'year': _year,
                    'month': _month,
                    'attendance': attendance,
                    'timesheet': timesheet_summary,
                    'leave_permits': leave_stats,
                    'daily_hours': daily_hours,
                    'daily_codes': daily_codes,
                    'missing_punch_days': missing_punch_days,
                },
                'leave_balance': {
                    'year': _year,
                    'annual_entitlement': 21,
                    'annual_used': ytd_leave.get('CO', {}).get('value', 0),
                    'annual_remaining': max(0, 21 - ytd_leave.get('CO', {}).get('value', 0)),
                    'sick_leave': ytd_leave.get('CM', {}).get('value', 0),
                    'unpaid_leave': ytd_leave.get('CES', {}).get('value', 0),
                    'child_care': ytd_leave.get('CIC', {}).get('value', 0),
                    'delegation': ytd_leave.get('DLG', {}).get('value', 0),
                    'sick_family': ytd_leave.get('CMS', {}).get('value', 0),
                    'ytd_permits': ytd_permits,
                },
            }
        })
    except Exception as exc:
        current_app.logger.error('Employee overview error for user %s: %s\n%s', user_id, exc, _tb.format_exc())
        return jsonify({'success': False, 'error': str(exc)}), 500


@events_bp.route('/bonuses/new')
@login_required
def add_bonus():
    """Redirect to React HR page."""
    return redirect('/app/hr')
