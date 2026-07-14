"""Mobile auth endpoints — JWT login, refresh, logout, current-user."""
import threading
from datetime import datetime, timedelta, timezone

from flask import jsonify, request

from core.auth.models import User
from core.auth.services.auth_service import AuthService
from core.notifications.push_service import send_push_to_users, _DeviceRepo
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

    device_id = (data.get('device_id') or '').strip()
    trusted_token = data.get('trusted_device_token')

    is_trusted = False
    if device_id and trusted_token:
        svc = AuthService()
        try:
            is_trusted = svc.validate_trusted_device_token(trusted_token, user.id, device_id, _JWT_SECRET)
        except Exception:
            is_trusted = False

    if is_trusted:
        # Trusted device — login completes now, so it's safe to record it.
        threading.Thread(target=lambda: _user_repo.update_last_login(user.id), daemon=True).start()
        tokens = _generate_tokens(user.id)
        return jsonify({
            **tokens,
            'user': _user_json(user),
        })

    # Untrusted device (or no device_id supplied) — issue an OTP challenge
    svc = AuthService()

    has_push = False
    try:
        has_push = bool(_DeviceRepo().get_tokens_for_users([user.id]))
    except Exception:
        has_push = False

    if has_push:
        code = svc._generate_otp_code()
        otp_id = _user_repo.create_otp(
            user.id,
            svc._hash_otp(code, _JWT_SECRET),
            datetime.now(timezone.utc) + timedelta(minutes=svc.OTP_EXPIRY_MINUTES),
        )
        send_push_to_users(
            [user.id],
            'JARVIS',
            f'Cod de autentificare: {code}',
            data={'type': 'login_otp', 'code': code},
            category='system',
            bypass_rules=True,
        )
        channel = 'push'
    else:
        otp_id, ok, err = svc.generate_and_send_otp(user.id, user.email, user.name, _JWT_SECRET)
        if not otp_id:
            return jsonify({'error': err or 'Failed to send code'}), 500
        if not ok:
            return jsonify({'error': err or 'Failed to send verification email'}), 502
        channel = 'email'

    return jsonify({
        'otp_required': True,
        'challenge_id': otp_id,
        'channel': channel,
    })


@mobile_bp.route('/api/auth/verify-otp', methods=['POST'])
def api_verify_otp():
    """Verify a mobile-login OTP challenge and issue tokens + a trusted-device token."""
    allowed, retry_after = _auth_limiter.is_allowed(
        f'mobile_verify:{request.remote_addr}', max_requests=10, window_seconds=300)
    if not allowed:
        return jsonify({'error': f'Too many attempts. Try again in {retry_after} seconds.'}), 429

    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    challenge_id = data.get('challenge_id')
    code = (data.get('code') or '').strip()
    device_id = (data.get('device_id') or '').strip()

    if not challenge_id or not code:
        return jsonify({'error': 'challenge_id and code are required'}), 400

    otp = _user_repo.get_otp(challenge_id)
    if not otp or otp.get('used_at'):
        return jsonify({'error': 'Invalid or expired code'}), 401

    svc = AuthService()
    success, error = svc.verify_otp(challenge_id, code, _JWT_SECRET)
    if not success:
        return jsonify({'error': error or 'Invalid or expired code'}), 401

    user_data = _user_repo.get_by_id(otp['user_id'])
    if not user_data:
        return jsonify({'error': 'User not found'}), 401

    user = User(user_data)
    tokens = _generate_tokens(user.id)
    trusted = svc.create_trusted_device_token(user.id, device_id, _JWT_SECRET)

    threading.Thread(target=lambda: _user_repo.update_last_login(user.id), daemon=True).start()

    return jsonify({
        **tokens,
        'user': _user_json(user),
        'trusted_device_token': trusted,
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
