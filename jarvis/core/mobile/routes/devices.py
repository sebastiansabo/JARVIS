"""Mobile device registration endpoints — push notification token management."""
from flask import jsonify, request

from ._shared import mobile_bp, jwt_required, _device_repo, _current_mobile_user


# ============== DEVICE REGISTRATION (Push Notifications) ==============

@mobile_bp.route('/api/devices/register', methods=['POST'])
@jwt_required
def api_register_device():
    """Register device push token for notifications."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    push_token = data.get('push_token') or ''
    platform = data.get('platform', 'unknown')  # ios | android
    device_id = data.get('device_id') or ''

    if not push_token:
        return jsonify({'error': 'push_token is required'}), 400

    user = _current_mobile_user()
    _device_repo.register(user.id, push_token, platform, device_id)
    return jsonify({'success': True})


@mobile_bp.route('/api/devices/unregister', methods=['POST'])
@jwt_required
def api_unregister_device():
    """Unregister device push token."""
    data = request.get_json() or {}
    push_token = data.get('push_token')
    if not push_token:
        return jsonify({'error': 'push_token required'}), 400

    _device_repo.unregister(push_token, _current_mobile_user().id)
    return jsonify({'success': True})
