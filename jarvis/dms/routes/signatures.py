"""DMS signature status routes (manual mode)."""
import logging
from datetime import datetime, timezone
from flask import jsonify
from flask_login import login_required, current_user

from dms import dms_bp
from dms.repositories import DocumentRepository
from dms.routes.documents import dms_permission_required
from core.utils.api_helpers import safe_error_response, get_json_or_error

logger = logging.getLogger('jarvis.dms.routes.signatures')

_doc_repo = DocumentRepository()

_VALID_SIG_STATUSES = (None, 'pending', 'sent', 'signed', 'declined', 'expired')
_VALID_PROVIDERS = ('manual', 'docusign', 'validsign')


@dms_bp.route('/api/documents/<int:doc_id>/signature-status', methods=['PUT'])
@login_required
@dms_permission_required('document', 'edit')
def api_update_signature_status(doc_id):
    """Update signature status for a document (manual mode)."""
    doc = _doc_repo.get_by_id(doc_id)
    if not doc:
        return jsonify({'success': False, 'error': 'Document not found'}), 404

    user_company = getattr(current_user, 'company_id', None)
    if user_company and doc['company_id'] != user_company:
        return jsonify({'success': False, 'error': 'Document not found'}), 404

    data, error = get_json_or_error()
    if error:
        return error

    status = data.get('signature_status')
    if status not in _VALID_SIG_STATUSES:
        return jsonify({
            'success': False,
            'error': f'Invalid status. Must be one of: {", ".join(str(s) for s in _VALID_SIG_STATUSES)}'
        }), 400

    provider = data.get('signature_provider', 'manual')
    if provider not in _VALID_PROVIDERS:
        return jsonify({'success': False, 'error': f'Invalid provider. Must be one of: {", ".join(_VALID_PROVIDERS)}'}), 400

    try:
        from core.database import get_db, get_cursor, release_db
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            now = datetime.now(timezone.utc)

            # Build updates
            sets = ['signature_status = %s', 'signature_provider = %s', 'updated_at = CURRENT_TIMESTAMP']
            params = [status, provider]

            if status == 'pending' or status == 'sent':
                sets.append('signature_requested_at = %s')
                params.append(now)
            elif status == 'signed':
                sets.append('signature_completed_at = %s')
                params.append(now)
            elif status is None:
                # Clearing signature — reset all fields
                sets.extend([
                    'signature_request_id = NULL',
                    'signature_requested_at = NULL',
                    'signature_completed_at = NULL',
                    'signature_provider = NULL',
                ])

            if data.get('signature_request_id'):
                req_id = str(data['signature_request_id'])[:255]
                sets.append('signature_request_id = %s')
                params.append(req_id)

            params.append(doc_id)
            cursor.execute(
                f'UPDATE dms_documents SET {", ".join(sets)} WHERE id = %s',
                tuple(params)
            )
            conn.commit()
        finally:
            release_db(conn)

        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@dms_bp.route('/api/documents/pending-signatures', methods=['GET'])
@login_required
@dms_permission_required('document', 'view')
def api_pending_signatures():
    """List documents with pending signatures."""
    company_id = getattr(current_user, 'company_id', None)
    from core.database import get_db, get_cursor, release_db
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        conditions = [
            "d.signature_status IN ('pending', 'sent')",
            "d.deleted_at IS NULL",
        ]
        params = []
        if company_id:
            conditions.append("d.company_id = %s")
            params.append(company_id)

        where = ' AND '.join(conditions)
        cursor.execute(f"""
            SELECT d.id, d.title, d.doc_number, d.signature_status,
                   d.signature_provider, d.signature_requested_at,
                   c.name AS category_name, co.company AS company_name,
                   u.name AS created_by_name
            FROM dms_documents d
            LEFT JOIN dms_categories c ON c.id = d.category_id
            LEFT JOIN companies co ON co.id = d.company_id
            LEFT JOIN users u ON u.id = d.created_by
            WHERE {where}
            ORDER BY d.signature_requested_at DESC
            LIMIT 100
        """, tuple(params))
        docs = [dict(r) for r in cursor.fetchall()]
        return jsonify({'success': True, 'documents': docs})
    finally:
        release_db(conn)
