"""Sincron connector API routes."""

import logging
import threading
from flask import request, jsonify, g
from flask_login import current_user

from . import sincron_bp
from .services import SincronSyncService
from core.utils.api_helpers import api_login_required, admin_required, safe_error_response
from core.roles.decorators import v2_permission_required

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
@api_login_required
def sync_timesheets():
    """Trigger timesheet sync (runs in background)."""
    if not getattr(current_user, 'can_access_hr', False) and not getattr(current_user, 'can_access_settings', False):
        return jsonify({'success': False, 'error': 'HR access required'}), 403
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


@sincron_bp.route('/api/employees/<int:sincron_employee_id>/count-for-leave', methods=['PUT'])
@api_login_required
def toggle_count_for_leave(sincron_employee_id):
    """Toggle count_for_leave flag on a Sincron employee contract."""
    data = request.get_json()
    if data is None or 'count_for_leave' not in data:
        return jsonify({'success': False, 'error': 'count_for_leave required'}), 400
    val = bool(data['count_for_leave'])
    service.repo.execute('''
        UPDATE sincron_employees SET count_for_leave = %s, updated_at = NOW()
        WHERE id = %s
    ''', (val, sincron_employee_id))
    return jsonify({'success': True, 'count_for_leave': val})


@sincron_bp.route('/api/employees/<int:sincron_employee_id>/exclude-from-pontaje', methods=['PUT'])
@api_login_required
def toggle_exclude_from_pontaje(sincron_employee_id):
    """Toggle exclude_from_pontaje flag on a Sincron employee contract."""
    data = request.get_json()
    if data is None or 'exclude_from_pontaje' not in data:
        return jsonify({'success': False, 'error': 'exclude_from_pontaje required'}), 400
    val = bool(data['exclude_from_pontaje'])
    service.repo.execute('''
        UPDATE sincron_employees SET exclude_from_pontaje = %s, updated_at = NOW()
        WHERE id = %s
    ''', (val, sincron_employee_id))
    return jsonify({'success': True, 'exclude_from_pontaje': val})


@sincron_bp.route('/api/employees/<int:sincron_employee_id>/department', methods=['PUT'])
@admin_required
def update_department(sincron_employee_id):
    """Update department on a Sincron employee (for organigram)."""
    data = request.get_json()
    if data is None or 'department' not in data:
        return jsonify({'success': False, 'error': 'department required'}), 400
    val = (data['department'] or '').strip() or None
    service.repo.execute('''
        UPDATE sincron_employees SET department = %s, updated_at = NOW()
        WHERE id = %s
    ''', (val, sincron_employee_id))
    return jsonify({'success': True, 'department': val})


@sincron_bp.route('/api/employees/contract-stats', methods=['GET'])
@admin_required
def get_contract_stats():
    """Get aggregate stats for base vs secondary contract toggles."""
    row = service.repo.query_one('''
        SELECT
            COUNT(*) FILTER (WHERE is_base_contract = TRUE) AS base_count,
            COUNT(*) FILTER (WHERE is_base_contract = FALSE) AS secondary_count,
            COUNT(*) FILTER (WHERE is_base_contract = FALSE AND count_for_leave = TRUE) AS secondary_leave_on,
            COUNT(*) FILTER (WHERE is_base_contract = FALSE AND exclude_from_pontaje = FALSE) AS secondary_pontaje_on
        FROM sincron_employees
        WHERE is_active = TRUE
    ''')
    return jsonify({'success': True, 'data': dict(row) if row else {}})


