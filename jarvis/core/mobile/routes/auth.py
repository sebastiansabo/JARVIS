"""Mobile auth endpoints — JWT login, refresh, logout, current-user."""
import threading

from flask import jsonify, request

from core.auth.models import User
from ._shared import (
    mobile_bp,
    jwt_required,
    _user_repo,
    _auth_limiter,
    _generate_tokens,
    _decode_token,
    _current_mobile_user,
    _user_json,
    _revoked_tokens,
    _JWT_SECRET,
)


# ============== AUTH ENDPOINTS ==============

@mobile_bp.route('/api/auth/token', methods=['POST'])
def api_token():
    """JWT login — returns access + refresh tokens."""
    allowed, retry_after = _auth_limiter.is_allowed(
        f'mobile_login:{request.remote_addr}', max_requests=10, window_seconds=300)
    if not allowed:
        return jsonify({'error': f'Too many login attempts. Try again in {retry_after} seconds.'}), 429

    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    email = (data.get('email') or '').strip()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400

    user_data = _user_repo.authenticate(email, password)
    if not user_data:
        return jsonify({'error': 'Invalid email or password'}), 401

    user = User(user_data)
    tokens = _generate_tokens(user.id)

    # Update last_login in background
    threading.Thread(target=lambda: _user_repo.update_last_login(user.id), daemon=True).start()

    return jsonify({
        **tokens,
        'user': _user_json(user),
    })


@mobile_bp.route('/api/auth/refresh', methods=['POST'])
def api_refresh():
    """Refresh access token using refresh token."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    refresh_token = data.get('refresh_token') or ''
    payload = _decode_token(refresh_token, _JWT_SECRET)

    if not payload or payload.get('type') != 'refresh':
        return jsonify({'error': 'Invalid or expired refresh token'}), 401

    jti = payload.get('jti', '')
    if jti in _revoked_tokens:
        return jsonify({'error': 'Token has been revoked'}), 401

    user_data = _user_repo.get_by_id(payload['sub'])
    if not user_data or not user_data.get('is_active', True):
        return jsonify({'error': 'User not found or inactive'}), 401

    # Revoke old refresh token and issue new pair
    _revoked_tokens.add(jti)
    tokens = _generate_tokens(payload['sub'])

    return jsonify(tokens)


@mobile_bp.route('/api/auth/logout', methods=['POST'])
@jwt_required
def api_mobile_logout():
    """Revoke refresh token on logout."""
    data = request.get_json() or {}
    refresh_token = data.get('refresh_token')
    if refresh_token:
        payload = _decode_token(refresh_token, _JWT_SECRET)
        if payload and payload.get('jti'):
            _revoked_tokens.add(payload['jti'])
    return jsonify({'success': True})


@mobile_bp.route('/api/auth/current-user')
@jwt_required
def api_mobile_current_user():
    """Get current user info for mobile app."""
    user = _current_mobile_user()
    return jsonify({'authenticated': True, 'user': _user_json(user)})
