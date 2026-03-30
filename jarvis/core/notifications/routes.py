"""Notification routes.

Notification settings, logs, test email, default column configuration,
in-app notification center (universal — used by all modules),
and push notification manager admin API.
"""
from flask import jsonify, request
from flask_login import login_required, current_user

from . import notifications_bp
from .repositories import NotificationRepository, InAppNotificationRepository, PushCategoryRepository, PushRateLimitRepository
from core.utils.api_helpers import safe_error_response

_notif_repo = NotificationRepository()
_in_app_repo = InAppNotificationRepository()
_cat_repo = PushCategoryRepository()
_rate_repo = PushRateLimitRepository()


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


# ============== Push Notification Manager (Admin) ==============

def _require_admin():
    """Return error response if current user is not admin, else None."""
    if not getattr(current_user, 'can_access_settings', False):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    return None


@notifications_bp.route('/api/push-manager/settings', methods=['GET'])
@login_required
def api_get_push_settings():
    """Get all push manager settings + categories + stats."""
    err = _require_admin()
    if err:
        return err
    try:
        all_settings = _notif_repo.get_settings()
        push_settings = {k: v for k, v in all_settings.items() if k.startswith('push_')}
        categories = _cat_repo.get_all_with_stats()
        stats = _rate_repo.get_stats() or {}

        from .push_service import _device_repo
        stats['active_devices'] = _device_repo.get_active_device_count()

        return jsonify({
            'settings': push_settings,
            'categories': categories,
            'stats': stats,
        })
    except Exception as e:
        return safe_error_response(e)


@notifications_bp.route('/api/push-manager/settings', methods=['POST'])
@login_required
def api_save_push_settings():
    """Save push manager settings (key-value pairs)."""
    err = _require_admin()
    if err:
        return err
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    try:
        # Only allow push_* keys
        filtered = {k: v for k, v in data.items() if k.startswith('push_')}
        if filtered:
            _notif_repo.save_settings_bulk(filtered)
            # Invalidate cache so changes take effect immediately
            from .push_service import get_push_settings_cache
            get_push_settings_cache().invalidate()
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@notifications_bp.route('/api/push-manager/categories', methods=['GET'])
@login_required
def api_get_push_categories():
    """List all push notification categories with 24h usage counts."""
    err = _require_admin()
    if err:
        return err
    try:
        categories = _cat_repo.get_all_with_stats()
        return jsonify({'categories': categories})
    except Exception as e:
        return safe_error_response(e)


@notifications_bp.route('/api/push-manager/categories', methods=['POST'])
@login_required
def api_create_push_category():
    """Create a new push notification category."""
    err = _require_admin()
    if err:
        return err
    data = request.get_json()
    slug = data.get('slug', '').strip().lower()
    name = data.get('name', '').strip()
    if not slug or not name:
        return jsonify({'success': False, 'error': 'slug and name are required'}), 400
    try:
        cat = _cat_repo.create(
            slug=slug, name=name,
            description=data.get('description'),
            priority=data.get('priority', 'normal'),
            max_per_hour=data.get('max_per_hour'),
            ttl_seconds=data.get('ttl_seconds'),
            android_channel_id=data.get('android_channel_id', 'default_notifications'),
        )
        from .push_service import get_push_settings_cache
        get_push_settings_cache().invalidate()
        return jsonify({'success': True, 'category': cat})
    except Exception as e:
        return safe_error_response(e)


@notifications_bp.route('/api/push-manager/categories/<int:category_id>', methods=['PUT'])
@login_required
def api_update_push_category(category_id):
    """Update a push notification category."""
    err = _require_admin()
    if err:
        return err
    data = request.get_json()
    allowed_fields = {'name', 'description', 'priority', 'is_active', 'max_per_hour',
                      'ttl_seconds', 'android_channel_id'}
    fields = {k: v for k, v in data.items() if k in allowed_fields}
    if not fields:
        return jsonify({'success': False, 'error': 'No valid fields to update'}), 400
    try:
        cat = _cat_repo.update(category_id, **fields)
        from .push_service import get_push_settings_cache
        get_push_settings_cache().invalidate()
        return jsonify({'success': True, 'category': cat})
    except Exception as e:
        return safe_error_response(e)


@notifications_bp.route('/api/push-manager/categories/<int:category_id>', methods=['DELETE'])
@login_required
def api_delete_push_category(category_id):
    """Delete a non-builtin push notification category."""
    err = _require_admin()
    if err:
        return err
    try:
        count = _cat_repo.delete(category_id)
        if count == 0:
            return jsonify({'success': False, 'error': 'Category not found or is builtin'}), 404
        from .push_service import get_push_settings_cache
        get_push_settings_cache().invalidate()
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@notifications_bp.route('/api/push-manager/stats', methods=['GET'])
@login_required
def api_get_push_stats():
    """Get push notification statistics for admin dashboard."""
    err = _require_admin()
    if err:
        return err
    try:
        stats = _rate_repo.get_stats() or {}
        from .push_service import _device_repo
        stats['active_devices'] = _device_repo.get_active_device_count()
        return jsonify(stats)
    except Exception as e:
        return safe_error_response(e)


@notifications_bp.route('/api/push-manager/test', methods=['POST'])
@login_required
def api_test_push():
    """Send a test push notification to the current admin user."""
    err = _require_admin()
    if err:
        return err
    try:
        from .push_service import send_push_to_users
        send_push_to_users(
            [current_user.id], 'JARVIS Test',
            'Push notifications are working!',
            data={'type': 'test'},
            category='system',
            bypass_rules=True,
        )
        return jsonify({'success': True, 'message': 'Test notification sent'})
    except Exception as e:
        return safe_error_response(e)
