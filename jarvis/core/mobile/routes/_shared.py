"""Mobile API routes — shared infrastructure (blueprint, repos, JWT helpers, CORS)."""

__all__ = [
    'mobile_bp',
    '_user_repo',
    '_auth_limiter',
    '_device_repo',
    '_dashboard_repo',
    '_checkin_repo',
    '_sig_repo',
    '_JWT_SECRET',
    '_JWT_ACCESS_TTL',
    '_JWT_REFRESH_TTL',
    '_revoked_tokens',
    '_CURRENT_VERSION',
    '_CURRENT_VERSION_CODE',
    '_DOWNLOAD_URL',
    '_b64url_encode',
    '_b64url_decode',
    '_create_token',
    '_decode_token',
    '_generate_tokens',
    'jwt_required',
    '_current_mobile_user',
    '_user_json',
]

import os
import time
import hmac
import hashlib
import json
import threading
from functools import wraps
from datetime import datetime, timedelta, timezone

from flask import jsonify, request

from .. import mobile_bp
from core.auth.repositories import UserRepository
from core.auth.models import User
from core.utils.api_helpers import RateLimiter
from core.connectors.push.repositories import DeviceRepository
from core.mobile.repositories import MobileDashboardRepository
from core.checkin.repository import CheckinRepository
from core.signatures.repositories.signature_repo import SignatureRepository

_user_repo = UserRepository()
_auth_limiter = RateLimiter()
_device_repo = DeviceRepository()
_dashboard_repo = MobileDashboardRepository()
_checkin_repo = CheckinRepository()
_sig_repo = SignatureRepository()



@mobile_bp.route('/api/auth/token', methods=['OPTIONS'])
@mobile_bp.route('/api/auth/verify-otp', methods=['OPTIONS'])
@mobile_bp.route('/api/auth/refresh', methods=['OPTIONS'])
@mobile_bp.route('/api/auth/logout', methods=['OPTIONS'])
@mobile_bp.route('/api/auth/current-user', methods=['OPTIONS'])
@mobile_bp.route('/api/mobile/current-user', methods=['OPTIONS'])
@mobile_bp.route('/api/mobile/dashboard', methods=['OPTIONS'])
@mobile_bp.route('/api/mobile/widget-data', methods=['OPTIONS'])
@mobile_bp.route('/api/mobile/version', methods=['OPTIONS'])
@mobile_bp.route('/api/mobile/notify-update', methods=['OPTIONS'])
@mobile_bp.route('/api/devices/register', methods=['OPTIONS'])
@mobile_bp.route('/api/devices/unregister', methods=['OPTIONS'])
@mobile_bp.route('/api/checkin/nfc-punch', methods=['OPTIONS'])
@mobile_bp.route('/api/checkin/nfc-tags', methods=['OPTIONS'])
@mobile_bp.route('/api/signatures/sign-mobile', methods=['OPTIONS'])
def _cors_preflight():
    """Handle CORS preflight requests."""
    return '', 204


# JWT config
def _resolve_jwt_secret() -> str:
    """Resolve the JWT signing secret.

    Uses JWT_SECRET_KEY (or FLASK_SECRET_KEY) when set. If neither is
    configured, fail HARD in production rather than signing tokens with a
    public, hardcoded default — that default let anyone forge a valid token.
    Outside production an insecure dev fallback is allowed so local/test runs
    still work.
    """
    secret = os.environ.get('JWT_SECRET_KEY') or os.environ.get('FLASK_SECRET_KEY')
    if secret:
        return secret

    flask_env = os.environ.get('FLASK_ENV', 'development').lower()
    database_url = os.environ.get('DATABASE_URL', '')
    is_production = flask_env == 'production' or (
        bool(database_url)
        and 'localhost' not in database_url
        and '127.0.0.1' not in database_url
    )
    if is_production:
        raise RuntimeError(
            'JWT secret is not configured: set JWT_SECRET_KEY (or FLASK_SECRET_KEY). '
            'Refusing to start with an insecure default JWT secret in production.'
        )

    import logging
    logging.getLogger('jarvis.mobile').warning(
        'No JWT_SECRET_KEY/FLASK_SECRET_KEY set — using an INSECURE dev JWT secret. '
        'Set JWT_SECRET_KEY before deploying.'
    )
    return 'dev-jwt-secret'


_JWT_SECRET = _resolve_jwt_secret()
_JWT_ACCESS_TTL = 3600       # 1 hour
_JWT_REFRESH_TTL = 2592000   # 30 days

# Revoked refresh tokens (in-memory; use Redis in production for multi-worker)
_revoked_tokens: set[str] = set()


# ============== JWT Helpers ==============

def _b64url_encode(data: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def _b64url_decode(s: str) -> bytes:
    import base64
    s += '=' * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s)


def _create_token(payload: dict, secret: str) -> str:
    header = _b64url_encode(json.dumps({'alg': 'HS256', 'typ': 'JWT'}).encode())
    body = _b64url_encode(json.dumps(payload).encode())
    sig = hmac.new(secret.encode(), f'{header}.{body}'.encode(), hashlib.sha256).digest()
    return f'{header}.{body}.{_b64url_encode(sig)}'


