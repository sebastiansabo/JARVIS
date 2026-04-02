"""Sincron connector API routes."""

import logging
import threading
from flask import request, jsonify
from flask_login import current_user

from . import sincron_bp
from .services import SincronSyncService
from core.utils.api_helpers import api_login_required, admin_required, safe_error_response

logger = logging.getLogger('jarvis.sincron.routes')
service = SincronSyncService()

# Prevent concurrent syncs
_sync_lock = threading.Lock()


def _validate_year_month(year, month):
    """Validate year/month params. Returns (year, month, error_response)."""
    if year is not None and (year < 2000 or year > 2100):
        return None, None, (jsonify({'success': False, 'error': 'Invalid year'}), 400)
    if month is not None and (month < 1 or month > 12):
        return None, None, (jsonify({'success': False, 'error': 'Invalid month'}), 400)
    return year, month, None


# ── Connection Config (admin only) ──

@sincron_bp.route('/api/config', methods=['GET'])
@admin_required
def get_config():
    """Get Sincron connection configuration."""
    config = service.get_connection_config()
    return jsonify({'success': True, 'data': config})


@sincron_bp.route('/api/config', methods=['POST'])
@admin_required
def save_config():
    """Save Sincron connection configuration (company tokens)."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    company_tokens = data.get('company_tokens')
    if not company_tokens or not isinstance(company_tokens, dict):
        return jsonify({'success': False, 'error': 'company_tokens dict required'}), 400

    try:
        connector_id = service.save_connection(company_tokens)
        return jsonify({'success': True, 'message': 'Configuration saved',
                        'connector_id': connector_id})
    except Exception as e:
        return safe_error_response(e)


@sincron_bp.route('/api/test-connection', methods=['POST'])
@admin_required
def test_connection():
    """Test Sincron API connectivity for all or one company."""
    data = request.get_json(silent=True) or {}
    company_name = data.get('company_name')
    try:
        result = service.test_connection(company_name)
        return jsonify(result)
    except Exception as e:
        return safe_error_response(e)


@sincron_bp.route('/api/status', methods=['GET'])
@api_login_required
def get_status():
    """Get connector status summary."""
    try:
        status = service.get_status()
        return jsonify({'success': True, 'data': status})
    except Exception:
        return jsonify({'success': False, 'data': {
            'connected': False, 'status': 'disconnected',
            'employee_count': {'total': 0, 'mapped': 0, 'unmapped': 0, 'companies': 0},
        }})


# ── Timesheet Sync (admin only) ──

@sincron_bp.route('/api/sync/timesheets', methods=['POST'])
@admin_required
def sync_timesheets():
    """Trigger timesheet sync (runs in background)."""
    data = request.get_json(silent=True) or {}
    year = data.get('year', type=int) if hasattr(data.get('year'), '__int__') else data.get('year')
    month = data.get('month', type=int) if hasattr(data.get('month'), '__int__') else data.get('month')
    company_name = data.get('company_name')

    if year is not None or month is not None:
        year, month, err = _validate_year_month(year, month)
        if err:
            return err

    if not _sync_lock.acquire(blocking=False):
        return jsonify({'success': False, 'error': 'Sync already in progress'}), 429

    def _run():
        try:
            result = service.sync_timesheets(year, month, company_name)
            logger.info(f"Sincron sync complete: {result.get('total_employees', 0)} employees, "
                        f"{result.get('total_records', 0)} records")
        except Exception:
            logger.exception("Sincron sync crashed")
        finally:
            _sync_lock.release()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return jsonify({'success': True, 'message': 'Sync started'})


@sincron_bp.route('/api/sync/timesheets/now', methods=['POST'])
@admin_required
def sync_timesheets_sync():
    """Trigger timesheet sync (synchronous — waits for completion)."""
    data = request.get_json(silent=True) or {}
    year = data.get('year')
    month = data.get('month')
    company_name = data.get('company_name')

    if year is not None or month is not None:
        year, month, err = _validate_year_month(year, month)
        if err:
            return err

    if not _sync_lock.acquire(blocking=False):
        return jsonify({'success': False, 'error': 'Sync already in progress'}), 429

    try:
        result = service.sync_timesheets(year, month, company_name)
        return jsonify(result)
    except Exception as e:
        return safe_error_response(e)
    finally:
        _sync_lock.release()


# ── Employees (admin only for management, read-only for status) ──

@sincron_bp.route('/api/employees', methods=['GET'])
@admin_required
def get_employees():
    """Get synced Sincron employees (admin only — contains sensitive data)."""
    company = request.args.get('company')
    active_only = request.args.get('active_only', 'true').lower() == 'true'
    employees = service.get_employees(company, active_only)
    return jsonify({'success': True, 'data': employees})


@sincron_bp.route('/api/employees/stats', methods=['GET'])
@api_login_required
def get_employee_stats():
    """Get employee counts (non-sensitive aggregate)."""
    stats = service.get_employee_stats()
    return jsonify({'success': True, 'data': stats})


@sincron_bp.route('/api/employees/mapping', methods=['PUT'])
@admin_required
def update_mapping():
    """Manually map a Sincron employee to a JARVIS user."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    sincron_id = data.get('sincron_employee_id')
    company = data.get('company_name')
    jarvis_id = data.get('jarvis_user_id')
    if not sincron_id or not company or not jarvis_id:
        return jsonify({'success': False,
                        'error': 'sincron_employee_id, company_name, jarvis_user_id required'}), 400

    service.update_employee_mapping(sincron_id, company, jarvis_id)
    return jsonify({'success': True, 'message': 'Mapping updated'})


