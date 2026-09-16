"""JARVIS alpha | BUSINESS CONTROL — first-party authorization contract (multi-tenant).

    GET  /api/integrations/business-control/authorize                 -> authz + tenants
    POST /api/integrations/business-control/authorize   {company_id}  -> select one tenant
    GET  /api/integrations/business-control/admin/users/<id>/access   -> admin read-only

JARVIS is the single source of truth for identity and authorization. These
endpoints let the separate JARVIS alpha application authorize an already
authenticated JARVIS principal — a browser **session cookie** or an existing
**Bearer access token** (the mobile JWT, transparently accepted via the global
``_jwt_session_bridge`` in ``app.py``; OTP/2FA is handled upstream when that token
is minted at ``POST /api/auth/token``). No new credential or password path.

Authorization gate: the existing ``permissions_v2`` permission
``business_control.access`` (role grant or admin bypass) — never a hard-coded role
name. The role name is returned only for display.

Tenant model — uses the existing JARVIS **company structure** (the ``companies``
table); no parallel membership store:
- **admin** (``can_access_settings``)   -> ALL active companies
- **non-admin** (has the permission)    -> ONLY their registered company (``users.company_id``), if active

Standard envelope ``{success, ...}``:
- 200 -> authorization result (GET: available tenants; POST: the selected scope)
- 403 -> denied (GET: ``{"success": false, "error": "Permission denied"}``;
         POST: ``{"success": false, "authorized": false, "error": "Tenant access denied"}``)
- 401 -> ``{"success": false, "error": "Authentication required"}``
"""
import re
import logging

from flask import jsonify, request
from flask_login import current_user

from core.integrations import integrations_bp
from core.utils.api_helpers import error_response, RateLimiter, admin_required
from core.roles.repositories import PermissionRepository
from core.integrations.repository import IntegrationsRepository
from core.auth.repositories import UserRepository

logger = logging.getLogger('jarvis.integrations')

# Public, stable permission identifier. Internally the permissions_v2 triple below.
BUSINESS_CONTROL_PERMISSION = 'business_control.access'
_BC_MODULE = 'business_control'
_BC_ENTITY = 'module'
_BC_ACTION = 'access'

# Defense-in-depth throttle (per authenticated principal). Alpha calls these once
# per login then mints its own cookie; credential issuance is rate-limited upstream.
_rate_limiter = RateLimiter()
_RATE_MAX_REQUESTS = 120
_RATE_WINDOW_SECONDS = 60

# Romanian legal forms stripped when deriving a display company_code from the name.
_LEGAL_FORM_RE = re.compile(
    r'\b(S\.?\s?C\.?|S\.?\s?R\.?\s?L\.?(?:\s?-?\s?D)?|S\.?\s?A\.?|P\.?\s?F\.?\s?A\.?|S\.?\s?N\.?\s?C\.?|S\.?\s?C\.?\s?S\.?)\b',
    re.IGNORECASE,
)


# ── Authorization helpers (reuse the existing permission model) ────────────────

def _is_admin(user) -> bool:
    return bool(getattr(user, 'is_admin', False) or getattr(user, 'can_access_settings', False))


def _role_has_bc_access(role_id, is_admin: bool) -> bool:
    """Mirror ``v2_permission_required``: admins are all-access (documented JARVIS
    behavior); everyone else needs an explicit, non-deny ``business_control.access``
    grant on their role."""
    if is_admin:
        return True
    if not role_id:
        return False
    perm = PermissionRepository().check_permission_v2(role_id, _BC_MODULE, _BC_ENTITY, _BC_ACTION)
    return bool(perm.get('has_permission'))


def _has_business_control_access(user) -> bool:
    return _role_has_bc_access(getattr(user, 'role_id', None), _is_admin(user))


def _company_code(name: str):
    """Derive a stable, display-only code from the company name (no code column
    exists). E.g. 'Autoworld SRL' -> 'AUTOWORLD'."""
    if not name:
        return None
    base = _LEGAL_FORM_RE.sub(' ', name)
    slug = re.sub(r'[^A-Za-z0-9]+', '_', base).strip('_').upper()
    return slug or None


def _eligible_companies(user):
    """Companies this user may access in BUSINESS CONTROL, from the company structure.

    Returns ``(tenants, default_company_id, default_company_name)`` where tenants is
    a list of ``{company_id, company_name, company_code, is_default}``. Empty list
    when the user has no eligible active company.
    """
    repo = IntegrationsRepository()
    registered_id = getattr(user, 'company_id', None)
    if _is_admin(user):
        rows = repo.list_active_companies()
    else:
        row = repo.get_active_company(registered_id)
        rows = [row] if row else []
    if not rows:
        return [], None, None
    ids = [r['id'] for r in rows]
    default_id = registered_id if registered_id in ids else ids[0]
    default_name = next(r['company'] for r in rows if r['id'] == default_id)
    tenants = [{
        'company_id': r['id'],
        'company_name': r['company'],
        'company_code': _company_code(r['company']),
        'is_default': r['id'] == default_id,
    } for r in rows]
    return tenants, default_id, default_name


def _user_block(user):
    return {
        'id': getattr(user, 'id', None),
        'email': getattr(user, 'email', None),
        'full_name': getattr(user, 'name', None),
        'role': getattr(user, 'role_name', None),
    }


