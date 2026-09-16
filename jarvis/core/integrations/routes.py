"""JARVIS alpha | BUSINESS CONTROL — first-party authorization contract.

    GET /api/integrations/business-control/authorize

JARVIS is the single source of truth for identity and authorization. This
endpoint lets the separate JARVIS alpha application authorize an already
authenticated JARVIS principal — a browser **session cookie** or an existing
**Bearer access token** (the mobile JWT, transparently accepted via the global
``_jwt_session_bridge`` in ``app.py``). No new credential or password path is
introduced: JARVIS alpha obtains a short-lived token from the existing
``POST /api/auth/token`` endpoint (which reuses ``werkzeug.check_password_hash``
via ``UserRepository.authenticate_identifier``), then calls this endpoint.

Authorization is decided by JARVIS's existing ``permissions_v2`` model through
the public permission ``business_control.access`` (stored as the
``business_control`` / ``module`` / ``access`` triple). The rule mirrors
``core.roles.decorators.v2_permission_required`` exactly, so JARVIS's documented
admin behavior is preserved: an admin (``can_access_settings``) is all-access;
every other role needs an explicit, non-deny grant. No role name is hard-coded
as the authorization contract — the permission is the contract.

Responses use JARVIS's standard envelope:
- 200 -> the authorization result (see ``_authorized_payload``)
- 403 -> ``{"success": false, "error": "Permission denied"}`` (authenticated but
         not permitted, or an inactive/disabled account)
- 401 -> ``{"success": false, "error": "Authentication required"}``
"""
import logging

from flask import jsonify, request
from flask_login import current_user

from core.integrations import integrations_bp
from core.utils.api_helpers import error_response, RateLimiter
from core.roles.repositories import PermissionRepository

logger = logging.getLogger('jarvis.integrations')

# Public, stable permission identifier returned in the contract and documented
# for JARVIS alpha. Internally it maps to the permissions_v2 triple below — the
# established "<module>.module.access" module-access convention.
BUSINESS_CONTROL_PERMISSION = 'business_control.access'
_BC_MODULE = 'business_control'
_BC_ENTITY = 'module'
_BC_ACTION = 'access'

# Defense-in-depth throttle. JARVIS alpha is expected to call this once per login
# and then mint its own session cookie, so the ceiling is generous. Credential
# issuance itself is already rate-limited upstream on /api/auth/token.
_rate_limiter = RateLimiter()
_RATE_MAX_REQUESTS = 120
_RATE_WINDOW_SECONDS = 60


def _has_business_control_access(user) -> bool:
    """Authorization rule, reusing the existing permissions_v2 model.

    Mirrors ``v2_permission_required`` semantics precisely:
    - JARVIS admins (``can_access_settings``) are authorized — this is JARVIS's
      documented, app-wide behavior (the explicit superadmin decision), not a
      role name hard-coded in JARVIS alpha.
    - Everyone else needs an explicit, non-deny ``business_control.access`` grant
      on their role, assignable through the normal Settings -> Roles workflow.
    """
    if getattr(user, 'is_admin', False) or getattr(user, 'can_access_settings', False):
        return True
    role_id = getattr(user, 'role_id', None)
    if not role_id:
        return False
    perm = PermissionRepository().check_permission_v2(role_id, _BC_MODULE, _BC_ENTITY, _BC_ACTION)
    return bool(perm.get('has_permission'))


def _audit(event_type: str, user, description: str, authorized: bool) -> None:
    """Best-effort audit trail to ``user_events``. Never breaks the response."""
    try:
        from core.auth.repositories.event_repository import EventRepository
        EventRepository().log_event(
            event_type=event_type,
            event_description=description,
            user_id=getattr(user, 'id', None),
            user_email=getattr(user, 'email', None),
            entity_type='integration',
            ip_address=request.headers.get('X-Forwarded-For', request.remote_addr),
            user_agent=request.headers.get('User-Agent'),
            details={'integration': 'business_control', 'authorized': authorized},
        )
    except Exception:  # pragma: no cover - audit must not affect the contract
        logger.exception('business_control authorize: audit logging failed (non-fatal)')


def _authorized_payload(user):
    """The exact 200 contract. Only whitelisted, non-sensitive fields are echoed.

    JARVIS has no separate tenant tier — the company is the isolation boundary —
    so ``tenant_id`` is always null and JARVIS alpha isolates data by
    ``company_id``.
    """
    return {
        'authorized': True,
        'user': {
            'id': user.id,
            'email': user.email,
            'full_name': getattr(user, 'name', None),
        },
        'scope': {
            'tenant_id': None,
            'company_id': getattr(user, 'company_id', None),
            'company': getattr(user, 'company', None),
        },
        'permission': BUSINESS_CONTROL_PERMISSION,
    }


@integrations_bp.route('/api/integrations/business-control/authorize', methods=['GET'])
def business_control_authorize():
    # 1) Authentication — session cookie OR Bearer token (via _jwt_session_bridge).
    if not current_user.is_authenticated:
        return error_response('Authentication required', 401)

    # 2) Throttle (per authenticated principal).
    allowed, retry_after = _rate_limiter.is_allowed(
        f'bc_authorize:{current_user.id}',
        max_requests=_RATE_MAX_REQUESTS,
        window_seconds=_RATE_WINDOW_SECONDS,
    )
    if not allowed:
        resp, code = error_response('Too many requests', 429)
        resp.headers['Retry-After'] = str(retry_after)
        return resp, code

    # 3) Active account. Runs BEFORE authorization so a disabled admin is still
    #    denied. The login and JWT-bridge paths refuse inactive users up front,
    #    but a session cookie is not re-checked per request — so a user disabled
    #    AFTER their cookie was issued is caught here.
    if not getattr(current_user, 'is_active', False):
        _audit('business_control.authorize_denied', current_user, 'inactive account', False)
        return error_response('Permission denied', 403)

    # 4) Authorization through the existing permissions_v2 model.
    if not _has_business_control_access(current_user):
        _audit('business_control.authorize_denied', current_user,
               'missing business_control.access', False)
        return error_response('Permission denied', 403)

    _audit('business_control.authorize', current_user, 'authorized', True)
    return jsonify(_authorized_payload(current_user))
