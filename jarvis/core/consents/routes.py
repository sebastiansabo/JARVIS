"""HTTP routes for the mandatory consent-documents gate.

No SQL / no raw DB driver import here (Ruling R1 — enforced by a post-commit
Architecture hook) — everything goes through ConsentService / ConsentRepository.

Permission gating (Ruling R2): the task brief specified
`@v2_permission_required('settings', 'consents', 'view'/'edit')` for the
document editor and `@v2_permission_required('hr', 'consents', 'view')` for
compliance. Investigation (see task-4-report.md) found module_key='settings'
does not exist anywhere in the permissions_v2 seed (grep of
migrations/domains/schema_roles.py) — only 'system' (entity_key='settings')
does. Seeding a brand-new 'settings' module would be silently useless for
every role until someone separately grants it, since v2_permission_required's
own admin bypass (`is_admin` / `can_access_settings`) already gates on the
established `can_access_settings` flag regardless of which module/entity is
named. So instead of literally seeding permissions_v2 rows, the local gates
below mirror the existing fallback pattern from
core/organization/routes.py (`_structure_view_required` /
`_structure_edit_required`) and the inline `can_access_hr or
can_access_settings` checks in core/connectors/{connecteam,sincron,
verification}/routes.py: check the v2 matrix first (forward-compatible if
`system.consents.*` / `hr.consents.view` are ever explicitly seeded for a
narrower role), then fall back to the established `can_access_settings`
(Settings admin) / `can_access_hr` (HR admin) boolean flags already present on
every role.
"""
from functools import wraps

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from core.consents.services.consent_service import ConsentService

consents_bp = Blueprint('consents', __name__)
_svc = ConsentService()


def _client_ip() -> str:
    fwd = request.headers.get('X-Forwarded-For', '')
    return (fwd.split(',')[0].strip() if fwd else '') or (request.remote_addr or '')


def _do_sign():
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(_svc.sign(
            current_user.id,
            int(data.get('document_id') or 0),
            data.get('signature_image') or '',
            _client_ip(),
            request.headers.get('User-Agent', ''),
        ))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


# ---------- Ruling R2: local admin/HR gates (see module docstring) ----------

def _consents_admin_required(action: str):
    """Settings-admin gate for the consent-document editor (view/edit).

    Checks the v2 permission matrix (module='system', entity='consents')
    first, then falls back to the established `can_access_settings` flag —
    same shape as core/organization/routes.py's _structure_*_required.
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({'error': 'Authentication required'}), 401
            role_id = getattr(current_user, 'role_id', None)
            if role_id:
                from core.roles.repositories.permission_repository import PermissionRepository
                perm = PermissionRepository().check_permission_v2(role_id, 'system', 'consents', action)
                if perm.get('has_permission'):
                    return f(*args, **kwargs)
            if getattr(current_user, 'can_access_settings', False):
                return f(*args, **kwargs)
            return jsonify({'error': f'Permission denied: consents {action} required'}), 403
        return decorated
    return decorator


def _consents_compliance_required(f):
    """HR-admin gate for the compliance dashboard.

    Checks the v2 permission matrix (module='hr', entity='consents',
    action='view') first, then falls back to `can_access_hr` or
    `can_access_settings` — mirrors the inline checks already used by
    core/connectors/connecteam/routes.py, core/connectors/sincron/routes.py
    and core/connectors/verification/routes.py.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': 'Authentication required'}), 401
        role_id = getattr(current_user, 'role_id', None)
        if role_id:
            from core.roles.repositories.permission_repository import PermissionRepository
            perm = PermissionRepository().check_permission_v2(role_id, 'hr', 'consents', 'view')
            if perm.get('has_permission'):
                return f(*args, **kwargs)
        if getattr(current_user, 'can_access_hr', False) or getattr(current_user, 'can_access_settings', False):
            return f(*args, **kwargs)
        return jsonify({'error': 'Permission denied: HR consents view required'}), 403
    return decorated


# ---------- user-facing (web) ----------
@consents_bp.route('/api/consents/pending')
@login_required
def pending():
    return jsonify(_svc.get_pending_for_user(current_user.id))


@consents_bp.route('/api/consents/sign', methods=['POST'])
@login_required
def sign():
    return _do_sign()


@consents_bp.route('/api/consents/documents/<doc_key>')
@login_required
def get_document(doc_key):
    doc = _svc.repo.get_by_key(doc_key)
    if not doc:
        return jsonify({'error': 'not_found'}), 404
    return jsonify({'document': doc})


# ---------- user-facing (mobile mirror) ----------
# @login_required is valid here too: app.py's `_jwt_session_bridge`
# before_request hook (registered globally in _register_hooks, runs before
# any view/blueprint dispatch) turns a Capacitor request's `Authorization:
# Bearer <JWT>` header into an active flask_login session via login_user()
# whenever there's no session cookie yet — see Ruling R3 in task-4-report.md.
@consents_bp.route('/api/mobile/consents/pending')
@login_required
def mobile_pending():
    return jsonify(_svc.get_pending_for_user(current_user.id))


@consents_bp.route('/api/mobile/consents/sign', methods=['POST'])
@login_required
def mobile_sign():
    return _do_sign()


# ---------- admin editor (Settings) ----------
@consents_bp.route('/api/consents/documents')
@_consents_admin_required('view')
def list_documents():
    return jsonify({'documents': _svc.repo.list_all()})


@consents_bp.route('/api/consents/documents', methods=['POST'])
@_consents_admin_required('edit')
def create_document():
    d = request.get_json(silent=True) or {}
    if not d.get('doc_key') or not d.get('title'):
        return jsonify({'error': 'doc_key_and_title_required'}), 400
    doc = _svc.repo.create_document(
        d['doc_key'], d['title'], d.get('body', ''), int(d.get('sort_order', 0)),
        bool(d.get('requires_signature', True)), bool(d.get('is_mandatory', True)),
        bool(d.get('is_active', False)), current_user.id)
    return jsonify({'document': doc}), 201


@consents_bp.route('/api/consents/documents/<int:doc_id>', methods=['PUT'])
@_consents_admin_required('edit')
def update_document(doc_id):
    d = request.get_json(silent=True) or {}
    existing = _svc.repo.get_by_id(doc_id)
    if not existing:
        return jsonify({'error': 'not_found'}), 404
    bump = 'body' in d and d['body'] != existing['body']
    doc = _svc.repo.update_document(
        doc_id,
        d.get('title', existing['title']),
        d.get('body', existing['body']),
        int(d.get('sort_order', existing['sort_order'])),
        bool(d.get('is_active', existing['is_active'])),
        bump, current_user.id)
    return jsonify({'document': doc})


# ---------- HR compliance ----------
@consents_bp.route('/api/consents/compliance')
@_consents_compliance_required
def compliance():
    rows = _svc.repo.get_compliance()
    users = {}
    for r in rows:
        u = users.setdefault(r['user_id'], {
            'user_id': r['user_id'], 'name': r['name'],
            'email': r['email'], 'company': r['company'], 'documents': []})
        u['documents'].append({
            'doc_key': r['doc_key'], 'title': r['title'],
            'signed': bool(r['signed']), 'signed_at': r['signed_at']})
    result = list(users.values())
    if request.args.get('status') == 'pending':
        result = [u for u in result if not all(d['signed'] for d in u['documents'])]
    return jsonify({'compliance': result})
