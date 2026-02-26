"""DMS file upload/download routes."""
import os
import logging
from urllib.parse import urlparse
from flask import request, jsonify, redirect, send_from_directory
from flask_login import login_required, current_user

from dms import dms_bp
from dms.repositories import DocumentRepository, FileRepository
from dms.services.document_service import DocumentService, MAX_FILE_SIZE
from dms.routes.documents import dms_permission_required
from core.utils.api_helpers import safe_error_response

logger = logging.getLogger('jarvis.dms.routes.files')

_doc_repo = DocumentRepository()
_file_repo = FileRepository()
_service = DocumentService()

# Allowed Drive hosts for redirect
_ALLOWED_REDIRECT_HOSTS = {'drive.google.com', 'docs.google.com'}


@dms_bp.route('/api/documents/<int:doc_id>/files/upload', methods=['POST'])
@login_required
@dms_permission_required('document', 'edit')
def api_upload_files(doc_id):
    """Upload one or more files to a document."""
    doc = _doc_repo.get_by_id(doc_id)
    if not doc:
        return jsonify({'success': False, 'error': 'Document not found'}), 404

    # Company isolation
    user_company = getattr(current_user, 'company_id', None)
    if user_company and doc['company_id'] != user_company:
        return jsonify({'success': False, 'error': 'Document not found'}), 404

    files = request.files.getlist('files')
    if not files:
        # Try single file field
        f = request.files.get('file')
        if f:
            files = [f]
    if not files:
        return jsonify({'success': False, 'error': 'No files provided'}), 400

    results = []
    errors = []
    for f in files:
        if not f.filename:
            continue
        # Pre-check content length before reading into memory
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(0)
        if size > MAX_FILE_SIZE:
            errors.append({'file': f.filename, 'error': f'File too large ({size // (1024*1024)}MB). Max: {MAX_FILE_SIZE // (1024*1024)}MB'})
            continue
        file_bytes = f.read()
        result = _service.upload_file(doc_id, file_bytes, f.filename, current_user.id)
        if result.success:
            results.append(result.data)
        else:
            errors.append({'file': f.filename, 'error': result.error})

    if not results and errors:
        return jsonify({'success': False, 'errors': errors}), 400

    return jsonify({
        'success': True,
        'uploaded': results,
        'errors': errors,
    }), 201 if results else 400


@dms_bp.route('/api/documents/<int:doc_id>/files', methods=['GET'])
@login_required
@dms_permission_required('document', 'view')
def api_list_files(doc_id):
    """List files for a document."""
    doc = _doc_repo.get_by_id(doc_id)
    if not doc:
        return jsonify({'success': False, 'error': 'Document not found'}), 404

    user_company = getattr(current_user, 'company_id', None)
    if user_company and doc['company_id'] != user_company:
        return jsonify({'success': False, 'error': 'Document not found'}), 404

    files = _file_repo.get_by_document(doc_id)
    return jsonify({'success': True, 'files': files})


@dms_bp.route('/api/dms/files/<int:file_id>', methods=['DELETE'])
@login_required
@dms_permission_required('document', 'edit')
def api_delete_file(file_id):
    """Delete a single file."""
    file_row = _file_repo.get_by_id(file_id)
    if not file_row:
        return jsonify({'success': False, 'error': 'File not found'}), 404

    # Company isolation via parent document
    doc = _doc_repo.get_by_id(file_row['document_id'])
    user_company = getattr(current_user, 'company_id', None)
    if doc and user_company and doc['company_id'] != user_company:
        return jsonify({'success': False, 'error': 'File not found'}), 404

    try:
        result = _service.delete_file(file_id)
        if result.success:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': result.error}), result.status_code
    except Exception as e:
        return safe_error_response(e)


@dms_bp.route('/api/dms/files/<int:file_id>/download', methods=['GET'])
@login_required
@dms_permission_required('document', 'view')
def api_download_file(file_id):
    """Download or redirect to file."""
    file_row = _file_repo.get_by_id(file_id)
    if not file_row:
        return jsonify({'success': False, 'error': 'File not found'}), 404

    # Company isolation via parent document
    doc = _doc_repo.get_by_id(file_row['document_id'])
    user_company = getattr(current_user, 'company_id', None)
    if doc and user_company and doc['company_id'] != user_company:
        return jsonify({'success': False, 'error': 'File not found'}), 404

    if file_row['storage_type'] == 'drive':
        # Validate redirect URL against allowed hosts
        parsed = urlparse(file_row['storage_uri'])
        if parsed.hostname not in _ALLOWED_REDIRECT_HOSTS:
            return jsonify({'success': False, 'error': 'Invalid storage URI'}), 400
        return redirect(file_row['storage_uri'])

    # Local file — validate path stays within upload directory
    base_dir = os.path.realpath(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'uploads', 'dms')
    )
    local_path = os.path.realpath(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     file_row['storage_uri'].lstrip('/'))
    )
    if not local_path.startswith(base_dir):
        return jsonify({'success': False, 'error': 'Invalid file path'}), 400

    if not os.path.exists(local_path):
        return jsonify({'success': False, 'error': 'File not found on disk'}), 404

    directory = os.path.dirname(local_path)
    filename = os.path.basename(local_path)
    return send_from_directory(directory, filename, as_attachment=True)
