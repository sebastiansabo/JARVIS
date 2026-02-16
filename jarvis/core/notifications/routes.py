"""Notification routes.

Notification settings, logs, test email, default column configuration,
and in-app notification center (universal — used by all modules).
"""
from flask import jsonify, request
from flask_login import login_required, current_user

from . import notifications_bp
from .repositories import NotificationRepository, InAppNotificationRepository
from core.utils.api_helpers import safe_error_response

_notif_repo = NotificationRepository()
_in_app_repo = InAppNotificationRepository()


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


# ============== In-App Notification Center ==============

@notifications_bp.route('/notifications/api/list', methods=['GET'])
@login_required
def api_get_in_app_notifications():
    """Get current user's in-app notifications."""
    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', 0, type=int)
    unread_only = request.args.get('unread_only', 'false').lower() == 'true'
    notifications = _in_app_repo.get_for_user(current_user.id, limit=limit, offset=offset, unread_only=unread_only)
    return jsonify({'notifications': notifications})


@notifications_bp.route('/notifications/api/unread-count', methods=['GET'])
@login_required
def api_get_unread_count():
    """Get count of unread notifications for current user."""
    count = _in_app_repo.get_unread_count(current_user.id)
    return jsonify({'count': count})


@notifications_bp.route('/notifications/api/mark-read/<int:notification_id>', methods=['POST'])
@login_required
def api_mark_read(notification_id):
    """Mark a single notification as read."""
    updated = _in_app_repo.mark_read(notification_id, current_user.id)
    return jsonify({'success': updated})


@notifications_bp.route('/notifications/api/mark-all-read', methods=['POST'])
@login_required
def api_mark_all_read():
    """Mark all notifications as read for current user."""
    count = _in_app_repo.mark_all_read(current_user.id)
    return jsonify({'success': True, 'count': count})
