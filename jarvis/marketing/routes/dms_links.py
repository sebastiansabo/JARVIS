"""Marketing project ↔ DMS document linking routes."""

import logging
from flask import jsonify, request
from flask_login import login_required, current_user

from marketing import marketing_bp
from marketing.repositories import ProjectDmsLinkRepository, ActivityRepository
from marketing.routes.projects import mkt_permission_required
from core.utils.api_helpers import get_json_or_error, safe_error_response

logger = logging.getLogger('jarvis.marketing.routes.dms_links')

_dms_link_repo = ProjectDmsLinkRepository()
_activity_repo = ActivityRepository()


# ---- Project ↔ DMS Document links ----

@marketing_bp.route('/api/projects/<int:project_id>/dms-documents', methods=['GET'])
@login_required
@mkt_permission_required('project', 'view')
def api_get_project_dms_docs(project_id):
    """List DMS documents linked to a project."""
    docs = _dms_link_repo.get_by_project(project_id)
    return jsonify({'documents': docs})


@marketing_bp.route('/api/projects/<int:project_id>/dms-documents', methods=['POST'])
@login_required
@mkt_permission_required('project', 'edit')
def api_link_dms_doc(project_id):
    """Link a DMS document to a project."""
    data, error = get_json_or_error()
    if error:
        return error

    document_id = data.get('document_id')
    if not document_id:
        return jsonify({'success': False, 'error': 'document_id is required'}), 400

    try:
        link_id = _dms_link_repo.link(project_id, document_id, current_user.id)
        if link_id is None:
            return jsonify({'success': False, 'error': 'Document already linked'}), 409
        _activity_repo.log(project_id, 'dms_document_linked', actor_id=current_user.id,
                           details={'document_id': document_id})
        return jsonify({'success': True, 'id': link_id}), 201
    except Exception as e:
        return safe_error_response(e)


@marketing_bp.route('/api/projects/<int:project_id>/dms-documents/<int:document_id>', methods=['DELETE'])
@login_required
@mkt_permission_required('project', 'edit')
def api_unlink_dms_doc(project_id, document_id):
    """Remove a DMS document link from a project."""
    if _dms_link_repo.unlink(project_id, document_id):
        _activity_repo.log(project_id, 'dms_document_unlinked', actor_id=current_user.id,
                           details={'document_id': document_id})
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Link not found'}), 404


@marketing_bp.route('/api/dms-documents/search', methods=['GET'])
@login_required
@mkt_permission_required('project', 'view')
def api_search_dms_docs():
    """Search DMS documents for the linking picker."""
    q = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', 20)), 50)
    docs = _dms_link_repo.search_documents(query=q if q else None, limit=limit)
    return jsonify({'documents': docs})