@sincron_bp.route('/api/employees/bulk-toggle', methods=['POST'])
@admin_required
def bulk_toggle_secondary():
    """Bulk toggle count_for_leave or exclude_from_pontaje on all secondary contracts."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Request body required'}), 400

    field = data.get('field')
    value = data.get('value')
    if field not in ('count_for_leave', 'exclude_from_pontaje') or value is None:
        return jsonify({'success': False, 'error': 'field (count_for_leave|exclude_from_pontaje) and value required'}), 400

    val = bool(value)
    count = service.repo.execute(f'''
        UPDATE sincron_employees SET {field} = %s, updated_at = NOW()
        WHERE is_active = TRUE AND is_base_contract = FALSE
    ''', (val,))
    return jsonify({'success': True, 'field': field, 'value': val, 'updated': count or 0})


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
@v2_permission_required('hr', 'timesheets', 'view')
def get_employee_timesheet(user_id):
    """Get monthly timesheet for a specific employee (V2 permission scoped)."""
    from core.organization.hr_utils import get_managed_employee_ids

    scope = getattr(g, 'permission_scope', 'all')

    # Allow own data always; for others, check scope
    if user_id != current_user.id:
        if scope == 'own':
            return jsonify({'success': False, 'error': 'Permission denied'}), 403
        if scope == 'department':
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


@sincron_bp.route('/api/timesheets/bulk-day-codes', methods=['GET'])
@api_login_required
def get_bulk_day_codes():
    """Bulk Sincron leave day codes for multiple users — HR export use.

    Query params: user_ids (comma-separated), year, month.
    Returns { data: { user_id: { "YYYY-MM-DD": "CO", ... }, ... } }
    """
    if not getattr(current_user, 'can_access_hr', False):
        return jsonify({'success': False, 'error': 'HR access required'}), 403

    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    user_ids_raw = request.args.get('user_ids', '')

    if not year or not month or not user_ids_raw:
        return jsonify({'success': False, 'error': 'year, month, user_ids required'}), 400

    try:
        user_ids = [int(x) for x in user_ids_raw.split(',') if x.strip()]
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid user_ids'}), 400

    year, month, err = _validate_year_month(year, month)
    if err:
        return err

    try:
        from .repositories.sincron_repository import SincronRepository
        repo = SincronRepository()
        rows = repo.get_day_codes_for_users(user_ids, year, month)

        result: dict = {}
        for row in rows:
            uid = row['mapped_jarvis_user_id']
            day_str = str(row['day'])
            if uid not in result:
                result[uid] = {}
            if day_str not in result[uid]:
                result[uid][day_str] = row['short_code']  # first code wins per day

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return safe_error_response(e)


@sincron_bp.route('/api/timesheets/tree', methods=['GET'])
@api_login_required
@v2_permission_required('hr', 'timesheets', 'view')
def get_timesheet_tree():
    """Get visible organigram tree for timesheet node filtering."""
    from core.organization.hr_utils import get_visible_tree, is_manager
    scope = getattr(g, 'permission_scope', 'all')
    if scope == 'own':
        return jsonify({'success': True, 'companies': [], 'nodes': []})
    if scope == 'all':
        # Admin — return all structure nodes + companies
        from core.organization.manager_utils import get_db, get_cursor, release_db
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute("SELECT id, company as name FROM companies ORDER BY company")
            companies = [{'id': f'company-{r["id"]}', 'name': r['name'], 'level': 0,
                          'parent_id': None, 'company_id': r['id']} for r in cursor.fetchall()]
            cursor.execute("""
                SELECT id, name, level, parent_id, company_id
                FROM structure_nodes ORDER BY level, name
            """)
            nodes = [dict(r) for r in cursor.fetchall()]
            return jsonify({'success': True, 'companies': companies, 'nodes': nodes})
        finally:
            release_db(conn)
    # department scope — manager sees their own tree
    tree = get_visible_tree(current_user.id)
    return jsonify({'success': True, **tree})


@sincron_bp.route('/api/timesheets/team', methods=['GET'])
@api_login_required
@v2_permission_required('hr', 'timesheets', 'view')
def get_team_timesheet():
    """Get team timesheet summary. V2 permission scoped."""
    from core.organization.hr_utils import get_managed_employee_ids

    scope = getattr(g, 'permission_scope', 'all')

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

    # Scope-based filtering
    if scope == 'own':
        managed_ids = [current_user.id]
    elif scope == 'department':
        managed_ids = get_managed_employee_ids(current_user.id, node_id=node_id)
        if not managed_ids:
            managed_ids = [current_user.id]
    else:
        # scope == 'all' — admin sees ALL mapped employees across all companies
        if node_id:
            # Admin filtering by specific node — get that node's descendants
            managed_ids = get_managed_employee_ids(current_user.id, node_id=node_id)
        else:
            managed_ids = None  # None = no filter

    if managed_ids is not None and not managed_ids:
        return jsonify({'success': True, 'data': [],
                        'year': year, 'month': month})

    try:
        data = service.get_team_timesheet_summary(managed_ids, year, month)
        return jsonify({'success': True, 'data': data,
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


@sincron_bp.route('/api/sync/last-run', methods=['GET'])
@api_login_required
def get_last_sync_run():
    """Get the last sync run for a given year/month (login-only, not admin)."""
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
    run = service.sync_repo.get_last_run_for_month(year, month)
    return jsonify({'success': True, 'data': dict(run) if run else None})


@sincron_bp.route('/api/sync/status-per-company', methods=['GET'])
@api_login_required
def get_sync_status_per_company():
    """Get the last sync run per company for a given year/month (HR-accessible)."""
    if not getattr(current_user, 'can_access_hr', False) and not getattr(current_user, 'can_access_settings', False):
        return jsonify({'success': False, 'error': 'HR access required'}), 403
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
    runs = service.sync_repo.get_last_run_per_company(year, month)
    return jsonify({'success': True, 'data': [dict(r) for r in runs]})


# ── Org Nodes (hierarchical organigram) ──

from .repositories.sincron_org_node_repository import SincronOrgNodeRepository
_org_repo = SincronOrgNodeRepository()


@sincron_bp.route('/api/org-companies', methods=['GET'])
@api_login_required
def get_org_companies():
    """Get companies that have active Sincron employees."""
    return jsonify({'success': True, 'data': _org_repo.get_sincron_companies()})


@sincron_bp.route('/api/org-nodes', methods=['GET'])
@api_login_required
def get_org_nodes():
    """Get all Sincron org nodes."""
    company_id = request.args.get('company_id', type=int)
    if company_id:
        nodes = _org_repo.get_by_company(company_id)
    else:
        nodes = _org_repo.get_all()
    return jsonify({'success': True, 'data': nodes})


@sincron_bp.route('/api/org-nodes', methods=['POST'])
@admin_required
def create_org_node():
    """Create a Sincron org node."""
    data = request.get_json()
    if not data or not data.get('company_id') or not data.get('name'):
        return jsonify({'success': False, 'error': 'company_id and name required'}), 400
    try:
        nid = _org_repo.create(
            company_id=data['company_id'],
            name=data['name'].strip(),
            parent_id=data.get('parent_id'),
            node_type=data.get('node_type', 'department'),
        )
        return jsonify({'success': True, 'id': nid})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@sincron_bp.route('/api/org-nodes/<int:node_id>', methods=['PUT'])
@admin_required
def update_org_node(node_id):
    """Update a Sincron org node."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data'}), 400
    _org_repo.update(node_id, name=data.get('name'), node_type=data.get('node_type'))
    return jsonify({'success': True})


