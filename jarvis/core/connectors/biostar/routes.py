"""BioStar 2 API routes."""

import logging
import threading
from datetime import datetime
from functools import wraps
from flask import request, jsonify
from flask_login import current_user

from . import biostar_bp
from .services import BioStarSyncService
from core.utils.api_helpers import api_login_required

logger = logging.getLogger('jarvis.biostar.routes')
service = BioStarSyncService()


def _resolve_manager_filter():
    """Resolve pontaje visibility based on team_pontaje permission scope.

    - scope 'all':        no filter (see everyone), unless frontend passes manager_filter=true
    - scope 'department': filter by organigram-managed employees + self
    - scope 'own':        only current user's own data
    - scope 'deny':       return [-1] (deny all)
    """
    from core.roles.repositories.permission_repository import PermissionRepository

    role_id = getattr(current_user, 'role_id', None)
    explicit = request.args.get('manager_filter', '').lower() == 'true'

    if not role_id:
        return [-1]

    perm_repo = PermissionRepository()
    perm = perm_repo.check_permission_v2(role_id, 'hr', 'team_pontaje', 'view')
    has_perm = perm.get('has_permission', False)
    scope = perm.get('scope', 'deny') if has_perm else 'deny'

    if scope == 'all':
        # Admin/all: see everyone; respect explicit manager_filter toggle from frontend
        return None if not explicit else _get_managed_ids_with_self()

    if scope == 'department':
        # See own team in organigram (subordinates + self)
        return _get_managed_ids_with_self()

    if scope == 'own':
        # Only see their own punch data
        return [current_user.id]

    # scope == 'deny' or no permission
    return [-1]


def _get_managed_ids_with_self():
    """Return organigram-managed employee IDs including the current user."""
    from core.organization.hr_utils import get_managed_employee_ids
    user_ids = get_managed_employee_ids(current_user.id) or []
    # Include self so manager also sees their own punches
    if current_user.id not in user_ids:
        user_ids = [current_user.id] + user_ids
    return user_ids if user_ids else [-1]


