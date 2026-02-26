"""DMS document routes."""
import json
import logging
from functools import wraps
from flask import request, jsonify, g
from flask_login import login_required, current_user

from dms import dms_bp
from dms.repositories import DocumentRepository, FileRepository
from dms.services.document_service import DocumentService
from core.roles.repositories import PermissionRepository
from core.utils.api_helpers import safe_error_response, get_json_or_error

logger = logging.getLogger('jarvis.dms.routes.documents')

_doc_repo = DocumentRepository()
_file_repo = FileRepository()
_service = DocumentService()
_perm_repo = PermissionRepository()


def dms_permission_required(entity, action):
    """Check DMS permissions_v2 with scope."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({'success': False, 'error': 'Authentication required'}), 401
            role_id = getattr(current_user, 'role_id', None)
            if role_id:
                perm = _perm_repo.check_permission_v2(role_id, 'dms', entity, action)
                if perm.get('has_permission'):
                    g.permission_scope = perm.get('scope', 'all')
                    return f(*args, **kwargs)
            return jsonify({'success': False, 'error': f'Permission denied: dms.{entity}.{action}'}), 403
        return decorated
    return decorator


# ---- Documents CRUD ----

@dms_bp.route('/api/documents', methods=['GET'])
@login_required
@dms_permission_required('document', 'view')
def api_list_documents():
    """List root documents with filters."""
    company_id = getattr(current_user, 'company_id', None)

    result = _doc_repo.list_documents(
        company_id=company_id,
        category_id=request.args.get('category_id', type=int),
        status=request.args.get('status'),
        search=request.args.get('search'),
        limit=min(request.args.get('limit', 50, type=int), 200),
        offset=request.args.get('offset', 0, type=int),
    )
    return jsonify({'success': True, **result})


@dms_bp.route('/api/documents/<int:doc_id>', methods=['GET'])
@login_required
@dms_permission_required('document', 'view')
def api_get_document(doc_id):
    """Get a single document with children and files."""
    doc = _doc_repo.get_by_id(doc_id)
    if not doc:
        return jsonify({'success': False, 'error': 'Document not found'}), 404

    # Company isolation
    user_company = getattr(current_user, 'company_id', None)
    if user_company and doc['company_id'] != user_company:
        return jsonify({'success': False, 'error': 'Document not found'}), 404

    # Fetch children grouped by type
    children_raw = _doc_repo.get_children(doc_id)
    children = {}
    for child in children_raw:
        rtype = child.get('relationship_type', 'other')
        children.setdefault(rtype, []).append(child)

    # Fetch files
    files = _file_repo.get_by_document(doc_id)

    doc['children'] = children
    doc['files'] = files
    return jsonify({'success': True, 'document': doc})


@dms_bp.route('/api/documents', methods=['POST'])
@login_required
@dms_permission_required('document', 'create')
def api_create_document():
    """Create a new root document."""
    data, error = get_json_or_error()
    if error:
        return error

    title = data.get('title', '').strip()
    if not title:
        return jsonify({'success': False, 'error': 'Title is required'}), 400

    company_id = getattr(current_user, 'company_id', None) or data.get('company_id')
    if not company_id:
        return jsonify({'success': False, 'error': 'company_id required'}), 400

    try:
        metadata = data.get('metadata', '{}')
        if isinstance(metadata, dict):
            metadata = json.dumps(metadata)

        row = _doc_repo.create(
            title=title,
            company_id=company_id,
            created_by=current_user.id,
            description=data.get('description'),
            category_id=data.get('category_id'),
            status=data.get('status', 'draft'),
            metadata=metadata,
            doc_number=data.get('doc_number'),
            doc_date=data.get('doc_date') or None,
            expiry_date=data.get('expiry_date') or None,
            notify_user_id=data.get('notify_user_id'),
        )
        return jsonify({'success': True, 'id': row['id']}), 201
    except Exception as e:
        return safe_error_response(e)


@dms_bp.route('/api/documents/<int:doc_id>', methods=['PUT'])
@login_required
@dms_permission_required('document', 'edit')
def api_update_document(doc_id):
    """Update document metadata."""
    data, error = get_json_or_error()
    if error:
        return error

    doc = _doc_repo.get_by_id(doc_id)
    if not doc:
        return jsonify({'success': False, 'error': 'Document not found'}), 404

    user_company = getattr(current_user, 'company_id', None)
    if user_company and doc['company_id'] != user_company:
        return jsonify({'success': False, 'error': 'Document not found'}), 404

    try:
        fields = {}
        for key in ('title', 'description', 'category_id', 'status',
                     'doc_number', 'doc_date', 'expiry_date', 'notify_user_id'):
            if key in data:
                fields[key] = data[key] if data[key] != '' else None
        if 'metadata' in data:
            fields['metadata'] = json.dumps(data['metadata']) if isinstance(data['metadata'], dict) else data['metadata']

        _doc_repo.update(doc_id, **fields)
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@dms_bp.route('/api/documents/<int:doc_id>', methods=['DELETE'])
@login_required
@dms_permission_required('document', 'delete')
def api_delete_document(doc_id):
    """Soft-delete a document."""
    doc = _doc_repo.get_by_id(doc_id)
    if not doc:
        return jsonify({'success': False, 'error': 'Document not found'}), 404

    user_company = getattr(current_user, 'company_id', None)
    if user_company and doc['company_id'] != user_company:
        return jsonify({'success': False, 'error': 'Document not found'}), 404

    _doc_repo.soft_delete(doc_id)
    return jsonify({'success': True})


@dms_bp.route('/api/documents/<int:doc_id>/restore', methods=['POST'])
@login_required
@dms_permission_required('document', 'edit')
def api_restore_document(doc_id):
    """Restore a soft-deleted document."""
    _doc_repo.restore(doc_id)
    return jsonify({'success': True})


@dms_bp.route('/api/documents/<int:doc_id>/permanent', methods=['DELETE'])
@login_required
@dms_permission_required('document', 'delete')
def api_permanent_delete_document(doc_id):
    """Permanently delete a soft-deleted document."""
    _doc_repo.permanent_delete(doc_id)
    return jsonify({'success': True})


# ---- Children ----

@dms_bp.route('/api/documents/<int:doc_id>/children', methods=['GET'])
@login_required
@dms_permission_required('document', 'view')
def api_get_children(doc_id):
    """Get children of a document grouped by relationship type."""
    children_raw = _doc_repo.get_children(doc_id)
    grouped = {}
    for child in children_raw:
        rtype = child.get('relationship_type', 'other')
        grouped.setdefault(rtype, []).append(child)
    return jsonify({'success': True, 'children': grouped})


@dms_bp.route('/api/documents/<int:doc_id>/children', methods=['POST'])
@login_required
@dms_permission_required('document', 'create')
def api_create_child(doc_id):
    """Create a child document (annex, deviz, proof, other)."""
    data, error = get_json_or_error()
    if error:
        return error

    title = data.get('title', '').strip()
    if not title:
        return jsonify({'success': False, 'error': 'Title is required'}), 400

    relationship_type = data.get('relationship_type', 'other')
    if relationship_type not in ('annex', 'deviz', 'proof', 'other'):
        return jsonify({'success': False, 'error': 'Invalid relationship_type'}), 400

    # Get parent to inherit company_id and category_id
    parent = _doc_repo.get_by_id(doc_id)
    if not parent:
        return jsonify({'success': False, 'error': 'Parent document not found'}), 404

    user_company = getattr(current_user, 'company_id', None)
    if user_company and parent['company_id'] != user_company:
        return jsonify({'success': False, 'error': 'Parent document not found'}), 404

    try:
        metadata = data.get('metadata', '{}')
        if isinstance(metadata, dict):
            metadata = json.dumps(metadata)

        row = _doc_repo.create(
            title=title,
            company_id=parent['company_id'],
            created_by=current_user.id,
            description=data.get('description'),
            category_id=data.get('category_id') or parent.get('category_id'),
            status=data.get('status', 'draft'),
            parent_id=doc_id,
            relationship_type=relationship_type,
            metadata=metadata,
            doc_number=data.get('doc_number'),
            doc_date=data.get('doc_date') or None,
            expiry_date=data.get('expiry_date') or None,
            notify_user_id=data.get('notify_user_id'),
        )
        return jsonify({'success': True, 'id': row['id']}), 201
    except Exception as e:
        return safe_error_response(e)


# ---- Stats ----

@dms_bp.route('/api/dms/stats', methods=['GET'])
@login_required
@dms_permission_required('document', 'view')
def api_get_stats():
    """Get document statistics."""
    company_id = getattr(current_user, 'company_id', None)
    stats = _doc_repo.get_stats(company_id)
    return jsonify({'success': True, **stats})