@sincron_bp.route('/api/org-nodes/<int:node_id>', methods=['DELETE'])
@admin_required
def delete_org_node(node_id):
    """Delete a Sincron org node (cascade removes children + members)."""
    _org_repo.delete(node_id)
    return jsonify({'success': True})


@sincron_bp.route('/api/org-nodes/members', methods=['GET'])
@api_login_required
def get_org_members():
    """Get all Sincron org members."""
    return jsonify({'success': True, 'data': _org_repo.get_all_members()})


@sincron_bp.route('/api/org-nodes/<int:node_id>/members/set', methods=['POST'])
@admin_required
def set_org_members(node_id):
    """Atomic replace members for a role on a node."""
    data = request.get_json()
    if not data or 'role' not in data or 'members' not in data:
        return jsonify({'success': False, 'error': 'role and members required'}), 400
    keys = [(m['sincron_employee_id'], m['company_name']) for m in data['members']]
    try:
        _org_repo.set_members(node_id, data['role'], keys)
        return jsonify({'success': True})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@sincron_bp.route('/api/org-nodes/seed', methods=['POST'])
@admin_required
def seed_org_nodes():
    """Seed org nodes from existing department data for a company."""
    data = request.get_json()
    if not data or not data.get('company_id'):
        return jsonify({'success': False, 'error': 'company_id required'}), 400
    try:
        result = _org_repo.seed_from_departments(data['company_id'])
        return jsonify({'success': True, **result})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@sincron_bp.route('/api/org-nodes/seed-all', methods=['POST'])
@admin_required
def seed_all_org_nodes():
    """Seed org nodes for all companies."""
    companies = _org_repo.query_all('SELECT id FROM companies ORDER BY id')
    total = {'created': 0, 'assigned': 0}
    for c in companies:
        try:
            r = _org_repo.seed_from_departments(c['id'])
            total['created'] += r['created']
            total['assigned'] += r['assigned']
        except Exception:
            pass
    return jsonify({'success': True, **total})