@sincron_bp.route('/api/employees/mapping', methods=['DELETE'])
@admin_required
def remove_mapping():
    """Remove JARVIS user mapping."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400

    sincron_id = data.get('sincron_employee_id')
    company = data.get('company_name')
    if not sincron_id or not company:
        return jsonify({'success': False,
                        'error': 'sincron_employee_id and company_name required'}), 400

    service.remove_employee_mapping(sincron_id, company)
    return jsonify({'success': True, 'message': 'Mapping removed'})


@sincron_bp.route('/api/employees/auto-map', methods=['POST'])
@admin_required
def auto_map():
    """Auto-map unmapped Sincron employees to JARVIS users."""
    try:
        result = service.auto_map_employees()
        return jsonify(result)
    except Exception as e:
        return safe_error_response(e)


@sincron_bp.route('/api/employees/unmapped', methods=['GET'])
@admin_required
def get_unmapped():
    """Get employees not yet mapped to JARVIS users."""
    employees = service.repo.get_unmapped_employees()
    return jsonify({'success': True, 'data': employees})


@sincron_bp.route('/api/employees/jarvis-users', methods=['GET'])
@admin_required
def get_jarvis_users():
    """Get active JARVIS users for mapping dropdown (admin only)."""
    users = service.repo.get_jarvis_users()
    return jsonify({'success': True, 'data': users})


# ── Timesheets (user-scoped) ──

@sincron_bp.route('/api/timesheets', methods=['GET'])
@api_login_required
def get_timesheet():
    """Get monthly timesheet for current user only."""
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)

    if not year or not month:
        from datetime import datetime
        now = datetime.now()
        year = year or now.year
        month = month or now.month

    year, month, err = _validate_year_month(year, month)
    if err:
        return err

    try:
        data = service.get_employee_timesheet(current_user.id, year, month)
        return jsonify({'success': True, 'data': data, 'year': year, 'month': month})
    except Exception as e:
        return safe_error_response(e)


@sincron_bp.route('/api/timesheets/employee/<int:user_id>', methods=['GET'])
@api_login_required
def get_employee_timesheet(user_id):
    """Get monthly timesheet for a specific employee (manager-scoped)."""
    from hr.events.database import get_managed_employee_ids, is_manager

    # Allow own data or manager access
    if user_id != current_user.id:
        if not is_manager(current_user.id):
            return jsonify({'success': False, 'error': 'Permission denied'}), 403
        managed_ids = get_managed_employee_ids(current_user.id)
        if user_id not in (managed_ids or []):
            return jsonify({'success': False, 'error': 'Permission denied'}), 403

    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)

    if not year or not month:
        from datetime import datetime
        now = datetime.now()
        year = year or now.year
        month = month or now.month

    year, month, err = _validate_year_month(year, month)
    if err:
        return err

    try:
        data = service.get_employee_timesheet(user_id, year, month)
        return jsonify({'success': True, 'data': data, 'year': year, 'month': month})
    except Exception as e:
        return safe_error_response(e)


@sincron_bp.route('/api/timesheets/team', methods=['GET'])
@api_login_required
def get_team_timesheet():
    """Get team timesheet summary for managed employees."""
    from hr.events.database import get_managed_employee_ids, is_manager

    if not is_manager(current_user.id):
        return jsonify({'success': True, 'is_manager': False, 'data': []})

    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    node_id = request.args.get('node_id', type=int)

    if not year or not month:
        from datetime import datetime
        now = datetime.now()
        year = year or now.year
        month = month or now.month

    year, month, err = _validate_year_month(year, month)
    if err:
        return err

    managed_ids = get_managed_employee_ids(current_user.id, node_id=node_id)
    if not managed_ids:
        return jsonify({'success': True, 'is_manager': True, 'data': [],
                        'year': year, 'month': month})

    try:
        data = service.get_team_timesheet_summary(managed_ids, year, month)
        return jsonify({'success': True, 'is_manager': True, 'data': data,
                        'year': year, 'month': month})
    except Exception as e:
        return safe_error_response(e)


# ── Activity Codes ──

@sincron_bp.route('/api/activity-codes', methods=['GET'])
@api_login_required
def get_activity_codes():
    """Get all discovered activity codes."""
    codes = service.get_activity_codes()
    return jsonify({'success': True, 'data': codes})


# ── Sync History (admin only) ──

@sincron_bp.route('/api/sync/history', methods=['GET'])
@admin_required
def get_sync_history():
    """Get recent sync runs."""
    sync_type = request.args.get('sync_type')
    limit = min(request.args.get('limit', 20, type=int), 100)
    runs = service.get_sync_history(sync_type, limit)
    return jsonify({'success': True, 'data': runs})
