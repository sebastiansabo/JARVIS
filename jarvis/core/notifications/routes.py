"""Notification routes.

Notification settings, logs, test email, and default column configuration.
"""
from flask import jsonify, request
from flask_login import login_required, current_user

from . import notifications_bp
from .repositories import NotificationRepository
from core.utils.api_helpers import safe_error_response

_notif_repo = NotificationRepository()


@notifications_bp.route('/api/notification-settings', methods=['GET'])
@login_required
def api_get_notification_settings():
    """Get all notification settings."""
    settings = _notif_repo.get_settings()
    return jsonify(settings)


@notifications_bp.route('/api/notification-settings', methods=['POST'])
@login_required
def api_save_notification_settings():
    """Save notification settings."""
    data = request.get_json()
    try:
        _notif_repo.save_settings_bulk(data)
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@notifications_bp.route('/api/notification-logs', methods=['GET'])
@login_required
def api_get_notification_logs():
    """Get notification logs with optional filters."""
    limit = request.args.get('limit', 100, type=int)
    logs = _notif_repo.get_logs(limit=limit)
    return jsonify(logs)


@notifications_bp.route('/api/notification-settings/test', methods=['POST'])
@login_required
def api_test_email():
    """Send a test email to verify SMTP configuration."""
    try:
        from core.services.notification_service import send_test_email, is_smtp_configured
    except ImportError:
        return jsonify({'success': False, 'error': 'Notifications module not available'}), 500

    if not is_smtp_configured():
        return jsonify({'success': False, 'error': 'SMTP not configured'}), 500

    data = request.get_json()
    to_email = data.get('email')
    if not to_email:
        return jsonify({'success': False, 'error': 'Email address is required'}), 400

    success, error_message = send_test_email(to_email)
    if success:
        return jsonify({'success': True, 'message': f'Test email sent to {to_email}'})
    return jsonify({'success': False, 'error': error_message}), 500


# ============== Default Column Configuration ==============

@notifications_bp.route('/api/default-columns', methods=['GET'])
@login_required
def api_get_default_columns():
    """Get default column configurations for all tabs."""
    settings = _notif_repo.get_settings()
    return jsonify({
        'accounting': settings.get('default_columns_accounting'),
        'company': settings.get('default_columns_company'),
        'department': settings.get('default_columns_department'),
        'brand': settings.get('default_columns_brand')
    })


@notifications_bp.route('/api/default-columns', methods=['POST'])
@login_required
def api_set_default_columns():
    """Set default column configuration (admin only)."""
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json()
    tab = data.get('tab')
    config = data.get('config')

    if not tab or not config:
        return jsonify({'success': False, 'error': 'Tab and config are required'}), 400

    valid_tabs = ['accounting', 'company', 'department', 'brand']
    if tab not in valid_tabs:
        return jsonify({'success': False, 'error': f'Invalid tab. Must be one of: {valid_tabs}'}), 400

    try:
        setting_key = f'default_columns_{tab}'
        _notif_repo.save_setting(setting_key, config)
        from core.auth.repositories import EventRepository
        EventRepository().log_event('default_columns_set', event_description=f'Set default column config for {tab} tab')
        return jsonify({'success': True, 'message': f'Default columns set for {tab} tab'})
    except Exception as e:
        return safe_error_response(e)
