"""BioStar 2 API routes."""

from datetime import datetime
from functools import wraps
from flask import request, jsonify
from flask_login import current_user

from . import biostar_bp
from .services import BioStarSyncService

service = BioStarSyncService()


def api_login_required(f):
    """Require authentication for API endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated


# ── Connection Config ──

@biostar_bp.route('/api/config', methods=['GET'])
@api_login_required
def get_config():
    """Get BioStar connection configuration."""
    config = service.get_connection_config()
    return jsonify({'success': True, 'data': config})


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
    """Trigger BioStar event sync."""
    data = request.get_json() or {}
    try:
        result = service.sync_events(
            start_date=data.get('start_date'),
            end_date=data.get('end_date'),
        )
        if result['success']:
            return jsonify(result)
        return jsonify(result), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


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
    return jsonify({'success': True, 'data': history})


@biostar_bp.route('/api/punch-logs/summary', methods=['GET'])
@api_login_required
def get_daily_summary():
    """Get per-employee daily punch summary."""
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'success': False, 'error': 'date parameter required'}), 400
    summary = service.get_daily_summary(date_str)
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
@api_login_required
def adjust_employee():
    """Manually adjust one employee's punches for a date."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    required = ['biostar_user_id', 'date', 'adjusted_first_punch', 'adjusted_last_punch',
                'original_first_punch', 'original_last_punch']
    for key in required:
        if key not in data:
            return jsonify({'success': False, 'error': f'{key} required'}), 400

    try:
        adj_first = datetime.fromisoformat(data['adjusted_first_punch'])
        adj_last = datetime.fromisoformat(data['adjusted_last_punch'])
        orig_first = datetime.fromisoformat(data['original_first_punch'])
        orig_last = datetime.fromisoformat(data['original_last_punch'])
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
@api_login_required
def auto_adjust_all():
    """Auto-adjust all off-schedule employees for a date."""
    data = request.get_json() or {}
    date_str = data.get('date')
    if not date_str:
        return jsonify({'success': False, 'error': 'date required'}), 400

    threshold = int(data.get('threshold', 15))
    result = service.auto_adjust_all(date_str, threshold, user_id=current_user.id)
    return jsonify({'success': True, 'data': result})


@biostar_bp.route('/api/adjustments/revert', methods=['POST'])
@api_login_required
def revert_adjustment():
    """Revert an adjustment (delete it)."""
    data = request.get_json() or {}
    biostar_user_id = data.get('biostar_user_id')
    date_str = data.get('date')
    if not biostar_user_id or not date_str:
        return jsonify({'success': False, 'error': 'biostar_user_id and date required'}), 400
    service.revert_adjustment(biostar_user_id, date_str)
    return jsonify({'success': True, 'message': 'Adjustment reverted'})


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
            'hour': settings.get('hour', int(job['default_schedule'].split(':')[0])),
            'minute': settings.get('minute', int(job['default_schedule'].split(':')[1])),
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
        cron_settings[job_id] = {
            'enabled': bool(job.get('enabled', True)),
            'hour': int(job.get('hour', 1)),
            'minute': int(job.get('minute', 0)),
        }
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
