"""Shared imports and singletons for voucher routes."""
import logging
from flask import jsonify, request, send_file
from flask_login import login_required, current_user

from accounting.vouchers import vouchers_bp
from accounting.vouchers.repositories import VoucherRepository, VoucherAttemptRepository
from accounting.vouchers.services import VoucherService
from accounting.vouchers.schemas import VoucherCreate, VoucherRead, VoucherListItem, VoucherRedeem
from core.utils.api_helpers import error_response, handle_api_errors
from core.roles.repositories.permission_repository import PermissionRepository

__all__ = [
    'logging', 'jsonify', 'request', 'send_file', 'login_required', 'current_user',
    'vouchers_bp',
    'VoucherRepository', 'VoucherService',
    'VoucherCreate', 'VoucherRead', 'VoucherListItem', 'VoucherRedeem',
    'error_response', 'handle_api_errors', 'PermissionRepository',
    'logger', '_repo', '_service', '_perm_repo', '_attempt_repo',
    '_check_accounting_role', '_check_redeem_perm', '_check_voucher_perm',
    '_check_redeem_rate_limit', '_record_redeem_attempt', '_get_client_ip',
    '_is_voucher_admin', '_voucher_company_ok',
]

logger = logging.getLogger('jarvis.vouchers.routes')
_repo = VoucherRepository()
_service = VoucherService()
_perm_repo = PermissionRepository()
_attempt_repo = VoucherAttemptRepository()

# Redeem/lookup rate-limit budgets (sliding windows). Only FAILED attempts
# count, so a normal single successful redemption never trips these.
_RL_IP_MAX, _RL_IP_WINDOW = 10, 600       # 10 failed / 10 min per IP
_RL_USER_MAX, _RL_USER_WINDOW = 20, 600   # 20 failed / 10 min per user
_RL_CODE_MAX, _RL_CODE_WINDOW = 5, 3600   # 5 failed / 60 min per voucher code


def _check_voucher_perm(entity: str, action: str) -> bool:
    """Check vouchers.{entity}.{action} V2 permission."""
    if getattr(current_user, 'role_name', '').lower() in ('admin', 'superadmin'):
        return True
    role_id = getattr(current_user, 'role_id', None)
    if not role_id:
        return False
    perm = _perm_repo.check_permission_v2(role_id, 'vouchers', entity, action)
    return perm.get('has_permission', False)


def _check_accounting_role() -> bool:
    """Check if current user has accounting voucher access (read)."""
    return _check_voucher_perm('accounting', 'view')


def _check_redeem_perm() -> bool:
    """Check the dedicated redeem write-permission (vouchers.accounting.redeem).

    Redemption is a state-changing action, so it is gated on the redeem perm
    rather than the read 'view' perm — and this matches the key the frontend
    redeem button checks.
    """
    return _check_voucher_perm('accounting', 'redeem')


def _is_voucher_admin() -> bool:
    """Admins/superadmins may act across companies (no tenant restriction)."""
    return getattr(current_user, 'role_name', '').lower() in ('admin', 'superadmin')


def _voucher_company_ok(voucher) -> bool:
    """True if the current user may access this voucher's tenant.

    Admins are cross-company; everyone else is confined to their own
    ``company_id``. Callers that fail this should 404 (not 403) so a voucher's
    existence is never disclosed across tenants. ``voucher`` is a row dict (or
    None → treated as not-ok).
    """
    if not voucher:
        return False
    if _is_voucher_admin():
        return True
    return voucher.get('company_id') == getattr(current_user, 'company_id', None)


def _get_client_ip() -> str:
    """Client IP for rate-limiting.

    Use the RIGHT-most ``X-Forwarded-For`` entry — the hop appended by our own
    reverse proxy — never the left-most, which is client-supplied and trivially
    spoofable (an attacker could rotate it to dodge the per-IP budget). Falls
    back to the socket peer. Assumes a single trusted proxy in front of the app
    (DigitalOcean); if a CDN adds another hop, raise the trusted-hop count. The
    unspoofable controls (per authenticated user, per voucher code) are the
    primary defense; the per-IP budget is a supplementary backstop.
    """
    xff = request.headers.get('X-Forwarded-For', '')
    hops = [h.strip() for h in xff.split(',') if h.strip()]
    if hops:
        return hops[-1]
    return request.remote_addr or '0.0.0.0'


def _rate_limited_response(retry_after: int):
    """Build a 429 response with a Retry-After header (seconds)."""
    resp = jsonify({
        'success': False,
        'error': 'Prea multe încercări. Încercați din nou mai târziu.',
        'retry_after': retry_after,
    })
    resp.status_code = 429
    resp.headers['Retry-After'] = str(retry_after)
    return resp


def _check_redeem_rate_limit(code):
    """Throttle code-based voucher lookup/redeem (brute-force / enumeration).

    Returns a 429 response if the client IP, the current user, or this voucher
    code has exceeded its failed-attempt budget in the window; otherwise None.
    Fails OPEN on any error so a limiter glitch never blocks a legitimate
    redemption.
    """
    try:
        uid = current_user.id if getattr(current_user, 'is_authenticated', False) else None
        code = (code or '').strip().upper()[:32]

        # Per-IP budget is the ANONYMOUS backstop only. For authenticated callers
        # the unspoofable per-user budget governs instead — this avoids locking
        # out several legitimate staff who share one office IP (NAT).
        if uid is None:
            ip = _get_client_ip()
            if ip and _attempt_repo.count_recent(ip=ip, window_seconds=_RL_IP_WINDOW) >= _RL_IP_MAX:
                return _rate_limited_response(_RL_IP_WINDOW)
        elif _attempt_repo.count_recent(user_id=uid, window_seconds=_RL_USER_WINDOW) >= _RL_USER_MAX:
            return _rate_limited_response(_RL_USER_WINDOW)
        # Per-code budget applies to everyone (IP-independent): caps hammering a
        # single voucher regardless of who/where.
        if code and _attempt_repo.count_recent(voucher_code=code, window_seconds=_RL_CODE_WINDOW) >= _RL_CODE_MAX:
            return _rate_limited_response(_RL_CODE_WINDOW)
        return None
    except Exception:
        logger.exception('Voucher rate-limit check failed — allowing (fail-open)')
        return None


def _record_redeem_attempt(code, outcome):
    """Best-effort log of a code attempt for rate limiting; never raises."""
    try:
        ip = _get_client_ip()
        uid = current_user.id if getattr(current_user, 'is_authenticated', False) else None
        _attempt_repo.record(ip, uid, (code or '').strip().upper()[:32], outcome)
    except Exception:
        logger.exception('Voucher attempt logging failed (ignored)')
