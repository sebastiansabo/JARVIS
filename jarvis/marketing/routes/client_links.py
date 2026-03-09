"""Marketing project <-> CRM client linking routes."""

import logging
from flask import jsonify, request
from flask_login import login_required, current_user

from marketing import marketing_bp
from marketing.repositories import ProjectClientLinkRepository, ActivityRepository
from marketing.routes.projects import mkt_permission_required
from core.utils.api_helpers import get_json_or_error, safe_error_response

logger = logging.getLogger('jarvis.marketing.routes.client_links')

_client_link_repo = ProjectClientLinkRepository()
_activity_repo = ActivityRepository()


# ---- Project <-> CRM Client links ----

@marketing_bp.route('/api/projects/<int:project_id>/clients', methods=['GET'])
@login_required
@mkt_permission_required('project', 'view')
def api_get_project_clients(project_id):
    """List CRM clients linked to a project."""
    clients = _client_link_repo.get_by_project(project_id)
    return jsonify({'clients': clients})


@marketing_bp.route('/api/projects/<int:project_id>/clients', methods=['POST'])
@login_required
@mkt_permission_required('project', 'edit')
def api_link_client(project_id):
    """Link a CRM client to a project."""
    data, error = get_json_or_error()
    if error:
        return error

    client_id = data.get('client_id')
    if not client_id:
        return jsonify({'success': False, 'error': 'client_id is required'}), 400

    try:
        link_id = _client_link_repo.link(project_id, client_id, current_user.id)
        if link_id is None:
            return jsonify({'success': False, 'error': 'Client already linked'}), 409
        _activity_repo.log(project_id, 'client_linked', actor_id=current_user.id,
                           details={'client_id': client_id})
        return jsonify({'success': True, 'id': link_id}), 201
    except Exception as e:
        return safe_error_response(e)


@marketing_bp.route('/api/projects/<int:project_id>/clients/<int:client_id>', methods=['DELETE'])
@login_required
@mkt_permission_required('project', 'edit')
def api_unlink_client(project_id, client_id):
    """Remove a CRM client link from a project."""
    if _client_link_repo.unlink(project_id, client_id):
        _activity_repo.log(project_id, 'client_unlinked', actor_id=current_user.id,
                           details={'client_id': client_id})
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Link not found'}), 404


@marketing_bp.route('/api/projects/<int:project_id>/clients/<int:client_id>/deals', methods=['GET'])
@login_required
@mkt_permission_required('project', 'view')
def api_get_client_deals(project_id, client_id):
    """Get deals for a linked client (expanded row)."""
    deals = _client_link_repo.get_client_deals(client_id)
    return jsonify({'deals': deals})


@marketing_bp.route('/api/crm-clients/search', methods=['GET'])
@login_required
@mkt_permission_required('project', 'view')
def api_search_crm_clients():
    """Search CRM clients for the linking picker."""
    q = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', 20)), 50)
    clients = _client_link_repo.search_clients(query=q if q else None, limit=limit)
    return jsonify({'clients': clients})


@marketing_bp.route('/api/crm-clients/<int:client_id>/campaigns', methods=['GET'])
@login_required
def api_get_client_campaigns(client_id):
    """Get all marketing campaigns linked to a client (for client profile)."""
    campaigns = _client_link_repo.get_projects_for_client(client_id)
    return jsonify({'campaigns': campaigns})