def adjust_permission_required(f):
    """Require can_adjust_punches permission."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        if not getattr(current_user, 'can_adjust_punches', False):
            return jsonify({'success': False, 'error': 'Permission denied: adjust punches required'}), 403
        return f(*args, **kwargs)
    return decorated


# ── Connection Config ──

@biostar_bp.route('/api/config', methods=['GET'])
@api_login_required
def get_config():
    """Get BioStar connection configuration."""
    config = service.get_connection_config()
    return jsonify({'success': True, 'data': config})


@biostar_bp.route('/api/groups', methods=['GET'])
@api_login_required
def get_groups():
    """Return distinct BioStar groups with their company mapping and available companies."""
    groups = service.repo.query_all('''
        SELECT user_group_name, company_id, COUNT(*) AS employee_count
        FROM biostar_employees
        WHERE user_group_name IS NOT NULL
        GROUP BY user_group_name, company_id
        ORDER BY user_group_name
    ''')
    companies = service.repo.query_all(
        'SELECT id, company AS name FROM companies WHERE company IS NOT NULL ORDER BY company'
    )
    # Merge with saved config map (may differ from live company_id on employees table)
    saved_map = service.get_group_company_map()
    result = []
    for g in groups:
        gname = g['user_group_name']
        result.append({
            'group_name': gname,
            'company_id': saved_map.get(gname, g['company_id']),
            'employee_count': g['employee_count'],
        })
    return jsonify({'success': True, 'groups': result, 'companies': [dict(c) for c in companies]})


@biostar_bp.route('/api/group-company-map', methods=['POST'])
@api_login_required
def save_group_company_map():
    """Save group→company mapping to connector config and update biostar_employees."""
    data = request.get_json() or {}
    mapping = data.get('map', {})
    if not isinstance(mapping, dict):
        return jsonify({'success': False, 'error': 'map must be an object'}), 400
    # Coerce values to int or None
    clean = {k: (int(v) if v else None) for k, v in mapping.items()}
    service.save_group_company_map(clean)
    # Update company_id on existing employees
    updated = service.repo.update_employees_company_from_map(clean)
    return jsonify({'success': True, 'updated_employees': updated})


@biostar_bp.route('/api/config', methods=['POST'])
@api_login_required
def save_config():
    """Save BioStar connection configuration."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    host = data.get('host', '').strip()
    port = data.get('port', 443)
    login_id = data.get('login_id', '').strip()
    password = data.get('password', '').strip()

    if not host or not login_id or not password:
        return jsonify({'success': False, 'error': 'Host, login_id, and password are required'}), 400

    try:
        connector_id = service.save_connection(host, int(port), login_id, password,
                                                data.get('verify_ssl', False))
        return jsonify({'success': True, 'message': 'Configuration saved', 'connector_id': connector_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@biostar_bp.route('/api/test-connection', methods=['POST'])
@api_login_required
def test_connection():
    """Test BioStar API connectivity."""
    data = request.get_json() or {}
    try:
        result = service.test_connection(
            host=data.get('host'),
            port=data.get('port'),
            login_id=data.get('login_id'),
            password=data.get('password'),
        )
        if result['success']:
            return jsonify(result)
        return jsonify(result), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@biostar_bp.route('/api/status', methods=['GET'])
@api_login_required
def get_status():
    """Get connector status summary."""
    try:
        status = service.get_status()
        return jsonify({'success': True, 'data': status})
    except Exception as e:
        return jsonify({'success': True, 'data': {
            'connected': False, 'status': 'disconnected',
            'host': None, 'error': str(e),
            'employee_count': {'total': 0, 'active': 0, 'mapped': 0, 'unmapped': 0},
            'event_count': 0,
        }})


# ── User Sync ──

@biostar_bp.route('/api/sync/users', methods=['POST'])
@api_login_required
def sync_users():
    """Trigger BioStar user sync."""
    try:
        result = service.sync_users()
        if result['success']:
            return jsonify(result)
        return jsonify(result), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@biostar_bp.route('/api/employees', methods=['GET'])
@api_login_required
def get_employees():
    """Get synced BioStar employees."""
    active_only = request.args.get('active_only', 'true').lower() == 'true'
    employees = service.get_employees(active_only)
    return jsonify({'success': True, 'data': employees})


@biostar_bp.route('/api/employees/stats', methods=['GET'])
@api_login_required
def get_employee_stats():
    """Get employee counts (total, mapped, unmapped)."""
    stats = service.get_employee_stats()
    return jsonify({'success': True, 'data': stats})


@biostar_bp.route('/api/employees/<biostar_user_id>/mapping', methods=['PUT'])
@api_login_required
def update_mapping(biostar_user_id):
    """Manually map a BioStar employee to a JARVIS user."""
    data = request.get_json()
    if not data or 'jarvis_user_id' not in data:
        return jsonify({'success': False, 'error': 'jarvis_user_id required'}), 400
    service.update_employee_mapping(biostar_user_id, data['jarvis_user_id'])
    return jsonify({'success': True, 'message': 'Mapping updated'})


@biostar_bp.route('/api/employees/<biostar_user_id>/mapping', methods=['DELETE'])
@api_login_required
def remove_mapping(biostar_user_id):
    """Remove JARVIS user mapping."""
    service.remove_employee_mapping(biostar_user_id)
    return jsonify({'success': True, 'message': 'Mapping removed'})


@biostar_bp.route('/api/employees/bulk-schedule', methods=['PUT'])
@api_login_required
def bulk_update_schedule():
    """Bulk update schedule fields for multiple employees."""
    data = request.get_json()
    if not data or 'biostar_user_ids' not in data:
        return jsonify({'success': False, 'error': 'biostar_user_ids required'}), 400
    ids = data['biostar_user_ids']
    if not isinstance(ids, list) or len(ids) == 0:
        return jsonify({'success': False, 'error': 'biostar_user_ids must be a non-empty list'}), 400
    count = service.bulk_update_schedule(
        biostar_user_ids=ids,
        lunch_break_minutes=data.get('lunch_break_minutes'),
        working_hours=data.get('working_hours'),
        schedule_start=data.get('schedule_start'),
        schedule_end=data.get('schedule_end'),
    )
    return jsonify({'success': True, 'message': f'Updated {count} employees', 'data': {'updated': count}})


@biostar_bp.route('/api/employees/bulk-deactivate', methods=['POST'])
@api_login_required
def bulk_deactivate():
    """Deactivate (soft-delete) multiple employees."""
    data = request.get_json()
    if not data or 'biostar_user_ids' not in data:
        return jsonify({'success': False, 'error': 'biostar_user_ids required'}), 400
    ids = data['biostar_user_ids']
    if not isinstance(ids, list) or len(ids) == 0:
        return jsonify({'success': False, 'error': 'biostar_user_ids must be a non-empty list'}), 400
    count = service.bulk_deactivate(ids)
    return jsonify({'success': True, 'message': f'Deactivated {count} employees', 'data': {'deactivated': count}})


@biostar_bp.route('/api/employees/<biostar_user_id>/blacklist', methods=['POST'])
@api_login_required
def toggle_blacklist(biostar_user_id):
    """Toggle blacklist status for an employee."""
    result = service.repo.toggle_blacklist(biostar_user_id)
    new_status = result['is_blacklisted'] if result else False
    return jsonify({'success': True, 'is_blacklisted': new_status})


@biostar_bp.route('/api/employees/bulk-blacklist', methods=['POST'])
@api_login_required
def bulk_blacklist():
    """Set blacklist status for multiple employees."""
    data = request.get_json()
    if not data or 'biostar_user_ids' not in data:
        return jsonify({'success': False, 'error': 'biostar_user_ids required'}), 400
    ids = data['biostar_user_ids']
    blacklisted = data.get('blacklisted', True)
    count = service.repo.bulk_blacklist(ids, blacklisted)
    return jsonify({'success': True, 'data': {'updated': count}})


@biostar_bp.route('/api/employees/blacklist-group', methods=['POST'])
@api_login_required
def blacklist_group():
    """Blacklist all employees in a group."""
    data = request.get_json()
    group = (data or {}).get('group_name', '').strip()
    if not group:
        return jsonify({'success': False, 'error': 'group_name required'}), 400
    blacklisted = (data or {}).get('blacklisted', True)
    count = service.repo.blacklist_group(group, blacklisted)
    return jsonify({'success': True, 'data': {'updated': count}})


@biostar_bp.route('/api/employees/<biostar_user_id>/schedule', methods=['PUT'])
@api_login_required
def update_schedule(biostar_user_id):
    """Update work schedule (lunch break, working hours) for an employee."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    lunch = data.get('lunch_break_minutes', 60)
    hours = data.get('working_hours', 8.0)
    start = data.get('schedule_start')
    end = data.get('schedule_end')
    service.update_employee_schedule(biostar_user_id, int(lunch), float(hours), start, end)
    return jsonify({'success': True, 'message': 'Schedule updated'})


# ── Event Sync ──

@biostar_bp.route('/api/sync/events', methods=['POST'])
@api_login_required
def sync_events():
    """Trigger BioStar event sync (runs in background to avoid HTTP timeout)."""
    data = request.get_json(silent=True) or {}
    start_date = data.get('start_date')
    end_date = data.get('end_date')

    def _run():
        try:
            result = service.sync_events(start_date=start_date, end_date=end_date)
            if result.get('success'):
                d = result.get('data', {})
                logger.info(f"Manual event sync complete: {d.get('inserted', 0)} new, {d.get('skipped', 0)} skipped")
            else:
                logger.warning(f"Manual event sync failed: {result.get('error', 'unknown')}")
        except Exception:
            logger.exception("Manual event sync crashed")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return jsonify({'success': True, 'message': 'Sync started'})


@biostar_bp.route('/api/punch-logs', methods=['GET'])
@api_login_required
def get_punch_logs():
    """Get punch logs with optional filters."""
    result = service.get_punch_logs(
        biostar_user_id=request.args.get('user_id'),
        start_date=request.args.get('start'),
        end_date=request.args.get('end'),
        limit=int(request.args.get('limit', 100)),
        offset=int(request.args.get('offset', 0)),
    )
    return jsonify({'success': True, 'data': result['logs'], 'total': result['total']})


@biostar_bp.route('/api/punch-logs/employee/<biostar_user_id>', methods=['GET'])
@api_login_required
def get_employee_punches(biostar_user_id):
    """Get all punches for one employee on a date."""
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'success': False, 'error': 'date parameter required'}), 400
    punches = service.get_employee_punches(biostar_user_id, date_str)
    return jsonify({'success': True, 'data': punches})


@biostar_bp.route('/api/employees/<biostar_user_id>/profile', methods=['GET'])
@api_login_required
def get_employee_profile(biostar_user_id):
    """Get employee profile with mapping info."""
    employee = service.get_employee_profile(biostar_user_id)
    if not employee:
        return jsonify({'success': False, 'error': 'Employee not found'}), 404
    return jsonify({'success': True, 'data': employee})


@biostar_bp.route('/api/employees/<biostar_user_id>/daily-history', methods=['GET'])
@api_login_required
def get_employee_daily_history(biostar_user_id):
    """Get per-day punch summaries for one employee over a date range."""
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    if not start_date or not end_date:
        return jsonify({'success': False, 'error': 'start and end date parameters required'}), 400
    history = service.get_employee_daily_history(biostar_user_id, start_date, end_date)

    # Include public holidays for the date range
    holidays = []
    try:
        from core.utils.holidays_repository import HolidayRepository
        _hol_repo = HolidayRepository()
        _holiday_dates = set()
        for _yr in range(int(start_date[:4]), int(end_date[:4]) + 1):
            for h in _hol_repo.get_holidays_for_year(_yr):
                d = h['date']
                _holiday_dates.add(d.isoformat() if hasattr(d, 'isoformat') else str(d))
        holidays = sorted(_holiday_dates)
    except Exception:
        pass

    return jsonify({'success': True, 'data': history, 'holidays': holidays})


# ── Attendance Overview (stable employee list) ──

@biostar_bp.route('/api/attendance/today', methods=['GET'])
@api_login_required
def get_attendance_today():
    """Get attendance overview with ALL active employees for a date."""
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'success': False, 'error': 'date parameter required'}), 400
    jarvis_user_ids = _resolve_manager_filter()
    data = service.get_attendance_overview(date_str, jarvis_user_ids=jarvis_user_ids)
    return jsonify({'success': True, 'data': data})


@biostar_bp.route('/api/attendance/week', methods=['GET'])
@api_login_required
def get_attendance_week():
    """Get 7-day attendance summary with ALL active employees."""
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'success': False, 'error': 'date parameter required'}), 400
    jarvis_user_ids = _resolve_manager_filter()
    data = service.get_attendance_week(date_str, jarvis_user_ids=jarvis_user_ids)
    return jsonify({'success': True, 'data': data})


@biostar_bp.route('/api/punch-logs/summary', methods=['GET'])
@api_login_required
def get_daily_summary():
    """Get per-employee daily punch summary."""
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'success': False, 'error': 'date parameter required'}), 400
    jarvis_user_ids = _resolve_manager_filter()
    summary = service.get_daily_summary(date_str, jarvis_user_ids=jarvis_user_ids)
    return jsonify({'success': True, 'data': summary})


@biostar_bp.route('/api/punch-logs/range-summary', methods=['GET'])
@api_login_required
def get_range_summary():
    """Get per-employee aggregated summary over a date range."""
    start = request.args.get('start')
    end = request.args.get('end')
    if not start or not end:
        return jsonify({'success': False, 'error': 'start and end parameters required'}), 400
    jarvis_user_ids = _resolve_manager_filter()
    summary = service.get_range_summary(start, end, jarvis_user_ids=jarvis_user_ids)
    return jsonify({'success': True, 'data': summary})


# ── Sync History ──

@biostar_bp.route('/api/sync/history', methods=['GET'])
@api_login_required
def get_sync_history():
    """Get recent sync runs."""
    sync_type = request.args.get('sync_type')
    limit = int(request.args.get('limit', 20))
    runs = service.get_sync_history(sync_type, limit)
    return jsonify({'success': True, 'data': runs})


@biostar_bp.route('/api/sync/errors/<run_id>', methods=['GET'])
@api_login_required
def get_sync_errors(run_id):
    """Get errors for a specific sync run."""
    errors = service.get_sync_errors(run_id)
    return jsonify({'success': True, 'data': errors})


# ── Schedule Adjustments ──

@biostar_bp.route('/api/adjustments/off-schedule', methods=['GET'])
@api_login_required
def get_off_schedule():
    """Get employees whose punches deviate from schedule."""
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'success': False, 'error': 'date parameter required'}), 400
    threshold = int(request.args.get('threshold', 15))
    rows = service.get_off_schedule_employees(date_str, threshold)
    return jsonify({'success': True, 'data': rows})


@biostar_bp.route('/api/adjustments', methods=['GET'])
@api_login_required
def get_adjustments():
    """Get all adjustments for a date."""
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'success': False, 'error': 'date parameter required'}), 400
    rows = service.get_adjustments(date_str)
    return jsonify({'success': True, 'data': rows})


@biostar_bp.route('/api/adjustments/adjust', methods=['POST'])
@adjust_permission_required
def adjust_employee():
    """Manually adjust one employee's punches for a date."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    required = ['biostar_user_id', 'date', 'adjusted_first_punch', 'adjusted_last_punch']
    for key in required:
        if key not in data:
            return jsonify({'success': False, 'error': f'{key} required'}), 400

    try:
        adj_first = datetime.fromisoformat(data['adjusted_first_punch'])
        adj_last = datetime.fromisoformat(data['adjusted_last_punch'])
        orig_first = datetime.fromisoformat(data['original_first_punch']) if data.get('original_first_punch') else None
        orig_last = datetime.fromisoformat(data['original_last_punch']) if data.get('original_last_punch') else None
    except (ValueError, TypeError) as e:
        return jsonify({'success': False, 'error': f'Invalid datetime: {e}'}), 400

    result = service.adjust_employee(
        biostar_user_id=data['biostar_user_id'],
        date_str=data['date'],
        adjusted_first=adj_first,
        adjusted_last=adj_last,
        original_first=orig_first,
        original_last=orig_last,
        schedule_start=data.get('schedule_start'),
        schedule_end=data.get('schedule_end'),
        lunch_break_minutes=data.get('lunch_break_minutes', 60),
        working_hours=data.get('working_hours', 8),
        original_duration=data.get('original_duration_seconds'),
        deviation_in=data.get('deviation_minutes_in', 0),
        deviation_out=data.get('deviation_minutes_out', 0),
        adjustment_type='manual',
        adjusted_by=current_user.id,
        notes=data.get('notes'),
    )
    return jsonify({'success': True, 'message': 'Adjustment saved', 'data': result})


@biostar_bp.route('/api/adjustments/auto-adjust', methods=['POST'])
@adjust_permission_required
def auto_adjust_all():
    """Auto-adjust all off-schedule employees for a date."""
    data = request.get_json() or {}
    date_str = data.get('date')
    if not date_str:
        return jsonify({'success': False, 'error': 'date required'}), 400

    threshold = int(data.get('threshold', 15))
    result = service.auto_adjust_all(date_str, threshold, user_id=current_user.id)
    return jsonify({'success': True, 'data': result})


@biostar_bp.route('/api/adjustments/auto-adjust-single', methods=['POST'])
@adjust_permission_required
def auto_adjust_single():
    """Auto-adjust a single employee for a specific date using Sincron per-day schedule.

    Optional company_name in body: if provided, only adjust that company interval.
    """
    data = request.get_json() or {}
    biostar_user_id = data.get('biostar_user_id')
    date_str = data.get('date')
    company_name = data.get('company_name')  # optional: per-company adjustment
    if not biostar_user_id or not date_str:
        return jsonify({'success': False, 'error': 'biostar_user_id and date required'}), 400
    result = service.auto_adjust_single(biostar_user_id, date_str,
                                        user_id=current_user.id,
                                        company_name=company_name)
    if not result.get('success'):
        return jsonify(result), 400
    return jsonify({'success': True, 'data': result})


@biostar_bp.route('/api/attendance/punches-by-interval', methods=['GET'])
@api_login_required
def get_punches_by_interval():
    """Get per-company interval punch split for a multi-contract employee.

    Query params: biostar_user_id, date
    Returns intervals with split punches + any per-company adjustments.
    """
    biostar_user_id = request.args.get('biostar_user_id')
    date_str = request.args.get('date')
    if not biostar_user_id or not date_str:
        return jsonify({'success': False, 'error': 'biostar_user_id and date required'}), 400

    # Get the employee's JARVIS mapping
    employee = service.repo.get_employee_by_biostar_id(biostar_user_id)
    if not employee or not employee.get('mapped_jarvis_user_id'):
        return jsonify({'success': True, 'intervals': []})

    jarvis_uid = employee['mapped_jarvis_user_id']

    # Get Sincron intervals for the date
    from core.connectors.sincron.repositories.sincron_repository import SincronRepository
    sincron_repo = SincronRepository()
    intervals = sincron_repo.get_day_intervals_by_jarvis_user(jarvis_uid, date_str)

    if not intervals or len(intervals) <= 1:
        return jsonify({'success': True, 'intervals': []})

    # Split punches into intervals
    split = service.repo.get_employee_punches_by_interval(biostar_user_id, date_str, intervals)

    # Fetch per-company adjustments
    adj_rows = service.adj_repo.query_all('''
        SELECT company_name, adjusted_first_punch, adjusted_last_punch, adjustment_type
        FROM biostar_daily_adjustments
        WHERE biostar_user_id = %s AND date = %s::date AND company_name IS NOT NULL
    ''', (biostar_user_id, date_str))
    adj_map = {r['company_name']: r for r in adj_rows} if adj_rows else {}

    # Merge adjustments into split results
    for iv in split:
        adj = adj_map.get(iv['company'])
        if adj:
            iv['adjusted_first_punch'] = str(adj['adjusted_first_punch']) if adj['adjusted_first_punch'] else None
            iv['adjusted_last_punch'] = str(adj['adjusted_last_punch']) if adj['adjusted_last_punch'] else None
            iv['adjustment_type'] = adj['adjustment_type']
        else:
            iv['adjusted_first_punch'] = None
            iv['adjusted_last_punch'] = None
            iv['adjustment_type'] = None

    return jsonify({'success': True, 'intervals': split})


@biostar_bp.route('/api/attendance/batch-intervals', methods=['POST'])
@api_login_required
def batch_intervals():
    """Get per-company interval punch split for multiple employees on a given date.

    Body: { date, biostar_user_ids: string[] }
    Returns: { success, data: { [biostar_user_id]: CompanyInterval[] } }
    Only returns entries for multi-contract employees (>1 interval).
    """
    body = request.get_json(force=True) or {}
    date_str = body.get('date')
    biostar_user_ids = body.get('biostar_user_ids', [])
    if not date_str or not biostar_user_ids:
        return jsonify({'success': False, 'error': 'date and biostar_user_ids required'}), 400

    from core.connectors.sincron.repositories.sincron_repository import SincronRepository
    sincron_repo = SincronRepository()

    result = {}
    # Build jarvis mapping cache
    jarvis_map = {}
    for buid in biostar_user_ids:
        emp = service.repo.get_employee_by_biostar_id(buid)
        if emp and emp.get('mapped_jarvis_user_id'):
            jarvis_map[buid] = emp['mapped_jarvis_user_id']

    # For each mapped employee, check if multi-contract and split
    for buid, jarvis_uid in jarvis_map.items():
        intervals = sincron_repo.get_day_intervals_by_jarvis_user(jarvis_uid, date_str)
        if not intervals or len(intervals) <= 1:
            continue

        split = service.repo.get_employee_punches_by_interval(buid, date_str, intervals)

        # Merge adjustments
        adj_rows = service.adj_repo.query_all('''
            SELECT company_name, adjusted_first_punch, adjusted_last_punch, adjustment_type
            FROM biostar_daily_adjustments
            WHERE biostar_user_id = %s AND date = %s::date AND company_name IS NOT NULL
        ''', (buid, date_str))
        adj_map = {r['company_name']: r for r in adj_rows} if adj_rows else {}

        for iv in split:
            adj = adj_map.get(iv['company'])
            if adj:
                iv['adjusted_first_punch'] = str(adj['adjusted_first_punch']) if adj['adjusted_first_punch'] else None
                iv['adjusted_last_punch'] = str(adj['adjusted_last_punch']) if adj['adjusted_last_punch'] else None
                iv['adjustment_type'] = adj['adjustment_type']
            else:
                iv['adjusted_first_punch'] = None
                iv['adjusted_last_punch'] = None
                iv['adjustment_type'] = None

        result[buid] = split

    return jsonify({'success': True, 'data': result})


@biostar_bp.route('/api/employees/<biostar_user_id>/sincron-schedule', methods=['GET'])
@api_login_required
def get_employee_sincron_schedule(biostar_user_id):
    """Get Sincron contract schedule data for a BioStar employee."""
    employee = service.repo.get_employee_by_biostar_id(biostar_user_id)
    if not employee or not employee.get('mapped_jarvis_user_id'):
        return jsonify({'success': True, 'contracts': []})

    from core.connectors.sincron.repositories.sincron_repository import SincronRepository
    sincron_repo = SincronRepository()
    entries = sincron_repo.get_all_employees_by_jarvis_id(employee['mapped_jarvis_user_id'])

    # Canonical company names from companies table
    co_map = {r['id']: r['company'] for r in sincron_repo.query_all("SELECT id, company FROM companies")}

    contracts = []
    for se in entries:
        norma = float(se['norma_lucru']) if se.get('norma_lucru') else None
        contracts.append({
            'company_name': co_map.get(se.get('company_id'), se.get('company_name')),
            'nr_contract': se.get('nr_contract'),
            'data_incepere_contract': str(se['data_incepere_contract']) if se.get('data_incepere_contract') and str(se['data_incepere_contract']) > '0001' else None,
            'norma_lucru': norma,
            'schedule_start': str(se['schedule_start'])[:5] if se.get('schedule_start') else None,
            'schedule_end': str(se['schedule_end'])[:5] if se.get('schedule_end') else None,
            'lunch_break_minutes': se.get('lunch_break_minutes'),
            'count_for_leave': se.get('count_for_leave', True),
            'exclude_from_pontaje': se.get('exclude_from_pontaje', False),
            'is_base_contract': se.get('is_base_contract', False),
            'sincron_employee_db_id': se.get('id'),
        })
    return jsonify({'success': True, 'contracts': contracts})


@biostar_bp.route('/api/employees/<biostar_user_id>/sincron-timesheet', methods=['GET'])
@api_login_required
def get_employee_sincron_timesheet(biostar_user_id):
    """Get Sincron monthly timesheet + contracts for a BioStar employee."""
    employee = service.repo.get_employee_by_biostar_id(biostar_user_id)
    if not employee or not employee.get('mapped_jarvis_user_id'):
        return jsonify({'success': True, 'contracts': [], 'timesheet': []})

    jarvis_id = employee['mapped_jarvis_user_id']
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    if not year or not month or month < 1 or month > 12:
        return jsonify({'success': False, 'error': 'year and month required'}), 400

    from core.connectors.sincron.repositories.sincron_repository import SincronRepository
    sincron_repo = SincronRepository()

    entries = sincron_repo.get_all_employees_by_jarvis_id(jarvis_id)

    # Canonical company names from companies table
    co_map = {r['id']: r['company'] for r in sincron_repo.query_all("SELECT id, company FROM companies")}

    contracts = []
    for se in entries:
        norma = float(se['norma_lucru']) if se.get('norma_lucru') else None
        contracts.append({
            'company_name': co_map.get(se.get('company_id'), se.get('company_name')),
            'nr_contract': se.get('nr_contract'),
            'norma_lucru': norma,
            'schedule_start': str(se['schedule_start'])[:5] if se.get('schedule_start') else None,
            'schedule_end': str(se['schedule_end'])[:5] if se.get('schedule_end') else None,
            'lunch_break_minutes': se.get('lunch_break_minutes'),
            'count_for_leave': se.get('count_for_leave', True),
            'exclude_from_pontaje': se.get('exclude_from_pontaje', False),
            'is_base_contract': se.get('is_base_contract', False),
            'sincron_employee_db_id': se.get('id'),
        })

    rows = sincron_repo.get_timesheet_by_jarvis_user(jarvis_id, year, month)
    timesheet = []
    for r in rows:
        timesheet.append({
            'day': str(r['day']),
            'short_code': r.get('short_code'),
            'company_name': r.get('company_name'),
            'program_in': str(r['program_in'])[:5] if r.get('program_in') else None,
            'program_out': str(r['program_out'])[:5] if r.get('program_out') else None,
            'program_break': r.get('program_break'),
        })

    return jsonify({'success': True, 'contracts': contracts, 'timesheet': timesheet})


@biostar_bp.route('/api/adjustments/revert', methods=['POST'])
@adjust_permission_required
def revert_adjustment():
    """Revert an adjustment (delete it).

    Optional company_name: if provided, only revert that company's adjustment.
    If omitted, reverts ALL adjustments for that user/date.
    """
    data = request.get_json() or {}
    biostar_user_id = data.get('biostar_user_id')
    date_str = data.get('date')
    company_name = data.get('company_name')
    if not biostar_user_id or not date_str:
        return jsonify({'success': False, 'error': 'biostar_user_id and date required'}), 400
    service.revert_adjustment(biostar_user_id, date_str, company_name=company_name)
    return jsonify({'success': True, 'message': 'Adjustment reverted'})


@biostar_bp.route('/api/adjustments/revert-range', methods=['POST'])
@adjust_permission_required
def revert_adjustments_range():
    """Revert all auto-adjustments in a date range."""
    data = request.get_json() or {}
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    if not start_date or not end_date:
        return jsonify({'success': False, 'error': 'start_date and end_date required'}), 400
    service.revert_adjustments_range(start_date, end_date)
    return jsonify({'success': True, 'message': f'Reverted auto-adjustments from {start_date} to {end_date}'})


@biostar_bp.route('/api/adjustments/backfill', methods=['POST'])
@adjust_permission_required
def backfill_adjustments():
    """Auto-adjust all past dates with unadjusted off-schedule employees."""
    data = request.get_json() or {}
    threshold = int(data.get('threshold', 15))
    result = service.backfill_adjustments(threshold, user_id=current_user.id)
    return jsonify({'success': True, 'data': result})


@biostar_bp.route('/api/employees/<biostar_user_id>/adjustment-history', methods=['GET'])
@api_login_required
def get_adjustment_history(biostar_user_id):
    """Get adjustment history for one employee (audit trail)."""
    start = request.args.get('start')
    end = request.args.get('end')
    history = service.get_employee_adjustment_history(biostar_user_id, start, end)
    return jsonify({'success': True, 'data': history})


# ── Device Directions ──

@biostar_bp.route('/api/devices', methods=['GET'])
@api_login_required
def get_devices():
    """Get all unique devices from punch logs with stats and configured directions."""
    devices = service.get_devices()
    directions = service.get_device_directions()
    for d in devices:
        d['direction'] = directions.get(d['device_name'])
    return jsonify({'success': True, 'data': devices})


@biostar_bp.route('/api/device-directions', methods=['GET'])
@api_login_required
def get_device_directions():
    """Get device→direction mapping."""
    directions = service.get_device_directions()
    return jsonify({'success': True, 'data': directions})


@biostar_bp.route('/api/device-directions', methods=['PUT'])
@api_login_required
def save_device_directions():
    """Save device→direction mapping and optionally backfill existing punch logs."""
    data = request.get_json()
    if not data or 'directions' not in data:
        return jsonify({'success': False, 'error': 'directions dict required'}), 400

    directions = data['directions']
    # Validate: values must be IN, OUT, or null
    for device, direction in directions.items():
        if direction is not None and direction not in ('IN', 'OUT'):
            return jsonify({'success': False, 'error': f'Invalid direction for {device}: must be IN, OUT, or null'}), 400

    # Remove null entries
    clean = {k: v for k, v in directions.items() if v is not None}
    service.save_device_directions(clean)

    # Optionally backfill existing records
    backfilled = 0
    if data.get('backfill', False):
        backfilled = service.backfill_directions(clean)

    return jsonify({
        'success': True,
        'message': f'Device directions saved. {backfilled} punch logs updated.' if backfilled else 'Device directions saved.',
        'data': {'backfilled': backfilled},
    })


@biostar_bp.route('/api/device-directions/backfill', methods=['POST'])
@api_login_required
def backfill_directions():
    """Backfill direction on all existing punch logs based on configured device mapping."""
    updated = service.backfill_directions()
    return jsonify({
        'success': True,
        'message': f'{updated} punch logs updated',
        'data': {'updated': updated},
    })


# ── Cron Job Settings ──

BIOSTAR_CRON_JOBS = [
    {'id': 'biostar_sync_events', 'label': 'Sync Events', 'description': 'Incremental punch log sync', 'default_schedule': '01:00'},
    {'id': 'biostar_sync_users', 'label': 'Sync Users', 'description': 'Full user sync + auto-mapping', 'default_schedule': '02:00'},
    {'id': 'biostar_auto_adjust', 'label': 'Auto-Adjust', 'description': "Auto-adjust yesterday's off-schedule punches", 'default_schedule': '03:00'},
]


@biostar_bp.route('/api/cron-jobs', methods=['GET'])
@api_login_required
def get_cron_jobs():
    """Get BioStar cron job settings."""
    import json as _json
    connector = service.connector_repo.get_by_type('biostar')
    config = {}
    if connector:
        raw = connector.get('config') or {}
        config = _json.loads(raw) if isinstance(raw, str) else raw

    cron_settings = config.get('cron_jobs', {})
    jobs = []
    for job in BIOSTAR_CRON_JOBS:
        settings = cron_settings.get(job['id'], {})
        jobs.append({
            'id': job['id'],
            'label': job['label'],
            'description': job['description'],
            'enabled': settings.get('enabled', True),
            'schedule_type': settings.get('schedule_type', 'cron'),
            'hour': settings.get('hour', int(job['default_schedule'].split(':')[0])),
            'minute': settings.get('minute', int(job['default_schedule'].split(':')[1])),
            'interval_minutes': settings.get('interval_minutes'),
            'last_run': settings.get('last_run'),
            'last_success': settings.get('last_success'),
            'last_message': settings.get('last_message'),
        })
    return jsonify({'success': True, 'data': jobs})


@biostar_bp.route('/api/cron-jobs', methods=['PUT'])
@api_login_required
def update_cron_jobs():
    """Update BioStar cron job settings and reschedule."""
    import json as _json
    data = request.get_json()
    if not data or 'jobs' not in data:
        return jsonify({'success': False, 'error': 'jobs array required'}), 400

    connector = service.connector_repo.get_by_type('biostar')
    if not connector:
        return jsonify({'success': False, 'error': 'BioStar connector not configured'}), 400

    raw = connector.get('config') or {}
    config = _json.loads(raw) if isinstance(raw, str) else raw

    cron_settings = config.get('cron_jobs', {})
    for job in data['jobs']:
        job_id = job.get('id')
        if not job_id:
            continue
        entry = {
            'enabled': bool(job.get('enabled', True)),
            'hour': int(job.get('hour', 1)),
            'minute': int(job.get('minute', 0)),
        }
        if job.get('schedule_type') == 'interval':
            entry['schedule_type'] = 'interval'
            entry['interval_minutes'] = int(job.get('interval_minutes', 60))
        else:
            entry['schedule_type'] = 'cron'
        # Preserve last_run info
        existing = cron_settings.get(job_id, {})
        for key in ('last_run', 'last_success', 'last_message'):
            if key in existing:
                entry[key] = existing[key]
        cron_settings[job_id] = entry
    config['cron_jobs'] = cron_settings
    service.connector_repo.update(connector['id'], config=config)

    # Reschedule jobs in the running scheduler
    try:
        from tasks.cleanup import scheduler
        if scheduler.running:
            from tasks.cleanup import sync_biostar_events, sync_biostar_users, auto_adjust_biostar_schedules
            job_funcs = {
                'biostar_sync_events': sync_biostar_events,
                'biostar_sync_users': sync_biostar_users,
                'biostar_auto_adjust': auto_adjust_biostar_schedules,
            }
            for job_id, settings in cron_settings.items():
                if job_id not in job_funcs:
                    continue
                try:
                    scheduler.remove_job(job_id)
                except Exception:
                    pass
                if settings.get('enabled', True):
                    if settings.get('schedule_type') == 'interval':
                        scheduler.add_job(
                            job_funcs[job_id],
                            'interval',
                            minutes=settings.get('interval_minutes', 60),
                            id=job_id,
                            replace_existing=True,
                            misfire_grace_time=300,
                            coalesce=True,
                        )
                    else:
                        scheduler.add_job(
                            job_funcs[job_id],
                            'cron',
                            hour=settings['hour'],
                            minute=settings['minute'],
                            id=job_id,
                            replace_existing=True,
                            misfire_grace_time=300,
                            coalesce=True,
                        )
    except Exception:
        pass  # Scheduler may not be running in dev

    return jsonify({'success': True, 'message': 'Cron jobs updated'})


# ── JARVIS Users (for mapping dropdown) ──

@biostar_bp.route('/api/employees/jarvis-users', methods=['GET'])
@api_login_required
def get_jarvis_users():
    """Get all active JARVIS users for mapping dropdown."""
    users = service.repo.get_jarvis_users()
    return jsonify({'success': True, 'data': users})


@biostar_bp.route('/api/employee-by-user/<int:user_id>', methods=['GET'])
@api_login_required
def get_employee_by_jarvis_user(user_id):
    """Look up BioStar employee by JARVIS user ID."""
    employee = service.repo.get_employee_by_jarvis_user(user_id)
    if not employee:
        return jsonify({'success': True, 'data': None})

    if employee.get('schedule_start') and hasattr(employee['schedule_start'], 'isoformat'):
        employee['schedule_start'] = str(employee['schedule_start'])
    if employee.get('schedule_end') and hasattr(employee['schedule_end'], 'isoformat'):
        employee['schedule_end'] = str(employee['schedule_end'])

    return jsonify({'success': True, 'data': employee})


# ── Admin: manual digest triggers ───────────────────────────────

def _check_admin_token():
    """Check for admin trigger token (X-Admin-Token header or ?token= param)."""
    import os
    expected = os.environ.get('ADMIN_TRIGGER_TOKEN', 'jarvis-trigger-2026')
    token = request.headers.get('X-Admin-Token') or request.args.get('token')
    return token == expected


@biostar_bp.route('/api/trigger-daily-digest', methods=['POST'])
def api_trigger_daily_digest():
    """Manually trigger the daily pontaje digest (admin token required)."""
    if not _check_admin_token():
        return jsonify({'success': False, 'error': 'Invalid token'}), 403
    try:
        import importlib
        mod = importlib.import_module('tasks.hr_attendance')
        mod.send_pontaje_digest()
        return jsonify({'success': True, 'message': 'Daily pontaje digest triggered'})
    except Exception as e:
        logger.error(f"Manual daily digest trigger failed: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@biostar_bp.route('/api/trigger-monthly-digest', methods=['POST'])
def api_trigger_monthly_digest():
    """Manually trigger the monthly pontaje summary (admin token required)."""
    if not _check_admin_token():
        return jsonify({'success': False, 'error': 'Invalid token'}), 403
    try:
        import importlib
        mod = importlib.import_module('tasks.hr_attendance')
        mod.send_monthly_pontaje_summary()
        return jsonify({'success': True, 'message': 'Monthly pontaje summary triggered'})
    except Exception as e:
        logger.error(f"Manual monthly digest trigger failed: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@biostar_bp.route('/api/trigger-hr-weekly-digest', methods=['POST'])
def api_trigger_hr_weekly_digest():
    """Manually trigger the HR weekly digest."""
    if not _check_admin_token():
        return jsonify({'success': False, 'error': 'Invalid token'}), 403
    try:
        import importlib
        mod = importlib.import_module('tasks.hr_attendance')
        mod.send_hr_weekly_digest()
        return jsonify({'success': True, 'message': 'HR weekly digest triggered'})
    except Exception as e:
        logger.error(f"Manual HR weekly digest trigger failed: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@biostar_bp.route('/api/test-smtp', methods=['POST'])
def api_test_smtp():
    """Quick SMTP connectivity test from the server (admin token required)."""
    if not _check_admin_token():
        return jsonify({'success': False, 'error': 'Invalid token'}), 403
    try:
        from core.services.notification_service import send_email, is_smtp_configured
        if not is_smtp_configured():
            return jsonify({'success': False, 'error': 'SMTP not configured'})
        to = request.args.get('to', 'sebastian.sabo@gmail.com')
        ok, err = send_email(
            to_email=to,
            subject='JARVIS SMTP Test',
            html_body='If you see this, SMTP works from the staging server.',
            skip_global_cc=True,
        )
        return jsonify({'success': ok, 'error': err or None})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
