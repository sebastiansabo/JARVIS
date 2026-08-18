"""Connecteam connector API routes.

Manual Excel import for Bilet de Invoire form submissions.
No API integration — Connecteam plan does not support webhooks/API.
"""

import hashlib
import logging
from datetime import datetime, date, time

from flask import request, jsonify, g
from flask_login import current_user

from . import connecteam_bp
from .services import ConnecteamService
from .config import BILET_INVOIRE_FORM_ID, BILET_INVOIRE_FORM_NAME
from core.utils.api_helpers import api_login_required, admin_required, safe_error_response
from core.roles.decorators import v2_permission_required

logger = logging.getLogger('jarvis.connecteam.routes')
service = ConnecteamService()


# ── Status ──

@connecteam_bp.route('/api/status', methods=['GET'])
@api_login_required
def get_status():
    """Get connector status summary."""
    try:
        status = service.get_status()
        return jsonify({'success': True, 'data': status})
    except Exception as e:
        return safe_error_response(e)


# ── Excel Import (admin) ──

@connecteam_bp.route('/api/import-excel', methods=['POST'])
@api_login_required
def import_excel():
    """Import Connecteam form submissions from Excel export.

    Expects multipart/form-data with 'file' field containing .xlsx file.
    """
    if not getattr(current_user, 'can_access_hr', False) and not getattr(current_user, 'can_access_settings', False):
        return jsonify({'success': False, 'error': 'HR access required'}), 403
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    file = request.files['file']
    if not file.filename or not file.filename.endswith('.xlsx'):
        return jsonify({'success': False, 'error': 'File must be .xlsx format'}), 400

    try:
        import openpyxl
        from io import BytesIO

        wb = openpyxl.load_workbook(BytesIO(file.read()), read_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(min_row=2, values_only=True))
        wb.close()

        if not rows:
            return jsonify({'success': True, 'data': {
                'rows_processed': 0, 'inserted': 0, 'skipped': 0,
                'users_created': 0, 'unmapped_names': [],
            }})

        result = service.import_from_rows(rows)
        return jsonify({'success': True, 'data': result})

    except Exception as e:
        logger.exception('Excel import error: %s', e)
        return safe_error_response(e)


# ── User Mapping (admin) ──

@connecteam_bp.route('/api/users', methods=['GET'])
@admin_required
def get_users():
    """List Connecteam users with mapping status."""
    active_only = request.args.get('active_only', 'true').lower() == 'true'
    try:
        users = service.repo.get_all_users(active_only)
        return jsonify({'success': True, 'data': users})
    except Exception as e:
        return safe_error_response(e)


@connecteam_bp.route('/api/users/auto-map', methods=['POST'])
@admin_required
def auto_map_users():
    """Auto-map Connecteam users to JARVIS users by name."""
    try:
        result = service.auto_map_users()
        return jsonify(result)
    except Exception as e:
        return safe_error_response(e)


@connecteam_bp.route('/api/users/mapping', methods=['PUT'])
@admin_required
def update_mapping():
    """Manually map a Connecteam user to a JARVIS user."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Request body required'}), 400

    connecteam_user_id = data.get('connecteam_user_id')
    jarvis_user_id = data.get('jarvis_user_id')

    if not connecteam_user_id or not jarvis_user_id:
        return jsonify({'success': False, 'error': 'connecteam_user_id and jarvis_user_id required'}), 400

    try:
        service.update_user_mapping(connecteam_user_id, jarvis_user_id)
        return jsonify({'success': True, 'message': 'Mapping updated'})
    except Exception as e:
        return safe_error_response(e)


@connecteam_bp.route('/api/users/mapping', methods=['DELETE'])
@admin_required
def remove_mapping():
    """Remove mapping for a Connecteam user."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Request body required'}), 400

    connecteam_user_id = data.get('connecteam_user_id')
    if not connecteam_user_id:
        return jsonify({'success': False, 'error': 'connecteam_user_id required'}), 400

    try:
        service.remove_user_mapping(connecteam_user_id)
        return jsonify({'success': True, 'message': 'Mapping removed'})
    except Exception as e:
        return safe_error_response(e)


# ── Approvers (for leave request form) ──

