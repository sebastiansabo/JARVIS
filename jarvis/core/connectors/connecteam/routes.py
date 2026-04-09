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
from core.utils.api_helpers import api_login_required, admin_required, safe_error_response, v2_permission_required

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
@admin_required
def import_excel():
    """Import Connecteam form submissions from Excel export.

    Expects multipart/form-data with 'file' field containing .xlsx file.
    """
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
    """
    from database import get_db, get_cursor, release_db

    conn = get_db()
    cursor = get_cursor(conn)
    try:
        uid = current_user.id

        # 1. Find user's structure node assignments
        cursor.execute('''
            SELECT sn.id AS node_id, sn.company_id
            FROM structure_node_members snm
            JOIN structure_nodes sn ON snm.node_id = sn.id
            WHERE snm.user_id = %s
            ORDER BY sn.level DESC
        ''', (uid,))
        assignments = cursor.fetchall()

        approver_ids = set()

        if assignments:
            for a in assignments:
                node_id = a['node_id'] if isinstance(a, dict) else a[0]
                # Walk UP parent chain collecting responsables
                cursor.execute('''
                    WITH RECURSIVE ancestors AS (
                        SELECT id, parent_id FROM structure_nodes WHERE id = %s
                        UNION ALL
                        SELECT sn.id, sn.parent_id
                        FROM structure_nodes sn
                        JOIN ancestors a ON sn.id = a.parent_id
                    )
                    SELECT DISTINCT snm.user_id
                    FROM ancestors a
                    JOIN structure_node_members snm ON snm.node_id = a.id
                    WHERE snm.role = 'responsable'
                      AND snm.user_id != %s
                ''', (node_id, uid))
                for row in cursor.fetchall():
                    rid = row['user_id'] if isinstance(row, dict) else row[0]
                    approver_ids.add(rid)

        # 2. Fallback: L0 company responsables
        if not approver_ids:
            cursor.execute('''
                SELECT DISTINCT cr.user_id
                FROM company_responsables cr
                JOIN structure_node_members snm ON snm.user_id = %s
                JOIN structure_nodes sn ON snm.node_id = sn.id
                WHERE cr.company_id = sn.company_id
                  AND cr.user_id != %s
            ''', (uid, uid))
            for row in cursor.fetchall():
                rid = row['user_id'] if isinstance(row, dict) else row[0]
                approver_ids.add(rid)

        # 3. If still empty, get all L0 responsables for any company
        if not approver_ids:
            cursor.execute('''
                SELECT DISTINCT cr.user_id
                FROM company_responsables cr
                WHERE cr.user_id != %s
            ''', (uid,))
            for row in cursor.fetchall():
                rid = row['user_id'] if isinstance(row, dict) else row[0]
                approver_ids.add(rid)

        # 4. Fetch names
        if approver_ids:
            cursor.execute('''
                SELECT id, name FROM users
                WHERE id = ANY(%s)
                ORDER BY name
            ''', (list(approver_ids),))
            approvers = [{'id': r['id'] if isinstance(r, dict) else r[0],
                          'name': r['name'] if isinstance(r, dict) else r[1]}
                         for r in cursor.fetchall()]
        else:
            approvers = []

        return jsonify({'success': True, 'data': approvers})
    except Exception as e:
        return safe_error_response(e)
    finally:
        release_db(conn)


# ── Submissions (user-scoped) ──

@connecteam_bp.route('/api/submissions/employee/<int:user_id>', methods=['GET'])
@api_login_required
@v2_permission_required('hr', 'leave_permissions', 'view')
def get_employee_submissions(user_id):
    """Get leave permission submissions for an employee (V2 permission scoped)."""
    from hr.events.database import get_managed_employee_ids

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


@connecteam_bp.route('/api/submissions/recent', methods=['GET'])
@admin_required
def get_recent_submissions():
    """Get most recent submissions across all users (admin only)."""
    limit = min(request.args.get('limit', 50, type=int), 200)
    try:
        data = service.repo.get_recent_submissions(limit)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return safe_error_response(e)
