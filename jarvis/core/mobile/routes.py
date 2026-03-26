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

_user_repo = UserRepository()


@mobile_bp.after_request
def _add_cors(response):
    """Allow cross-origin requests from mobile app."""
    origin = request.headers.get('Origin', '')
    # Allow capacitor:// (native app) and localhost dev
    if origin.startswith(('capacitor://', 'http://localhost', 'https://localhost', 'http://127.0.0.1')):
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Max-Age'] = '86400'
    return response


@mobile_bp.route('/api/auth/token', methods=['OPTIONS'])
@mobile_bp.route('/api/auth/refresh', methods=['OPTIONS'])
@mobile_bp.route('/api/auth/logout', methods=['OPTIONS'])
@mobile_bp.route('/api/auth/current-user', methods=['OPTIONS'])
@mobile_bp.route('/api/mobile/dashboard', methods=['OPTIONS'])
@mobile_bp.route('/api/mobile/widget-data', methods=['OPTIONS'])
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
    }


# ============== AUTH ENDPOINTS ==============

@mobile_bp.route('/api/auth/token', methods=['POST'])
def api_token():
    """JWT login — returns access + refresh tokens."""
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
    from database import get_db_connection
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    push_token = data.get('push_token') or ''
    platform = data.get('platform', 'unknown')  # ios | android
    device_id = data.get('device_id') or ''

    if not push_token:
        return jsonify({'error': 'push_token is required'}), 400

    user = _current_mobile_user()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO mobile_devices (user_id, push_token, platform, device_id, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (push_token) DO UPDATE
                SET user_id = EXCLUDED.user_id, platform = EXCLUDED.platform,
                    device_id = EXCLUDED.device_id, updated_at = NOW()
            """, (user.id, push_token, platform, device_id))
        conn.commit()

    return jsonify({'success': True})


@mobile_bp.route('/api/devices/unregister', methods=['POST'])
@jwt_required
def api_unregister_device():
    """Unregister device push token."""
    from database import get_db_connection
    data = request.get_json() or {}
    push_token = data.get('push_token')
    if not push_token:
        return jsonify({'error': 'push_token required'}), 400

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM mobile_devices WHERE push_token = %s AND user_id = %s",
                        (push_token, _current_mobile_user().id))
        conn.commit()

    return jsonify({'success': True})


# ============== MOBILE DASHBOARD ==============

@mobile_bp.route('/api/mobile/dashboard')
@jwt_required
def api_mobile_dashboard():
    """Aggregated dashboard data for mobile home screen — single request."""
    import logging
    logger = logging.getLogger(__name__)
    from database import get_db_connection
    user = _current_mobile_user()
    result = {'stats': {'invoices': 0, 'revenue': 0, 'pending_invoices': 0,
                        'pending_approvals': 0, 'pending_signatures': 0, 'clients': 0},
              'recent_invoices': [], 'recent_clients': [], 'upcoming_events': []}

    def _safe_query(conn, sql, params=None):
        """Run a query with savepoint so failures don't poison the transaction."""
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall(), [d[0] for d in cur.description] if cur.description else []
        except Exception as e:
            conn.rollback()
            logger.warning('Dashboard query failed: %s — %s', sql[:80], e)
            return [], []

    with get_db_connection() as conn:
        try:
            # Stat cards — invoices
            rows, _ = _safe_query(conn, """
                SELECT COUNT(*), COALESCE(SUM(invoice_value), 0),
                       COUNT(*) FILTER (WHERE status = 'pending')
                FROM invoices WHERE deleted_at IS NULL
            """)
            if rows:
                result['stats']['invoices'] = rows[0][0]
                result['stats']['revenue'] = float(rows[0][1])
                result['stats']['pending_invoices'] = rows[0][2]

            # Pending approvals
            rows, _ = _safe_query(conn, """
                SELECT COUNT(*) FROM approval_decisions ad
                JOIN approval_requests ar ON ar.id = ad.request_id
                WHERE ad.decided_by = %s AND ad.decision = 'pending' AND ar.status = 'pending'
            """, (user.id,))
            if rows:
                result['stats']['pending_approvals'] = rows[0][0]

            # Pending signatures
            rows, _ = _safe_query(conn, """
                SELECT COUNT(*) FROM document_signatures
                WHERE signed_by = %s AND status = 'pending'
            """, (user.id,))
            if rows:
                result['stats']['pending_signatures'] = rows[0][0]

            # Client count
            rows, _ = _safe_query(conn, "SELECT COUNT(*) FROM crm_clients WHERE is_blacklisted = false")
            if rows:
                result['stats']['clients'] = rows[0][0]

            # Recent invoices (last 5)
            rows, cols = _safe_query(conn, """
                SELECT id, invoice_number, supplier, invoice_value as amount,
                       currency, invoice_date as date, status
                FROM invoices WHERE deleted_at IS NULL
                ORDER BY created_at DESC LIMIT 5
            """)
            result['recent_invoices'] = [dict(zip(cols, r)) for r in rows]
            for inv in result['recent_invoices']:
                if inv.get('date'):
                    inv['date'] = str(inv['date'])
                if inv.get('amount'):
                    inv['amount'] = float(inv['amount'])

            # Recent clients (last 5)
            rows, cols = _safe_query(conn, """
                SELECT id, display_name as name, company_name as cui,
                       '' as contact_person, phone, email, city, client_type as status
                FROM crm_clients WHERE is_blacklisted = false
                ORDER BY created_at DESC LIMIT 5
            """)
            result['recent_clients'] = [dict(zip(cols, r)) for r in rows]

            # Upcoming events — check table exists first
            rows, _ = _safe_query(conn, """
                SELECT EXISTS (SELECT 1 FROM information_schema.tables
                               WHERE table_schema = 'public' AND table_name = 'hr_events')
            """)
            if rows and rows[0][0]:
                rows, cols = _safe_query(conn, """
                    SELECT he.id, he.title, he.event_date as date, he.end_date,
                           he.location, he.event_type as type, he.status,
                           (SELECT COUNT(*) FROM hr_event_participants WHERE event_id = he.id) as participants_count
                    FROM hr_events he WHERE he.event_date >= CURRENT_DATE
                    ORDER BY he.event_date ASC LIMIT 3
                """)
                result['upcoming_events'] = [dict(zip(cols, r)) for r in rows]
                for ev in result['upcoming_events']:
                    if ev.get('date'):
                        ev['date'] = str(ev['date'])
                    if ev.get('end_date'):
                        ev['end_date'] = str(ev['end_date'])

            return jsonify(result)
        except Exception as e:
            logger.error('Dashboard endpoint error: %s', e)
            return jsonify({'error': 'An internal error occurred', 'success': False}), 500


# ============== WIDGET DATA (lightweight) ==============

@mobile_bp.route('/api/mobile/widget-data')
@jwt_required
def api_widget_data():
    """Minimal data payload for home screen widgets."""
    from database import get_db_connection
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

    pending_count = 0
    next_event = None
    next_event_date = None

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("""
                    SELECT COUNT(*) FROM approval_step_decisions asd
                    JOIN approval_request_steps ars ON ars.id = asd.step_id
                    JOIN approval_requests ar ON ar.id = ars.request_id
                    WHERE asd.approver_id = %s AND asd.decision = 'pending' AND ar.status = 'pending'
                """, (user.id,))
                row = cur.fetchone()
                pending_count = row[0] if row else 0
            except Exception:
                conn.rollback()

            try:
                cur.execute("""
                    SELECT title, event_date FROM hr_events
                    WHERE event_date >= CURRENT_DATE
                    ORDER BY event_date ASC LIMIT 1
                """)
                ev = cur.fetchone()
                if ev:
                    next_event = ev[0]
                    next_event_date = str(ev[1])
            except Exception:
                conn.rollback()

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
    from database import get_db_connection
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    nfc_tag_id = data.get('nfc_tag_id') or ''
    if not nfc_tag_id:
        return jsonify({'error': 'nfc_tag_id is required'}), 400

    user = _current_mobile_user()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Look up NFC tag → location_id
            cur.execute("""
                SELECT nt.location_id, cl.name FROM checkin_nfc_tags nt
                JOIN checkin_locations cl ON cl.id = nt.location_id
                WHERE nt.tag_id = %s AND cl.is_active = true
            """, (nfc_tag_id,))
            tag = cur.fetchone()
            if not tag:
                return jsonify({'error': 'Unknown NFC tag'}), 404

    # Reuse existing punch logic via QR token format "checkin:<location_id>"
    from core.checkin.service import CheckinService
    svc = CheckinService()
    qr_token = f'checkin:{tag[0]}'
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
    from database import get_db_connection
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT nt.id, nt.tag_id, cl.id as location_id, cl.name as location_name
                FROM checkin_nfc_tags nt
                JOIN checkin_locations cl ON cl.id = nt.location_id
                WHERE cl.is_active = true
                ORDER BY cl.name
            """)
            cols = [d[0] for d in cur.description]
            tags = [dict(zip(cols, r)) for r in cur.fetchall()]
            return jsonify({'success': True, 'tags': tags})


# ============== MOBILE SIGNATURE ==============

@mobile_bp.route('/api/signatures/sign-mobile', methods=['POST'])
@jwt_required
def api_sign_mobile():
    """Sign a document from mobile — accepts base64 signature image."""
    from database import get_db_connection
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    signature_id = data.get('signature_id')
    signature_image = data.get('signature_image')  # base64

    if not signature_id or not signature_image:
        return jsonify({'error': 'signature_id and signature_image are required'}), 400

    user = _current_mobile_user()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Verify ownership
            cur.execute("""
                SELECT id, status FROM document_signatures
                WHERE id = %s AND signed_by = %s
            """, (signature_id, user.id))
            sig = cur.fetchone()
            if not sig:
                return jsonify({'error': 'Signature request not found'}), 404
            if sig[1] != 'pending':
                return jsonify({'error': f'Signature already {sig[1]}'}), 400

            # Save signature
            cur.execute("""
                UPDATE document_signatures
                SET status = 'signed', signature_image = %s, signed_at = NOW()
                WHERE id = %s
            """, (signature_image, signature_id))
            conn.commit()

            return jsonify({'success': True, 'message': 'Document signed successfully'})
