"""DMS Google Drive sync routes."""
import logging
from flask import jsonify, request
from flask_login import login_required, current_user

from dms import dms_bp
from dms.repositories import DocumentRepository, FileRepository
from dms.services.drive_sync_service import DriveSyncService
from dms.routes.documents import dms_permission_required

logger = logging.getLogger('jarvis.dms.routes.drive_sync')

_doc_repo = DocumentRepository()
_file_repo = FileRepository()
_sync_service = DriveSyncService()


def _check_doc_access(doc_id):
    """Check document exists and user has company access."""
    doc = _doc_repo.get_by_id(doc_id)
    if not doc:
        return None, (jsonify({'success': False, 'error': 'Document not found'}), 404)
    user_company = getattr(current_user, 'company_id', None)
    if user_company and doc['company_id'] != user_company:
        return None, (jsonify({'success': False, 'error': 'Document not found'}), 404)
    return doc, None


@dms_bp.route('/api/documents/<int:doc_id>/drive-sync', methods=['GET'])
@login_required
@dms_permission_required('document', 'view')
def api_drive_sync_status(doc_id):
    """Get Drive sync status for a document."""
    _doc, err = _check_doc_access(doc_id)
    if err:
        return err

    sync = _sync_service.get_sync_status(doc_id)
    return jsonify({
        'success': True,
        'sync': {
            'synced': sync is not None and sync['sync_status'] in ('synced', 'partial'),
            'status': sync['sync_status'] if sync else None,
            'folder_url': sync['drive_folder_url'] if sync else None,
            'last_synced_at': str(sync['last_synced_at'] or '') if sync else None,
            'error_message': sync['error_message'] if sync else None,
        } if sync else None,
        'drive_available': _sync_service.check_drive_available(),
    })


@dms_bp.route('/api/documents/<int:doc_id>/drive-sync', methods=['POST'])
@login_required
@dms_permission_required('document', 'edit')
def api_drive_sync(doc_id):
    """Sync document files to Google Drive."""
    doc, err = _check_doc_access(doc_id)
    if err:
        return err

    files = _file_repo.get_by_document(doc_id)
    if not files:
        return jsonify({'success': False, 'error': 'No files to sync'}), 400

    result = _sync_service.sync_document(doc_id, doc, files)
    status_code = 200 if result['success'] else 500
    return jsonify(result), status_code


@dms_bp.route('/api/documents/<int:doc_id>/drive-sync', methods=['DELETE'])
@login_required
@dms_permission_required('document', 'edit')
def api_drive_unsync(doc_id):
    """Remove Drive sync tracking (does not delete Drive files)."""
    _doc, err = _check_doc_access(doc_id)
    if err:
        return err

    result = _sync_service.unsync_document(doc_id)
    return jsonify(result)


@dms_bp.route('/api/dms/drive-status', methods=['GET'])
@login_required
def api_drive_status():
    """Check if Google Drive integration is available."""
    return jsonify({
        'success': True,
        'available': _sync_service.check_drive_available(),
    })
