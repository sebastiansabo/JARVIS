"""GPS check-in API routes."""

from functools import wraps
from flask import request, jsonify
from flask_login import current_user

from . import checkin_bp
from .service import CheckinService
from core.utils.api_helpers import safe_error_response

service = CheckinService()


def _login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated


def _admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        if not getattr(current_user, 'can_access_settings', False):
            return jsonify({'success': False, 'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated


# ── User endpoints ──

@checkin_bp.route('/api/locations', methods=['GET'])
@_login_required
def get_locations():
    try:
        show_all = request.args.get('all', '').lower() == 'true'
        active_only = not (show_all and getattr(current_user, 'can_access_settings', False))
        locations = service.get_locations(active_only=active_only)
        return jsonify({'success': True, 'data': locations})
    except Exception as e:
        return safe_error_response(e)


@checkin_bp.route('/api/status', methods=['GET'])
@_login_required
def get_status():
    try:
        result = service.get_status(current_user.id)
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return safe_error_response(e)


@checkin_bp.route('/api/punch', methods=['POST'])
@_login_required
def punch():
    try:
        data = request.get_json() or {}
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if client_ip and ',' in client_ip:
            client_ip = client_ip.split(',')[0].strip()

        result = service.punch(
            jarvis_user_id=current_user.id,
            lat=data.get('lat'),
            lng=data.get('lng'),
            direction=data.get('direction'),
            client_ip=client_ip,
            qr_token=data.get('qr_token'),
        )
        status_code = 200 if result['success'] else 400
        return jsonify(result), status_code
    except Exception as e:
        return safe_error_response(e)


# ── Admin endpoints ──

@checkin_bp.route('/api/locations', methods=['POST'])
@_admin_required
def create_location():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data'}), 400
        for field in ('name', 'latitude', 'longitude'):
            if field not in data:
                return jsonify({'success': False, 'error': f'{field} is required'}), 400
        loc = service.create_location(
            name=data['name'],
            latitude=data['latitude'],
            longitude=data['longitude'],
            radius=data.get('allowed_radius_meters', 50),
            allowed_ips=data.get('allowed_ips', []),
            created_by=current_user.id,
            auto_checkout_radius=data.get('auto_checkout_radius_meters', 200),
        )
        return jsonify({'success': True, 'data': loc})
    except Exception as e:
        return safe_error_response(e)


@checkin_bp.route('/api/locations/<int:location_id>', methods=['PUT'])
@_admin_required
def update_location(location_id):
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data'}), 400
        loc = service.update_location(
            location_id=location_id,
            name=data.get('name', ''),
            latitude=data.get('latitude', 0),
            longitude=data.get('longitude', 0),
            radius=data.get('allowed_radius_meters', 50),
            is_active=data.get('is_active', True),
            allowed_ips=data.get('allowed_ips', []),
            auto_checkout_radius=data.get('auto_checkout_radius_meters', 200),
        )
        return jsonify({'success': True, 'data': loc})
    except Exception as e:
        return safe_error_response(e)


@checkin_bp.route('/api/locations/<int:location_id>', methods=['DELETE'])
@_admin_required
def delete_location(location_id):
    try:
        service.delete_location(location_id)
        return jsonify({'success': True, 'message': 'Location deleted'})
    except Exception as e:
        return safe_error_response(e)
