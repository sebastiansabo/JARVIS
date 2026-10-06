"""Public (unauthenticated) webhook intake for project leads.

External systems (Zapier, Facebook Lead Ads, landing pages) POST a lead here.
Auth is a per-project Bearer token (mkt_project_webhooks): the token selects
the target project, so the request body never carries a project id. This
never relies on a logged-in session.

    POST /marketing/api/webhooks/leads
    Authorization: Bearer whk_xxx
    { "contact_name": "...", "phone": "...", "email": "...", "source": "..." }
"""
import logging

from flask import Blueprint, request, jsonify

from marketing.repositories.webhook_repo import ProjectWebhookRepository
from marketing.repositories.lead_repo import ProjectLeadRepository
from marketing.repositories.activity_repo import ActivityRepository
from marketing.services import webhook_token
from marketing.services.lead_intake import normalize_lead_payload
from core.utils.api_helpers import RateLimiter, safe_error_response

logger = logging.getLogger('jarvis.marketing.routes.leads_webhook')

leads_webhook_bp = Blueprint('leads_webhook', __name__)

_webhook_repo = ProjectWebhookRepository()
_lead_repo = ProjectLeadRepository()
_activity_repo = ActivityRepository()
_rate_limiter = RateLimiter()      # per-token (defence in depth)
_ip_rate_limiter = RateLimiter()   # per-IP, pre-auth

_MAX_BODY = 1_048_576   # 1 MB
_RATE_MAX = 60          # requests per token / window
_RATE_WINDOW = 60       # seconds
_IP_RATE_MAX = 120      # per-IP / window (generous — a caller sends one lead at a time)
_IP_RATE_WINDOW = 60

# NOTE: RateLimiter is per-gunicorn-worker in-memory state (see api_helpers), so the
# effective ceiling is workers x limit and it resets on deploy. Accepted for v1; a
# shared/DB-backed limiter is a later hardening step.


def _bearer_token():
    """Extract the Bearer token from the Authorization header, or None."""
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        return auth[len('Bearer '):].strip() or None
    return None


def _client_ip():
    """Best-effort client IP, honoring a single-hop X-Forwarded-For (mirrors forms/public)."""
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip and ',' in ip:
        ip = ip.split(',')[0].strip()
    return ip or '0.0.0.0'


def _rate_limited_response(retry_after):
    resp = jsonify({'success': False, 'error': 'Rate limit exceeded'})
    resp.headers['Retry-After'] = str(retry_after)
    return resp, 429


@leads_webhook_bp.route('/leads', methods=['POST'])
def intake_lead():
    # Cheap per-IP throttle BEFORE any DB work, so invalid-token floods can't
    # hammer the token lookup.
    ok, retry_after = _ip_rate_limiter.is_allowed(
        f'leadhook-ip:{_client_ip()}', max_requests=_IP_RATE_MAX, window_seconds=_IP_RATE_WINDOW)
    if not ok:
        return _rate_limited_response(retry_after)

    token = _bearer_token()
    if not token:
        return jsonify({'success': False, 'error': 'Missing bearer token'}), 401

    webhook = _webhook_repo.resolve_active(webhook_token.hash_token(token))
    if not webhook:
        return jsonify({'success': False, 'error': 'Invalid token'}), 401

    # Per-token throttle (the project is one logical caller).
    allowed, retry_after = _rate_limiter.is_allowed(
        f'leadhook:{webhook["id"]}', max_requests=_RATE_MAX, window_seconds=_RATE_WINDOW)
    if not allowed:
        return _rate_limited_response(retry_after)

    if request.content_length and request.content_length > _MAX_BODY:
        return jsonify({'success': False, 'error': 'Request too large'}), 413

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'success': False, 'error': 'Invalid or missing JSON body'}), 400

    try:
        payload = normalize_lead_payload(data)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    project_id = webhook['project_id']
    try:
        lead_id = _lead_repo.create(
            project_id, payload, received_via='webhook', webhook_id=webhook['id'])
        _webhook_repo.touch_last_used(webhook['id'])
    except Exception as e:
        return safe_error_response(e)

    try:
        _activity_repo.log(project_id, 'lead_received', actor_id=None, actor_type='webhook',
                           details={'lead_id': lead_id, 'source': payload.get('source')})
    except Exception:
        logger.exception('Failed to log lead_received activity for project %s', project_id)

    return jsonify({'success': True, 'lead_id': lead_id}), 201
