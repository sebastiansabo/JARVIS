"""Authenticated routes for the project lead sheet + webhook token management.

- Lead sheet:   GET/PATCH/DELETE under /marketing/api/projects/<id>/leads
- Webhook tokens: GET/POST/DELETE under /marketing/api/projects/<id>/webhooks

All gated by marketing.project view/edit. The public intake endpoint lives
separately in leads_webhook.py.
"""
import logging

from flask import jsonify, request, g
from flask_login import login_required, current_user

from marketing import marketing_bp
from marketing.repositories import (
    ProjectLeadRepository, ProjectWebhookRepository, ActivityRepository,
    ProjectRepository,
)
from marketing.services.project_service import ProjectService
from marketing.decorators import mkt_permission_required
from marketing.services import webhook_token
from marketing.services.lead_intake import LEAD_STATUSES
from core.utils.api_helpers import get_json_or_error, error_response, safe_error_response

logger = logging.getLogger('jarvis.marketing.routes.leads')

_lead_repo = ProjectLeadRepository()
_webhook_repo = ProjectWebhookRepository()
_activity_repo = ActivityRepository()
_project_repo = ProjectRepository()
_service = ProjectService()

_WEBHOOK_PATH = '/marketing/api/webhooks/leads'


def _require_project_access(project_id):
    """Fetch the project and enforce the caller's permission scope.

    Mirrors the gate used throughout projects.py: mkt_permission_required only
    proves the caller holds the permission with *some* scope — this confirms
    the caller may actually touch THIS project ('own'/'department'/'all').
    Returns an error response tuple to return, or None when access is granted.
    """
    project = _project_repo.get_by_id(project_id)
    if not project:
        return error_response('Project not found', 404)
    scope = getattr(g, 'permission_scope', 'all')
    if not _service.can_access_project(project, current_user.id, scope,
                                       getattr(current_user, 'company', None)):
        return error_response('Access denied', 403)
    return None


# ---- Lead sheet ----

@marketing_bp.route('/api/projects/<int:project_id>/leads', methods=['GET'])
@login_required
@mkt_permission_required('project', 'view')
def api_list_project_leads(project_id):
    """List leads for a project with optional status/search filters."""
    denied = _require_project_access(project_id)
    if denied:
        return denied
    status = request.args.get('status') or None
    search = request.args.get('search', '').strip() or None
    limit = min(int(request.args.get('limit', 100)), 500)
    offset = int(request.args.get('offset', 0))
    leads = _lead_repo.list_by_project(project_id, status=status, search=search,
                                       limit=limit, offset=offset)
    return jsonify({'leads': leads, 'status_counts': _lead_repo.status_counts(project_id)})


@marketing_bp.route('/api/projects/<int:project_id>/leads/<int:lead_id>', methods=['PATCH'])
@login_required
@mkt_permission_required('project', 'edit')
def api_update_project_lead(project_id, lead_id):
    """Update a lead's status and/or notes."""
    denied = _require_project_access(project_id)
    if denied:
        return denied
    data, error = get_json_or_error()
    if error:
        return error

    status = data.get('status')
    if status is not None and status not in LEAD_STATUSES:
        return error_response(f'Invalid status: {status}', 400)

    status_notes = data.get('status_notes')
    if status is None and status_notes is None:
        return error_response('Nothing to update', 400)

    try:
        updated = _lead_repo.update(project_id, lead_id, status=status, status_notes=status_notes)
        if not updated:
            return error_response('Lead not found', 404)
        _activity_repo.log(project_id, 'lead_updated', actor_id=current_user.id,
                           details={'lead_id': lead_id, 'status': status})
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@marketing_bp.route('/api/projects/<int:project_id>/leads/<int:lead_id>', methods=['DELETE'])
@login_required
@mkt_permission_required('project', 'edit')
def api_delete_project_lead(project_id, lead_id):
    """Delete a lead from the project sheet."""
    denied = _require_project_access(project_id)
    if denied:
        return denied
    if _lead_repo.delete(project_id, lead_id):
        _activity_repo.log(project_id, 'lead_deleted', actor_id=current_user.id,
                           details={'lead_id': lead_id})
        return jsonify({'success': True})
    return error_response('Lead not found', 404)


# ---- Webhook token management ----

@marketing_bp.route('/api/projects/<int:project_id>/webhooks', methods=['GET'])
@login_required
@mkt_permission_required('project', 'edit')
def api_list_project_webhooks(project_id):
    """List webhook tokens for a project (hash never exposed)."""
    denied = _require_project_access(project_id)
    if denied:
        return denied
    return jsonify({
        'webhooks': _webhook_repo.list_by_project(project_id),
        'webhook_url': request.host_url.rstrip('/') + _WEBHOOK_PATH,
    })


@marketing_bp.route('/api/projects/<int:project_id>/webhooks', methods=['POST'])
@login_required
@mkt_permission_required('project', 'edit')
def api_create_project_webhook(project_id):
    """Mint a webhook token. The plaintext token is returned exactly ONCE."""
    denied = _require_project_access(project_id)
    if denied:
        return denied
    data, error = get_json_or_error()
    if error:
        return error

    label = (data.get('label') or '').strip()
    if not label:
        return error_response('Label is required', 400)

    try:
        plaintext, token_hash, token_prefix = webhook_token.generate_token()
        webhook_id = _webhook_repo.create(project_id, label, token_hash, token_prefix, current_user.id)
        _activity_repo.log(project_id, 'webhook_created', actor_id=current_user.id,
                           details={'webhook_id': webhook_id, 'label': label})
        return jsonify({
            'success': True,
            'id': webhook_id,
            'label': label,
            'token': plaintext,          # shown once — never retrievable again
            'token_prefix': token_prefix,
            'webhook_url': request.host_url.rstrip('/') + _WEBHOOK_PATH,
        }), 201
    except Exception as e:
        return safe_error_response(e)


@marketing_bp.route('/api/projects/<int:project_id>/webhooks/<int:webhook_id>', methods=['DELETE'])
@login_required
@mkt_permission_required('project', 'edit')
def api_revoke_project_webhook(project_id, webhook_id):
    """Revoke a webhook token (scoped to the project)."""
    denied = _require_project_access(project_id)
    if denied:
        return denied
    if _webhook_repo.revoke(project_id, webhook_id):
        _activity_repo.log(project_id, 'webhook_revoked', actor_id=current_user.id,
                           details={'webhook_id': webhook_id})
        return jsonify({'success': True})
    return error_response('Webhook not found', 404)