@connecteam_bp.route('/api/approvers', methods=['GET'])
@api_login_required
def get_approvers():
    """Get potential approvers for the current user's leave request.

    Walks UP the company structure from the user's assigned node(s)
    to collect all responsables above them. Falls back to L0 company
    responsables if the user has no structure node assignment.

    ?scope=all → returns all active users (for free-select mode).
    """
    try:
        scope = request.args.get('scope', '')
        if scope == 'all':
            from core.base_repository import BaseRepository
            rows = BaseRepository().query_all(
                "SELECT id, name FROM users WHERE is_active = TRUE ORDER BY name"
            )
            all_users = [{'id': r['id'], 'name': r['name']} for r in rows]
            return jsonify({'success': True, 'data': all_users})
        approvers = service.repo.get_approvers_for_user(current_user.id)
        return jsonify({'success': True, 'data': approvers})
    except Exception as e:
        return safe_error_response(e)


@connecteam_bp.route('/api/leave-schedule', methods=['GET'])
@api_login_required
def get_leave_schedule_route():
    """Sincron work window + day cap + reason options for the current user's leave form."""
    from .services.leave_schedule import get_leave_schedule
    from forms.services.form_service import FormService
    try:
        data = get_leave_schedule(current_user.id, request.args.get('date'))
        data['reasons'] = FormService().get_leave_reason_options()
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return safe_error_response(e)


# ── Submissions (user-scoped) ──

@connecteam_bp.route('/api/submissions/employee/<int:user_id>', methods=['GET'])
@api_login_required
@v2_permission_required('hr', 'leave_permissions', 'view')
def get_employee_submissions(user_id):
    """Get leave permission submissions for an employee (V2 permission scoped)."""
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

    try:
        data = service.get_user_submissions(user_id, year, month)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return safe_error_response(e)


@connecteam_bp.route('/api/submissions/leave-permit', methods=['POST'])
@api_login_required
def create_leave_permit():
    """Create a Bilet de Invoire from the code-defined Invoire module form.

    Fields are owned by the frontend (no DB form schema); the submission is
    stored as a form_submission and routed through the approval engine
    (primary manager + optional second approver, either approves).
    """
    from forms.services.form_service import FormService, UserContext
    data = request.get_json(silent=True) or {}
    answers = data.get('answers') if isinstance(data.get('answers'), dict) else data
    user = UserContext(user_id=current_user.id, company=getattr(current_user, 'company', None))
    try:
        result = FormService().submit_leave_permit(answers, user, ip_address=request.remote_addr)
    except Exception as e:
        return safe_error_response(e)
    if not result.success:
        return jsonify({'success': False, 'error': result.error}), result.status_code
    return jsonify({'success': True, 'data': result.data}), result.status_code


@connecteam_bp.route('/api/leave-approvals/pending', methods=['GET'])
@api_login_required
def get_pending_leave_approvals():
    """Leave requests awaiting the current user's approval (empty if not an approver)."""
    try:
        data = service.get_pending_leave_approvals(current_user.id)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return safe_error_response(e)


@connecteam_bp.route('/api/leave-approvals/<int:request_id>/decide', methods=['POST'])
@api_login_required
def decide_leave_approval(request_id):
    """Approve or reject a leave request the current user is an approver for."""
    data = request.get_json(silent=True) or {}
    decision = data.get('decision')
    if decision not in ('approved', 'rejected'):
        return jsonify({'success': False, 'error': "decision must be 'approved' or 'rejected'"}), 400
    try:
        service.decide_leave_approval(request_id, decision, current_user.id, comment=data.get('comment'))
        return jsonify({'success': True})
    except PermissionError:
        return jsonify({'success': False, 'error': 'Not an approver for this request'}), 403
    except Exception as e:
        return safe_error_response(e)


@connecteam_bp.route('/api/submissions/recent', methods=['GET'])
@admin_required
def get_recent_submissions():
    """Get submissions across all users (admin only), filtered by year/month.

    Merges Connecteam imported submissions and JARVIS internal form submissions.
    """
    limit = min(request.args.get('limit', 500, type=int), 1000)
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    try:
        data = service.get_all_submissions(year=year, month=month, limit=limit)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return safe_error_response(e)


# ── CO Conversions ──

