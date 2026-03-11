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

_VALID_COLUMN_PAGES = [
    'accounting', 'crm_deals', 'crm_clients', 'dms', 'marketing', 'efactura',
]


@notifications_bp.route('/api/default-columns', methods=['GET'])
@login_required
def api_get_default_columns():
    """Get default column configurations for all pages."""
    import json
    settings = _notif_repo.get_settings()
    result = {}
    for page in _VALID_COLUMN_PAGES:
        raw = settings.get(f'default_columns_{page}')
        version = settings.get(f'default_columns_{page}_version', '0')
        if raw:
            try:
                cols = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                cols = None
        else:
            cols = None
        result[page] = {'columns': cols, 'version': int(version) if version else 0}
    return jsonify(result)


@notifications_bp.route('/api/default-columns', methods=['POST'])
@login_required
def api_set_default_columns():
    """Set default column configuration (admin only)."""
    import json
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Permission denied'}), 403

    data = request.get_json()
    page = data.get('page') or data.get('tab')
    columns = data.get('columns') or data.get('config')
    apply_to_all = data.get('apply_to_all', False)

    if not page or not columns:
        return jsonify({'success': False, 'error': 'page and columns are required'}), 400

    if page not in _VALID_COLUMN_PAGES:
        return jsonify({'success': False, 'error': f'Invalid page. Must be one of: {_VALID_COLUMN_PAGES}'}), 400

    if not isinstance(columns, list):
        return jsonify({'success': False, 'error': 'columns must be an array'}), 400

    try:
        _notif_repo.save_setting(f'default_columns_{page}', json.dumps(columns))

        if apply_to_all:
            settings = _notif_repo.get_settings()
            cur_version = int(settings.get(f'default_columns_{page}_version', '0') or '0')
            _notif_repo.save_setting(f'default_columns_{page}_version', str(cur_version + 1))

        from core.auth.repositories import EventRepository
        action = 'applied to all users' if apply_to_all else 'saved as default'
        EventRepository().log_event('default_columns_set', event_description=f'Column defaults for {page} {action}')
        return jsonify({'success': True, 'message': f'Default columns set for {page}'})
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
