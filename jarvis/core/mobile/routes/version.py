"""Mobile app version check and update notification endpoints."""
from flask import jsonify, request

from ._shared import (
    mobile_bp,
    jwt_required,
    _CURRENT_VERSION,
    _CURRENT_VERSION_CODE,
    _DOWNLOAD_URL,
    _device_repo,
    _current_mobile_user,
)


# ============== APP VERSION CHECK ==============

@mobile_bp.route('/api/mobile/version')
def api_mobile_version():
    """Public endpoint — returns latest app version and download URL."""
    return jsonify({
        'version': _CURRENT_VERSION,
        'version_code': _CURRENT_VERSION_CODE,
        'download_url': _DOWNLOAD_URL,
        'force_update': False,
    })


@mobile_bp.route('/api/mobile/notify-update', methods=['POST'])
@jwt_required
def api_notify_update():
    """Send push notification to ALL registered devices about a new app version.
    Requires admin/HR manager role."""
    from core.notifications.push_service import send_push_to_users

    user = _current_mobile_user()
    if not getattr(user, 'is_hr_manager', False) and user.id != 1:
        return jsonify({'error': 'Admin access required'}), 403

    data = request.get_json() or {}
    version = data.get('version', _CURRENT_VERSION)

    # Get ALL user_ids with registered devices
    user_ids = _device_repo.get_all_user_ids()

    if not user_ids:
        return jsonify({'success': True, 'message': 'No devices registered', 'notified': 0})

    send_push_to_users(
        user_ids=user_ids,
        title='JARVIS Update Available',
        body=f'A new version ({version}) is available. Tap to update.',
        data={
            'type': 'app_update',
            'version': version,
            'download_url': _DOWNLOAD_URL,
        },
        category='system',
        bypass_rules=True,
    )

    return jsonify({'success': True, 'notified': len(user_ids)})