@connecteam_bp.route('/api/conversions', methods=['POST'])
@admin_required
def create_conversion():
    """Initiate a CO conversion request for an employee's leave permits."""
    from .repositories.conversion_repository import ConversionRepository
    from hr.co_balance.repository import CoBalanceRepository
    from core.approvals.engine import ApprovalEngine

    data = request.get_json(force=True)
    employee_user_id = data.get('employee_user_id')
    year = data.get('year')
    month = data.get('month')
    co_days = data.get('co_days_requested')
    approver_user_id = data.get('approver_user_id')
    submission_ids = data.get('submission_ids', [])

    if not all([employee_user_id, year, month, co_days, approver_user_id]):
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400

    conv_repo = ConversionRepository()
    co_repo = CoBalanceRepository()

    # Check no pending conversion for this employee/month
    existing = conv_repo.get_for_employee_month(employee_user_id, year, month)
    if existing:
        return jsonify({'success': False, 'error': 'A pending conversion already exists for this employee/month'}), 409

    # Get employee's accumulated hours for this month
    subs = service.repo.get_recent_submissions(500, year=year, month=month)
    user_subs = [s for s in subs if s.get('mapped_jarvis_user_id') == employee_user_id]
    total_hours = sum(float(s.get('leave_hours') or 0) for s in user_subs)

    if total_hours <= 0:
        return jsonify({'success': False, 'error': 'No accumulated hours for this employee/month'}), 400

    # Default to all submissions for this employee/month if none specified
    if not submission_ids:
        submission_ids = [s['submission_id'] for s in user_subs]

    # Check CO balance
    balance = co_repo.get_for_user(employee_user_id, year)
    if not balance:
        return jsonify({'success': False, 'error': 'No CO balance found for this employee'}), 400

    # Get employee name for context
    from core.base_repository import BaseRepository
    user_row = BaseRepository().query_one("SELECT name FROM users WHERE id = %s", (employee_user_id,))
    employee_name = user_row['name'] if user_row else f'User #{employee_user_id}'

    month_label = datetime(year, month, 1).strftime('%B %Y')

    try:
        # Create conversion record (approval_request_id will be set after)
        conversion_id = conv_repo.create(
            employee_user_id=employee_user_id,
            year=year, month=month,
            total_accumulated_hours=total_hours,
            co_days_requested=co_days,
            approver_user_id=approver_user_id,
            requested_by=current_user.id,
            approval_request_id=None,
            submission_ids=submission_ids,
        )

        # Submit to approval engine
        engine = ApprovalEngine()
        result = engine.submit(
            entity_type='leave_permit_conversion',
            entity_id=conversion_id,
            context={
                'approver_user_id': approver_user_id,
                'title': f'CO Conversion: {employee_name} — {co_days} days ({month_label})',
                'employee_name': employee_name,
                'employee_user_id': employee_user_id,
                'co_days_requested': co_days,
                'total_hours': float(total_hours),
                'year': year,
                'month': month,
            },
            requested_by=current_user.id,
        )

        # Link approval request back to conversion
        if result and result.get('request_id'):
            conv_repo.set_approval_request_id(conversion_id, result['request_id'])

        conversion = conv_repo.get_by_id(conversion_id)
        return jsonify({'success': True, 'data': dict(conversion) if conversion else {'id': conversion_id}})

    except Exception as e:
        return safe_error_response(e)


@connecteam_bp.route('/api/conversions', methods=['GET'])
@api_login_required
def list_conversions():
    """List conversion requests filtered by year/month."""
    from .repositories.conversion_repository import ConversionRepository

    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    if not year or not month:
        return jsonify({'success': False, 'error': 'year and month required'}), 400

    try:
        data = ConversionRepository().get_for_month(year, month)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return safe_error_response(e)


@connecteam_bp.route('/api/conversions/<int:conversion_id>', methods=['GET'])
@api_login_required
def get_conversion(conversion_id):
    """Get a single conversion detail."""
    from .repositories.conversion_repository import ConversionRepository

    try:
        data = ConversionRepository().get_by_id(conversion_id)
        if not data:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        return jsonify({'success': True, 'data': dict(data)})
    except Exception as e:
        return safe_error_response(e)
