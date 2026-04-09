"""Connecteam connector API routes.

Webhook endpoint is PUBLIC (no login required) — secured by HMAC signature.
Admin endpoints require admin_required decorator.
User-scoped endpoints use v2_permission_required.
"""

import logging
from flask import request, jsonify, g
from flask_login import current_user

from . import connecteam_bp
from .services import ConnecteamService
from core.utils.api_helpers import api_login_required, admin_required, safe_error_response, v2_permission_required

logger = logging.getLogger('jarvis.connecteam.routes')
service = ConnecteamService()


# ── PUBLIC WEBHOOK ENDPOINT (no login required) ──

@connecteam_bp.route('/webhook/form-submission', methods=['POST'])
def webhook_form_submission():
    """Receive Connecteam webhook POST.

    Security: Verify HMAC signature if webhook_secret is configured.
    Returns 200 quickly to avoid Connecteam retries.
    """
    try:
        raw_body = request.get_data()
        signature = request.headers.get('X-Connecteam-Signature', '')
        payload = request.get_json(silent=True)

        if not payload:
            return jsonify({'status': 'error', 'message': 'Invalid JSON payload'}), 400

        # Verify signature
        if not service.verify_webhook(raw_body, signature):
            logger.warning('Webhook signature verification failed (request_id=%s)',
                           payload.get('requestId', 'unknown'))
            return jsonify({'status': 'error', 'message': 'Invalid signature'}), 401

        # Process webhook
        result = service.process_webhook(payload)
        return jsonify({'status': 'ok', **result}), 200

    except Exception as e:
        logger.exception('Webhook processing error: %s', e)
        return jsonify({'status': 'error', 'message': str(e)}), 200  # Return 200 to avoid retries


# ── Connection Config (admin only) ──

@connecteam_bp.route('/api/config', methods=['GET'])
@admin_required
def get_config():
    """Get Connecteam connection configuration."""
    config = service.get_connection_config()
    return jsonify({'success': True, 'data': config})