def _decode_token(token: str, secret: str) -> dict | None:
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        header, body, sig = parts
        expected_sig = hmac.new(secret.encode(), f'{header}.{body}'.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url_decode(sig), expected_sig):
            return None
        payload = json.loads(_b64url_decode(body))
        if payload.get('exp', 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def _generate_tokens(user_id: int) -> dict:
    now = int(time.time())
    access_payload = {'sub': user_id, 'iat': now, 'exp': now + _JWT_ACCESS_TTL, 'type': 'access'}
    refresh_payload = {'sub': user_id, 'iat': now, 'exp': now + _JWT_REFRESH_TTL, 'type': 'refresh', 'jti': os.urandom(16).hex()}
    return {
        'access_token': _create_token(access_payload, _JWT_SECRET),
        'refresh_token': _create_token(refresh_payload, _JWT_SECRET),
        'expires_in': _JWT_ACCESS_TTL,
    }


def jwt_required(f):
    """Decorator: require valid JWT access token in Authorization header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return jsonify({'error': 'Missing authorization token'}), 401
        token = auth[7:]
        payload = _decode_token(token, _JWT_SECRET)
        if not payload:
            return jsonify({'error': 'Invalid or expired token'}), 401
        if payload.get('type') != 'access':
            return jsonify({'error': 'Invalid token type'}), 401
        user_data = _user_repo.get_by_id(payload['sub'])
        if not user_data or not user_data.get('is_active', True):
            return jsonify({'error': 'User not found or inactive'}), 401
        request._jwt_user = User(user_data)
        request._jwt_user_data = user_data
        return f(*args, **kwargs)
    return decorated


def _current_mobile_user():
    return getattr(request, '_jwt_user', None)


def _user_json(user) -> dict:
    """Serialize user for mobile API response."""
    from core.roles.repositories.permission_repository import PermissionRepository as _PermRepo
    _perm_repo = _PermRepo()
    mod_access = _perm_repo.get_module_access_map(user.role_id) if user.role_id else {}
    mob_access = _perm_repo.get_mobile_access_map(user.role_id) if user.role_id else {}

    def _mod(module_key, fallback_attr=None):
        if module_key in mod_access:
            return mod_access[module_key]
        if fallback_attr:
            return bool(getattr(user, fallback_attr, False))
        return False

    def _mobile(module_key):
        return mob_access.get(module_key, True)

    return {
        'id': user.id,
        'name': user.name,
        'email': user.email,
        'phone': user.phone,
        'company': user.company,
        'company_id': getattr(user, 'company_id', None),
        'brand': getattr(user, 'brand', None),
        'department': user.department,
        'subdepartment': getattr(user, 'subdepartment', None),
        'position': getattr(user, 'position', None),
        'role_name': user.role_name,
        'role_id': user.role_id,
        'contract_work_date': getattr(user, 'contract_work_date', None),
        'cnp': getattr(user, 'cnp', None),
        'birthdate': getattr(user, 'birthdate', None),
        # Flat permission flags (no wrapper — extractPermissions reads top-level)
        'is_hr_manager': bool(getattr(user, 'is_hr_manager', False)),
        'is_superuser': bool(getattr(user, 'is_superuser', False)),
        'can_access_marketing':  _mod('marketing',  'can_access_marketing'),
        'can_access_hr':         _mod('hr',         'can_access_hr'),
        'can_access_approvals':  _mod('approvals',  'can_access_approvals'),
        'can_access_forms':      _mod('forms',      'can_access_forms'),
        'can_access_ai_agent':   _mod('ai_agent',   'can_access_ai_agent'),
        'can_access_digest':     _mod('digest',     'can_access_digest'),
        'can_access_accounting': _mod('accounting', 'can_access_accounting'),
        'can_access_field_sales': _mod('field_sales', None),
        'can_access_vouchers':    _mod('vouchers', None),
        'can_access_facturare':   _mod('facturare', None),
        'can_access_controlling': _mod('controlling', None),
        'can_access_test_drive':  _mod('test_drive', None),
        # Mobile-specific toggles
        'can_access_approvals_mobile':    _mobile('approvals'),
        'can_access_forms_mobile':        _mobile('forms'),
        'can_access_ai_agent_mobile':     _mobile('ai_agent'),
        'can_access_marketing_mobile':    _mobile('marketing'),
        'can_access_hr_mobile':           _mobile('hr'),
        'can_access_digest_mobile':       _mobile('digest'),
        'can_access_accounting_mobile':   _mobile('accounting'),
        'can_access_field_sales_mobile':  _mobile('field_sales'),
        # Field sales granular flags for mobile
        'can_view_field_sales_team': bool(
            _perm_repo.check_permission_v2(user.role_id, 'field_sales', 'team', 'view').get('has_permission')
        ) if user.role_id else False,
    }


# ============== APP VERSION CONSTANTS ==============

# Bump this on each release to trigger update prompts
_CURRENT_VERSION = '1.2.0'
_CURRENT_VERSION_CODE = 3
_DOWNLOAD_URL = 'https://jarvis.autoworld.ro/download/jarvis.apk'
