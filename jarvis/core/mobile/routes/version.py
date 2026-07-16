"""Mobile app version check and update notification endpoints."""
import json
import os

from flask import current_app, jsonify, request

from ._shared import (
    mobile_bp,
    jwt_required,
    _CURRENT_VERSION,
    _CURRENT_VERSION_CODE,
    _DOWNLOAD_URL,
    _device_repo,
    _current_mobile_user,
)

_MOBILE2_APP_KEYS = {'mobile2', 'jarvis2', 'com.jarvis.mobile2'}
_MOBILE2_DOWNLOAD_URL = 'https://jarvis.autoworld.ro/download/jarvis2.apk'


def _mobile2_version():
    """Latest jarvis-mobile-2 version, read from the CI-published manifest
    (jarvis2-version.json, written next to jarvis2.apk). Falls back to a baseline
    if the manifest isn't published yet so the app's update check never errors."""
    try:
        path = os.path.join(current_app.static_folder, 'downloads', 'jarvis2-version.json')
        with open(path) as f:
            data = json.load(f)
        return {
            'version': data.get('version', '2.0.0'),
            'version_code': int(data.get('version_code', 1)),
            'download_url': data.get('download_url', _MOBILE2_DOWNLOAD_URL),
            'force_update': bool(data.get('force_update', False)),
        }
    except Exception:
        return {
            'version': '2.0.0',
            'version_code': 1,
            'download_url': _MOBILE2_DOWNLOAD_URL,
            'force_update': False,
        }


# ============== APP VERSION CHECK ==============

@mobile_bp.route('/api/mobile/version')
def api_mobile_version():
    """Public endpoint — latest app version and download URL.

    `?app=mobile2` reports jarvis-mobile-2 (com.jarvis.mobile2) from its
    CI-published manifest; default reports the original app (com.jarvis.mobile).
    """
    if (request.args.get('app') or '').lower() in _MOBILE2_APP_KEYS:
        return jsonify(_mobile2_version())
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
