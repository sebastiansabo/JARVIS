"""Mobile API routes — JWT auth, dashboard, NFC, device registration."""
import os
import time
import hmac
import hashlib
import json
import threading
from functools import wraps
from datetime import datetime, timedelta, timezone

from flask import jsonify, request

from . import mobile_bp
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
@mobile_bp.route('/api/auth/refresh', methods=['OPTIONS'])
@mobile_bp.route('/api/auth/logout', methods=['OPTIONS'])
@mobile_bp.route('/api/auth/current-user', methods=['OPTIONS'])
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
_JWT_SECRET = os.environ.get('JWT_SECRET_KEY', os.environ.get('FLASK_SECRET_KEY', 'dev-jwt-secret'))
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
        'can_access_marketing':  _mod('marketing',  'can_access_marketing'),
        'can_access_hr':         _mod('hr',         'can_access_hr'),
        'can_access_approvals':  _mod('approvals',  'can_access_approvals'),
        'can_access_forms':      _mod('forms',      'can_access_forms'),
        'can_access_ai_agent':   _mod('ai_agent',   'can_access_ai_agent'),
        'can_access_digest':     _mod('digest',     'can_access_digest'),
        'can_access_accounting': _mod('accounting', 'can_access_accounting'),
        'can_access_field_sales': _mod('field_sales', None),
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


# ============== MOBILE DASHBOARD ==============

@mobile_bp.route('/api/mobile/dashboard')
@jwt_required
def api_mobile_dashboard():
    """Aggregated dashboard data for mobile home screen — single request."""
    import logging
    logger = logging.getLogger(__name__)
    user = _current_mobile_user()

    try:
        invoices, revenue, pending_invoices = _dashboard_repo.get_invoice_stats()
        result = {
            'stats': {
                'invoices': invoices,
                'revenue': revenue,
                'pending_invoices': pending_invoices,
                'pending_approvals': _dashboard_repo.get_pending_approvals_count(user.id),
                'pending_signatures': _dashboard_repo.get_pending_signatures_count(user.id),
                'clients': _dashboard_repo.get_client_count(),
            },
            'recent_invoices': [],
            'recent_clients': [],
            'upcoming_events': [],
        }

        recent_invoices = _dashboard_repo.get_recent_invoices()
        for inv in recent_invoices:
            if inv.get('date'):
                inv['date'] = str(inv['date'])
            if inv.get('amount'):
                inv['amount'] = float(inv['amount'])
        result['recent_invoices'] = recent_invoices

        result['recent_clients'] = _dashboard_repo.get_recent_clients()

        upcoming = _dashboard_repo.get_upcoming_events()
        for ev in upcoming:
            if ev.get('date'):
                ev['date'] = str(ev['date'])
            if ev.get('end_date'):
                ev['end_date'] = str(ev['end_date'])
        result['upcoming_events'] = upcoming

        return jsonify(result)
    except Exception as e:
        logger.error('Dashboard endpoint error: %s', e)
        return jsonify({'error': 'An internal error occurred', 'success': False}), 500


# ============== WIDGET DATA (lightweight) ==============

@mobile_bp.route('/api/mobile/widget-data')
@jwt_required
def api_widget_data():
    """Minimal data payload for home screen widgets."""
    from core.checkin.service import CheckinService
    user = _current_mobile_user()

    # Check-in status via existing service
    checkin_svc = CheckinService()
    status = checkin_svc.get_status(user.id)
    punches = status.get('punches', [])
    checked_in = False
    last_punch_time = None
    if punches:
        last = punches[-1]
        checked_in = last.get('direction') == 'IN'
        last_punch_time = last.get('event_datetime')

    pending_count = _dashboard_repo.get_pending_approvals_widget(user.id)
    next_event, next_event_date = _dashboard_repo.get_next_event()

    return jsonify({
        'checked_in': checked_in,
        'last_punch_time': last_punch_time,
        'pending_approvals': pending_count,
        'next_event': next_event,
        'next_event_date': next_event_date,
    })


# ============== NFC CHECK-IN ==============

@mobile_bp.route('/api/checkin/nfc-punch', methods=['POST'])
@jwt_required
def api_nfc_punch():
    """Check in/out via NFC tag — reuses existing CheckinService with QR token format."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    nfc_tag_id = data.get('nfc_tag_id') or ''
    if not nfc_tag_id:
        return jsonify({'error': 'nfc_tag_id is required'}), 400

    user = _current_mobile_user()
    tag = _checkin_repo.get_nfc_tag_by_tag_id(nfc_tag_id)
    if not tag:
        return jsonify({'error': 'Unknown NFC tag'}), 404

    location_id = tag['location_id'] if isinstance(tag, dict) else tag[0]

    # Reuse existing punch logic via QR token format "checkin:<location_id>"
    from core.checkin.service import CheckinService
    svc = CheckinService()
    qr_token = f'checkin:{location_id}'
    result = svc.punch(
        jarvis_user_id=user.id,
        qr_token=qr_token,
        direction=data.get('direction'),
    )
    return jsonify(result), 200 if result['success'] else 400


@mobile_bp.route('/api/checkin/nfc-tags')
@jwt_required
def api_nfc_tags():
    """List registered NFC tag-location mappings."""
    tags = _checkin_repo.get_all_nfc_tags()
    return jsonify({'success': True, 'tags': tags})


# ============== MOBILE SIGNATURE ==============

@mobile_bp.route('/api/signatures/sign-mobile', methods=['POST'])
@jwt_required
def api_sign_mobile():
    """Sign a document from mobile — accepts base64 signature image."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    signature_id = data.get('signature_id')
    signature_image = data.get('signature_image')  # base64

    if not signature_id or not signature_image:
        return jsonify({'error': 'signature_id and signature_image are required'}), 400

    user = _current_mobile_user()
    sig = _sig_repo.get_for_user_verification(signature_id, user.id)
    if not sig:
        return jsonify({'error': 'Signature request not found'}), 404
    status = sig['status'] if isinstance(sig, dict) else sig[1]
    if status != 'pending':
        return jsonify({'error': f'Signature already {status}'}), 400

    _sig_repo.sign_mobile(signature_id, signature_image)
    return jsonify({'success': True, 'message': 'Document signed successfully'})


# ============== APP VERSION CHECK ==============

# Bump this on each release to trigger update prompts
_CURRENT_VERSION = '1.2.0'
_CURRENT_VERSION_CODE = 3
_DOWNLOAD_URL = 'https://jarvis.autoworld.ro/download/jarvis.apk'


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
