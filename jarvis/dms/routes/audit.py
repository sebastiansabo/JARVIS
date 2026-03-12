"""DMS Audit Log routes — change history."""
import logging
from flask import request, jsonify
from flask_login import login_required, current_user

from dms import dms_bp
from dms.repositories import AuditRepository
from core.utils.api_helpers import safe_error_response, v2_permission_required

logger = logging.getLogger('jarvis.dms.routes.audit')

_audit_repo = AuditRepository()


def dms_permission_required(entity, action):
    return v2_permission_required('dms', entity, action)


@dms_bp.route('/api/dms/audit', methods=['GET'])
@login_required
@dms_permission_required('folder', 'view')
def api_get_audit_log():
    """Get audit log for the user's company."""
    try:
        entity_type = request.args.get('entity_type')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)

        entries = _audit_repo.get_by_company(
            current_user.company_id,
            entity_type=entity_type,
            limit=min(limit, 200),
            offset=offset
        )
        return jsonify({'success': True, 'entries': entries})
    except Exception as e:
        logger.exception('Failed to get audit log')
        return safe_error_response(e)


@dms_bp.route('/api/dms/audit/<entity_type>/<int:entity_id>', methods=['GET'])
@login_required
@dms_permission_required('folder', 'view')
def api_get_entity_audit(entity_type, entity_id):
    """Get audit trail for a specific entity."""
    try:
        if entity_type not in ('folder', 'document', 'file', 'acl'):
            return jsonify({'success': False, 'error': 'Invalid entity type'}), 400

        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)

        entries = _audit_repo.get_by_entity(
            entity_type, entity_id,
            limit=min(limit, 200), offset=offset
        )
        return jsonify({'success': True, 'entries': entries})
    except Exception as e:
        logger.exception('Failed to get entity audit log')
        return safe_error_response(e)


@dms_bp.route('/api/dms/folders/<int:folder_id>/activity', methods=['GET'])
@login_required
@dms_permission_required('folder', 'view')
def api_get_folder_activity(folder_id):
    """Get all activity for a folder (folder + docs + ACL changes)."""
    try:
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)

        entries = _audit_repo.get_folder_activity(
            folder_id, limit=min(limit, 200), offset=offset
        )
        return jsonify({'success': True, 'entries': entries})
    except Exception as e:
        logger.exception('Failed to get folder activity')
        return safe_error_response(e)
