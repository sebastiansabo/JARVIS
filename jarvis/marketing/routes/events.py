"""Marketing project ↔ HR event linking routes + invoice search for budget."""

import logging
from flask import jsonify, request
from flask_login import login_required, current_user

from marketing import marketing_bp
from marketing.repositories import ProjectEventRepository, ActivityRepository
from marketing.routes.projects import mkt_permission_required
from core.utils.api_helpers import get_json_or_error, safe_error_response

logger = logging.getLogger('jarvis.marketing.routes.events')

_event_repo = ProjectEventRepository()
_activity_repo = ActivityRepository()


# ---- Project ↔ HR Event links ----

@marketing_bp.route('/api/projects/<int:project_id>/events', methods=['GET'])
@login_required
@mkt_permission_required('project', 'view')
def api_get_project_events(project_id):
    """List HR events linked to a project."""
    events = _event_repo.get_by_project(project_id)
    return jsonify({'events': events})


@marketing_bp.route('/api/projects/<int:project_id>/events', methods=['POST'])
@login_required
@mkt_permission_required('project', 'edit')
def api_link_event(project_id):
    """Link an HR event to a project."""
    data, error = get_json_or_error()
    if error:
        return error

    event_id = data.get('event_id')
    if not event_id:
        return jsonify({'success': False, 'error': 'event_id is required'}), 400

    try:
        link_id = _event_repo.link(project_id, event_id, current_user.id, notes=data.get('notes'))
        if link_id is None:
            return jsonify({'success': False, 'error': 'Event already linked'}), 409
        _activity_repo.log(project_id, 'event_linked', actor_id=current_user.id,
                           details={'event_id': event_id})
        return jsonify({'success': True, 'id': link_id}), 201
    except Exception as e:
        return safe_error_response(e)


@marketing_bp.route('/api/projects/<int:project_id>/events/<int:event_id>', methods=['DELETE'])
@login_required
@mkt_permission_required('project', 'edit')
def api_unlink_event(project_id, event_id):
    """Remove an HR event link from a project."""
    if _event_repo.unlink(project_id, event_id):
        _activity_repo.log(project_id, 'event_unlinked', actor_id=current_user.id,
                           details={'event_id': event_id})
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Link not found'}), 404


@marketing_bp.route('/api/hr-events/search', methods=['GET'])
@login_required
@mkt_permission_required('project', 'view')
def api_search_hr_events():
    """Search HR events for the linking picker."""
    q = request.args.get('q', '')
    limit = min(int(request.args.get('limit', 20)), 50)
    events = _event_repo.search_hr_events(query=q if q else None, limit=limit)
    return jsonify({'events': events})


# ---- Invoice search for budget linking ----

@marketing_bp.route('/api/invoices/search', methods=['GET'])
@login_required
@mkt_permission_required('budget', 'view')
def api_search_invoices():
    """Search invoices for linking to budget transactions."""
    q = request.args.get('q', '').strip()
    company = request.args.get('company')
    limit = min(int(request.args.get('limit', 20)), 50)

    invoices = _event_repo.search_invoices(query=q, company=company, limit=limit)
    return jsonify({'invoices': invoices})
