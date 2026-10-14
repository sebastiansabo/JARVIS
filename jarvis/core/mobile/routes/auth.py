"""Mobile auth endpoints — JWT login, refresh, logout, current-user."""
import threading
from datetime import datetime, timedelta, timezone

from flask import jsonify, request

from core.auth.models import User
from core.auth.services.auth_service import AuthService
from core.auth.repositories import EventRepository
from core.notifications.push_service import send_push_to_users, _DeviceRepo
from core.utils.logging_config import get_logger
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

logger = get_logger('jarvis.mobile.auth')
_event_repo = EventRepository()


def _log_mobile_auth(event_type, description, user_id=None, user_email=None, reason=None, extra=None):
    """Best-effort audit log for mobile auth attempts.

    Mobile login was previously UNAUDITED — no row anywhere for a failed
    mobile login, and telemetry can't see it (pre-session). This closes that
    blind spot. Wrapped so an audit-log failure can NEVER break login.
    `details.platform='mobile'` makes these distinguishable from web rows.
    """
    try:
        details = {'platform': 'mobile'}
        if reason:
            details['reason'] = reason
        if extra:
            details.update(extra)
        _event_repo.log_event(
            event_type=event_type,
            event_description=description,
            user_id=user_id,
            user_email=user_email,
            ip_address=request.remote_addr if request else None,
            user_agent=(request.headers.get('User-Agent', '')[:500] if request else None),
            details=details,
        )
    except Exception as e:
        logger.warning(f'mobile auth audit log failed ({event_type}): {e}')


# ============== AUTH ENDPOINTS ==============

@mobile_bp.route('/api/auth/token', methods=['POST'])
def api_token():
    """JWT login — returns access + refresh tokens."""
    allowed, retry_after = _auth_limiter.is_allowed(
        f'mobile_login:{request.remote_addr}', max_requests=10, window_seconds=300)
    if not allowed:
        _log_mobile_auth('login_failed', 'Mobile login rate-limited', reason='rate_limited')
        return jsonify({'error': f'Too many login attempts. Try again in {retry_after} seconds.'}), 429

    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    identifier = (data.get('identifier') or data.get('email') or '').strip()
    password = data.get('password') or ''

    if not identifier or not password:
        return jsonify({'error': 'Identifier and password are required'}), 400

    via_phone = '@' not in identifier

    user_data = _user_repo.authenticate_identifier(identifier, password)
    if not user_data:
        _log_mobile_auth('login_failed', f'Mobile login failed for {identifier}',
                         user_email=identifier,
                         reason=_user_repo.classify_login_failure(identifier))
        return jsonify({'error': 'Invalid credentials'}), 401

    user = User(user_data)
    is_viewer = (user.role_name or '').strip().lower() == 'viewer'

    # Phone sign-in is restricted to Viewer accounts.
    if via_phone and not is_viewer:
        _log_mobile_auth('login_failed', f'Mobile phone login rejected for non-viewer {identifier}',
                         user_id=user.id, user_email=user.email, reason='phone_login_nonviewer')
        return jsonify({'error': 'Phone sign-in is only available for viewer '
                                 'accounts. Please use your email address.'}), 403

    # Viewers are single-factor — issue tokens immediately, no OTP.
    if is_viewer:
        threading.Thread(target=lambda: _user_repo.update_last_login(user.id), daemon=True).start()
        _log_mobile_auth('login', f'{user.email} logged in (mobile, viewer single-factor)',
                         user_id=user.id, user_email=user.email,
                         extra={'factor': 'viewer', 'via': 'phone' if via_phone else 'email'})
        tokens = _generate_tokens(user.id)
        return jsonify({**tokens, 'user': _user_json(user)})

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
        _log_mobile_auth('login', f'User {user.email} logged in (mobile, trusted device)',
                         user_id=user.id, user_email=user.email,
                         extra={'factor': 'trusted-device'})
        tokens = _generate_tokens(user.id)
        return jsonify({
            **tokens,
            'user': _user_json(user),
        })

    # Untrusted device (or no device_id supplied) — issue an OTP challenge
    svc = AuthService()

    has_push = False
    try:
        has_push = bool(device_id) and bool(_DeviceRepo().get_tokens_for_user_device(user.id, device_id))
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
            _log_mobile_auth('login_failed', f'Mobile OTP generation failed for {user.email}',
                             user_id=user.id, user_email=user.email, reason='otp_generate_failed')
            return jsonify({'error': err or 'Failed to send code'}), 500
        if not ok:
            _log_mobile_auth('login_failed', f'Mobile OTP email send failed for {user.email}',
                             user_id=user.id, user_email=user.email, reason='otp_send_failed')
            return jsonify({'error': err or 'Failed to send verification email'}), 502
        channel = 'email'

    _log_mobile_auth('login_otp_challenged', f'Mobile OTP challenge issued for {user.email}',
                     user_id=user.id, user_email=user.email, extra={'channel': channel})
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
        _log_mobile_auth('login_otp_failed', 'Mobile OTP verify rate-limited', reason='rate_limited')
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
        _log_mobile_auth('login_otp_failed', 'Mobile OTP invalid/expired challenge',
                         reason='invalid_challenge', extra={'challenge_id': challenge_id})
        return jsonify({'error': 'Invalid or expired code'}), 401

    svc = AuthService()
    success, error = svc.verify_otp(challenge_id, code, _JWT_SECRET)
    if not success:
        _log_mobile_auth('login_otp_failed', f'Mobile OTP verification failed for user {otp.get("user_id")}',
                         user_id=otp.get('user_id'), reason='otp_failed', extra={'detail': error})
        return jsonify({'error': error or 'Invalid or expired code'}), 401

    user_data = _user_repo.get_by_id(otp['user_id'])
    if not user_data:
        _log_mobile_auth('login_otp_failed', f'Mobile OTP ok but user {otp.get("user_id")} not found',
                         user_id=otp.get('user_id'), reason='user_not_found')
        return jsonify({'error': 'User not found'}), 401

    user = User(user_data)
    tokens = _generate_tokens(user.id)
    trusted = svc.create_trusted_device_token(user.id, device_id, _JWT_SECRET)

    threading.Thread(target=lambda: _user_repo.update_last_login(user.id), daemon=True).start()
    _log_mobile_auth('login', f'User {user.email} logged in (mobile, OTP verified)',
                     user_id=user.id, user_email=user.email, extra={'factor': 'otp'})

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


@mobile_bp.route('/api/mobile/current-user')
@jwt_required
def api_mobile_current_user_v2():
    """Mobile-unique current-user route (avoids collision with web auth_bp's
    /api/auth/current-user, which is registered first and may shadow the JWT one)."""
    user = _current_mobile_user()
    payload = _user_json(user)

    # Mandatory consent-documents gate status — single 2-query pass (never
    # call is_complete()/pending_count() separately; this endpoint runs on
    # ~every mobile app open/resume).
    from core.consents.services.consent_service import ConsentService as _ConsentSvc
    _consent_status = _ConsentSvc().get_status(user.id)
    payload['consents_complete'] = _consent_status['complete']
    payload['pending_consents_count'] = _consent_status['pending_count']

    return jsonify({'authenticated': True, 'user': payload})
