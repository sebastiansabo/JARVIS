"""Authenticated routes for the project lead sheet + webhook token management.

- Lead sheet:   GET/PATCH/DELETE under /marketing/api/projects/<id>/leads
- Webhook tokens: GET/POST/DELETE under /marketing/api/projects/<id>/webhooks

All gated by marketing.project view/edit. The public intake endpoint lives
separately in leads_webhook.py.
"""
import io
import logging
from datetime import datetime

from flask import jsonify, request, g, send_file
from flask_login import login_required, current_user

try:  # py3.9+ stdlib; backport on older runtimes
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo

from marketing import marketing_bp
from marketing.repositories import (
    ProjectLeadRepository, ProjectWebhookRepository, ActivityRepository,
    ProjectRepository, ProjectClientLinkRepository, MemberRepository,
)
from marketing.services.project_service import ProjectService
from marketing.services.lead_convert import resolve_or_create_client
from marketing.services.leads_export import build_leads_workbook
from marketing.decorators import mkt_permission_required
from marketing.services import webhook_token
from marketing.services.lead_intake import LEAD_STATUSES
from crm.repositories.client_repository import ClientRepository
from core.utils.api_helpers import get_json_or_error, error_response, safe_error_response

logger = logging.getLogger('jarvis.marketing.routes.leads')

_lead_repo = ProjectLeadRepository()
_webhook_repo = ProjectWebhookRepository()
_activity_repo = ActivityRepository()
_project_repo = ProjectRepository()
_client_link_repo = ProjectClientLinkRepository()
_client_repo = ClientRepository()
_member_repo = MemberRepository()
_service = ProjectService()

_WEBHOOK_PATH = '/marketing/api/webhooks/leads'
_RO_TZ = ZoneInfo('Europe/Bucharest')


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


def _webhook_url():
    """Public webhook URL to display. Force https for real hosts — behind the
    TLS-terminating proxy Flask sees http, but an http URL 301-redirects and the
    redirect drops the POST body/method (client then sees 405). Keep localhost
    on http for local dev."""
    root = request.host_url.rstrip('/')
    if root.startswith('http://') and not any(h in root for h in ('localhost', '127.0.0.1')):
        root = 'https://' + root[len('http://'):]
    return root + _WEBHOOK_PATH


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
    assigned_to = request.args.get('assigned_to') or None
    limit = min(int(request.args.get('limit', 100)), 500)
    offset = int(request.args.get('offset', 0))
    leads = _lead_repo.list_by_project(project_id, status=status, search=search,
                                       assigned_to=assigned_to, limit=limit, offset=offset)
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
    # assigned_to is only touched when the key is present (value may be null = unassign).
    update_kwargs = {'status': status, 'status_notes': status_notes}
    if 'assigned_to' in data:
        assignee = data['assigned_to']
        # A non-null assignee must be a member of THIS project — mirrors the
        # member-only frontend picker and stops assigning to an arbitrary user id.
        if assignee is not None:
            member_ids = {m['user_id'] for m in _member_repo.get_by_project(project_id)}
            if assignee not in member_ids:
                return error_response('Assignee must be a member of this project', 400)
        update_kwargs['assigned_to'] = assignee

    if status is None and status_notes is None and 'assigned_to' not in data:
        return error_response('Nothing to update', 400)

    try:
        updated = _lead_repo.update(project_id, lead_id, **update_kwargs)
        if not updated:
            return error_response('Lead not found', 404)
        _activity_repo.log(project_id, 'lead_updated', actor_id=current_user.id,
                           details={'lead_id': lead_id, 'status': status,
                                    'assigned_to': data.get('assigned_to')})
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


@marketing_bp.route('/api/projects/<int:project_id>/leads/<int:lead_id>/convert', methods=['POST'])
@login_required
@mkt_permission_required('project', 'edit')
def api_convert_lead(project_id, lead_id):
    """Convert a lead into a CRM client, link it to the project, mark converted."""
    denied = _require_project_access(project_id)
    if denied:
        return denied
    # Converting writes to the CRM (creates/links a crm_clients row), so it
    # requires CRM edit rights on top of marketing.project.edit.
    if not getattr(current_user, 'can_edit_crm', False):
        return error_response('CRM edit permission required to convert a lead', 403)
    lead = _lead_repo.get_for_project(project_id, lead_id)
    if not lead:
        return error_response('Lead not found', 404)
    if lead.get('converted_client_id'):
        return error_response('Lead already converted', 409)

    try:
        client_id, created = resolve_or_create_client(_client_repo, lead)
        # Link to the project (idempotent); surfaces in the Clients tab.
        linked = _client_link_repo.link(project_id, client_id, current_user.id) is not None
        _lead_repo.mark_converted(project_id, lead_id, client_id, current_user.id)
        _activity_repo.log(project_id, 'lead_converted', actor_id=current_user.id,
                           details={'lead_id': lead_id, 'client_id': client_id, 'created': created})
        return jsonify({'success': True, 'client_id': client_id,
                        'created': created, 'linked': linked})
    except Exception as e:
        return safe_error_response(e)


@marketing_bp.route('/api/projects/<int:project_id>/leads/export', methods=['GET'])
@login_required
@mkt_permission_required('project', 'view')
def api_export_leads(project_id):
    """Export the (filtered) lead sheet as .xlsx."""
    denied = _require_project_access(project_id)
    if denied:
        return denied
    status = request.args.get('status') or None
    search = request.args.get('search', '').strip() or None
    assigned_to = request.args.get('assigned_to') or None
    try:
        leads = _lead_repo.list_by_project(project_id, status=status, search=search,
                                           assigned_to=assigned_to, limit=10000, offset=0)
        xlsx = build_leads_workbook(leads)
        today = datetime.now(_RO_TZ).strftime('%Y-%m-%d')
        return send_file(
            io.BytesIO(xlsx),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'leads_project_{project_id}_{today}.xlsx',
        )
    except Exception as e:
        return safe_error_response(e)


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
        'webhook_url': _webhook_url(),
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
            'webhook_url': _webhook_url(),
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