def _audit(event_type: str, user, description: str, authorized: bool, company_id=None) -> None:
    """Best-effort audit to ``user_events`` (actor, company_id, action, timestamp).
    Never breaks the response; never records passwords/OTPs/tokens."""
    try:
        from core.auth.repositories.event_repository import EventRepository
        details = {'integration': 'business_control', 'authorized': authorized}
        if company_id is not None:
            details['company_id'] = company_id
        EventRepository().log_event(
            event_type=event_type,
            event_description=description,
            user_id=getattr(user, 'id', None),
            user_email=getattr(user, 'email', None),
            entity_type='integration',
            entity_id=company_id,
            ip_address=request.headers.get('X-Forwarded-For', request.remote_addr),
            user_agent=request.headers.get('User-Agent'),
            details=details,
        )
    except Exception:  # pragma: no cover - audit must not affect the contract
        logger.exception('business_control audit logging failed (non-fatal)')


def _throttle(key_suffix: str):
    """Returns a 429 response tuple if over budget, else None."""
    allowed, retry_after = _rate_limiter.is_allowed(
        f'bc:{key_suffix}:{current_user.id}',
        max_requests=_RATE_MAX_REQUESTS, window_seconds=_RATE_WINDOW_SECONDS,
    )
    if not allowed:
        resp, code = error_response('Too many requests', 429)
        resp.headers['Retry-After'] = str(retry_after)
        return resp, code
    return None


def _tenant_denied():
    # Uniform 403 for POST — never reveals whether other companies exist.
    return jsonify({'success': False, 'authorized': False, 'error': 'Tenant access denied'}), 403


# ── GET: authorize + list available tenants ────────────────────────────────────

@integrations_bp.route('/api/integrations/business-control/authorize', methods=['GET'])
def business_control_authorize():
    if not current_user.is_authenticated:
        return error_response('Authentication required', 401)

    throttled = _throttle('authorize')
    if throttled:
        return throttled

    # Active account first, so a disabled admin is still denied (see prior task).
    if not getattr(current_user, 'is_active', False):
        _audit('business_control.authorize_denied', current_user, 'inactive account', False)
        return error_response('Permission denied', 403)

    if not _has_business_control_access(current_user):
        _audit('business_control.authorize_denied', current_user, 'missing business_control.access', False)
        return error_response('Permission denied', 403)

    tenants, default_id, default_name = _eligible_companies(current_user)
    if not tenants:
        _audit('business_control.authorize_denied', current_user, 'no eligible active companies', False)
        return error_response('Permission denied', 403)

    _audit('business_control.authorize', current_user, 'authorized', True, company_id=default_id)
    return jsonify({
        'success': True,
        'authorized': True,
        'user': _user_block(current_user),
        'permission': BUSINESS_CONTROL_PERMISSION,
        'tenant_selection_required': len(tenants) > 1,
        'default_company_id': default_id,
        'available_tenants': tenants,
        # Backward-compatible superset: the currently-deployed consumers read `scope`.
        'scope': {'tenant_id': default_id, 'company_id': default_id, 'company': default_name},
    })


# ── POST: select one tenant (server-verified) ──────────────────────────────────

@integrations_bp.route('/api/integrations/business-control/authorize', methods=['POST'])
def business_control_select_tenant():
    if not current_user.is_authenticated:
        return error_response('Authentication required', 401)

    throttled = _throttle('select')
    if throttled:
        return throttled

    # Any authorization failure returns the uniform, non-leaky tenant-denied 403.
    if not getattr(current_user, 'is_active', False) or not _has_business_control_access(current_user):
        _audit('business_control.tenant_denied', current_user, 'not authorized', False)
        return _tenant_denied()

    data = request.get_json(silent=True) or {}
    raw = data.get('company_id')
    if raw is None:
        return error_response('company_id is required', 400)
    try:
        company_id = int(raw)
    except (TypeError, ValueError):
        return error_response('company_id must be an integer', 400)

    # Recompute the eligible set server-side — the posted value is NEVER trusted.
    tenants, _default_id, _default_name = _eligible_companies(current_user)
    match = next((t for t in tenants if t['company_id'] == company_id), None)
    if not match:
        _audit('business_control.tenant_denied', current_user, 'company not permitted', False,
               company_id=company_id)
        return _tenant_denied()

    _audit('business_control.tenant_selected', current_user, 'tenant selected', True,
           company_id=company_id)
    return jsonify({
        'success': True,
        'authorized': True,
        'user': _user_block(current_user),
        'scope': {
            'tenant_id': company_id,
            'company_id': company_id,
            'company': match['company_name'],
        },
        'permission': BUSINESS_CONTROL_PERMISSION,
    })


# ── Admin read-only view (#5): does user X have BC access + which company ──────

@integrations_bp.route('/api/integrations/business-control/admin/users/<int:user_id>/access',
                       methods=['GET'])
@admin_required
def bc_admin_user_access(user_id):
    """Admin-only view of a user's BUSINESS CONTROL access. Read-only — company
    membership is managed via the existing Settings->Users, permissions via
    Settings->Roles. Never returns secrets."""
    # Re-check the caller is still active (a session cookie is not re-validated per
    # request), matching the GET/POST authorize handlers.
    if not getattr(current_user, 'is_active', False):
        return error_response('Permission denied', 403)

    data = UserRepository().get_by_id(user_id)
    if not data:
        return error_response('User not found', 404)

    is_admin = bool(data.get('can_access_settings'))
    has_bc = _role_has_bc_access(data.get('role_id'), is_admin)
    registered_company = None
    if data.get('company_id'):
        registered_company = {'company_id': data.get('company_id'), 'company_name': data.get('company')}

    return jsonify({
        'success': True,
        'user': {
            'id': data.get('id'),
            'email': data.get('email'),
            'full_name': data.get('name'),
            'role': data.get('role_name'),
        },
        'has_business_control_access': has_bc,
        'sees_all_companies': is_admin,
        'registered_company': registered_company,
    })