@connecteam_bp.route('/api/config', methods=['POST'])
@admin_required
def save_config():
    """Save Connecteam OAuth credentials."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Request body required'}), 400

    client_id = data.get('client_id')
    client_secret = data.get('client_secret')
    webhook_secret = data.get('webhook_secret')

    if not client_id or not client_secret:
        return jsonify({'success': False, 'error': 'client_id and client_secret are required'}), 400

    try:
        connector_id = service.save_connection(client_id, client_secret, webhook_secret)
        return jsonify({'success': True, 'connector_id': connector_id})
    except Exception as e:
        return safe_error_response(e)


@connecteam_bp.route('/api/test-connection', methods=['POST'])
@admin_required
def test_connection():
    """Test OAuth connectivity."""
    try:
        result = service.test_connection()
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@connecteam_bp.route('/api/status', methods=['GET'])
@api_login_required
def get_status():
    """Get connector status summary."""
    try:
        status = service.get_status()
        return jsonify({'success': True, 'data': status})
    except Exception as e:
        return safe_error_response(e)


# ── Webhook Management (admin) ──

@connecteam_bp.route('/api/webhooks', methods=['GET'])
@admin_required
def list_webhooks():
    """List registered webhooks in Connecteam."""
    try:
        result = service.list_webhooks()
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return safe_error_response(e)


@connecteam_bp.route('/api/webhooks/register', methods=['POST'])
@admin_required
def register_webhook():
    """Register JARVIS webhook with Connecteam API."""
    data = request.get_json(silent=True) or {}
    callback_url = data.get('callback_url')

    if not callback_url:
        # Default to staging URL
        callback_url = 'https://mkt-app-922ou.ondigitalocean.app/connecteam/webhook/form-submission'

    try:
        result = service.register_webhook(callback_url)
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return safe_error_response(e)


@connecteam_bp.route('/api/webhooks/<int:webhook_id>', methods=['DELETE'])
@admin_required
def delete_webhook(webhook_id):
    """Delete a registered webhook."""
    try:
        service.delete_webhook(webhook_id)
        return jsonify({'success': True, 'message': 'Webhook deleted'})
    except Exception as e:
        return safe_error_response(e)


# ── Webhook Log (admin) ──

@connecteam_bp.route('/api/webhook-log', methods=['GET'])
@admin_required
def get_webhook_log():
    """Get recent webhook events for debugging."""
    limit = min(request.args.get('limit', 50, type=int), 200)
    try:
        logs = service.repo.get_webhook_log(limit)
        return jsonify({'success': True, 'data': logs})
    except Exception as e:
        return safe_error_response(e)


# ── User Mapping (admin) ──

@connecteam_bp.route('/api/users', methods=['GET'])
@admin_required
def get_users():
    """List Connecteam users with mapping status."""
    active_only = request.args.get('active_only', 'true').lower() == 'true'
    try:
        users = service.repo.get_all_users(active_only)
        return jsonify({'success': True, 'data': users})
    except Exception as e:
        return safe_error_response(e)


@connecteam_bp.route('/api/users/auto-map', methods=['POST'])
@admin_required
def auto_map_users():
    """Auto-map Connecteam users to JARVIS users by email/phone/name."""
    try:
        result = service.auto_map_users()
        return jsonify(result)
    except Exception as e:
        return safe_error_response(e)


@connecteam_bp.route('/api/users/mapping', methods=['PUT'])
@admin_required
def update_mapping():
    """Manually map a Connecteam user to a JARVIS user."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Request body required'}), 400

    connecteam_user_id = data.get('connecteam_user_id')
    jarvis_user_id = data.get('jarvis_user_id')

    if not connecteam_user_id or not jarvis_user_id:
        return jsonify({'success': False, 'error': 'connecteam_user_id and jarvis_user_id required'}), 400

    try:
        service.update_user_mapping(connecteam_user_id, jarvis_user_id)
        return jsonify({'success': True, 'message': 'Mapping updated'})
    except Exception as e:
        return safe_error_response(e)


@connecteam_bp.route('/api/users/mapping', methods=['DELETE'])
@admin_required
def remove_mapping():
    """Remove mapping for a Connecteam user."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Request body required'}), 400

    connecteam_user_id = data.get('connecteam_user_id')
    if not connecteam_user_id:
        return jsonify({'success': False, 'error': 'connecteam_user_id required'}), 400

    try:
        service.remove_user_mapping(connecteam_user_id)
        return jsonify({'success': True, 'message': 'Mapping removed'})
    except Exception as e:
        return safe_error_response(e)


# ── Submissions (user-scoped) ──

@connecteam_bp.route('/api/submissions/employee/<int:user_id>', methods=['GET'])
@api_login_required
@v2_permission_required('hr', 'leave_permissions', 'view')
def get_employee_submissions(user_id):
    """Get leave permission submissions for an employee (V2 permission scoped)."""
    from hr.events.database import get_managed_employee_ids

    scope = getattr(g, 'permission_scope', 'all')

    # Allow own data always; for others, check scope
    if user_id != current_user.id:
        if scope == 'own':
            return jsonify({'success': False, 'error': 'Permission denied'}), 403
        if scope == 'department':
            managed_ids = get_managed_employee_ids(current_user.id)
            if user_id not in (managed_ids or []):
                return jsonify({'success': False, 'error': 'Permission denied'}), 403

    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)

    try:
        data = service.get_user_submissions(user_id, year, month)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return safe_error_response(e)


@connecteam_bp.route('/api/submissions/recent', methods=['GET'])
@admin_required
def get_recent_submissions():
    """Get most recent submissions across all users (admin only)."""
    limit = min(request.args.get('limit', 50, type=int), 200)
    try:
        data = service.repo.get_recent_submissions(limit)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return safe_error_response(e)
