"""Forms CRUD routes (authenticated)."""

import logging

from flask import jsonify, request, g
from flask_login import login_required, current_user

from forms import forms_bp
from forms.repositories import FormRepository
from forms.services.form_service import FormService, UserContext
from core.utils.api_helpers import get_json_or_error, handle_api_errors, v2_permission_required

logger = logging.getLogger('jarvis.forms.routes.forms')

_form_repo = FormRepository()
_service = FormService()

# Whitelist of fields allowed in update (no status, owner_id, or requires_approval)
_UPDATABLE_FIELDS = {'name', 'description', 'schema', 'settings', 'utm_config', 'branding'}


def form_permission_required(entity, action):
    """Forms V2 permission check."""
    return v2_permission_required('forms', entity, action)


def _check_company_access(form):
    """Return True if current_user can access this form's company."""
    if not form:
        return False
    return form.get('company_id') == getattr(current_user, 'company_id', None)


# ---- List / Get ----

@forms_bp.route('/api/forms', methods=['GET'])
@login_required
@form_permission_required('form', 'view')
def api_list_forms():
    """List forms with optional filters."""
    filters = {
        'status': request.args.get('status'),
        'company_id': getattr(current_user, 'company_id', None),
        'owner_id': request.args.get('owner_id'),
        'search': request.args.get('search'),
        'limit': request.args.get('limit', 100),
        'offset': request.args.get('offset', 0),
    }
    filters = {k: v for k, v in filters.items() if v is not None}

    scope = getattr(g, 'permission_scope', 'all')
    if scope == 'own':
        filters['owner_id'] = current_user.id

    result = _form_repo.list_forms(filters)
    return jsonify(result)


@forms_bp.route('/api/forms/<int:form_id>', methods=['GET'])
@login_required
@form_permission_required('form', 'view')
def api_get_form(form_id):
    """Get form detail."""
    form = _form_repo.get_by_id(form_id)
    if not form or not _check_company_access(form):
        return jsonify({'success': False, 'error': 'Form not found'}), 404
    return jsonify(form)


# ---- Create ----

@forms_bp.route('/api/forms', methods=['POST'])
@login_required
@form_permission_required('form', 'create')
@handle_api_errors
def api_create_form():
    """Create a new form."""
    data, error = get_json_or_error()
    if error:
        return error

    # Force company_id to current user's company
    data['company_id'] = getattr(current_user, 'company_id', data.get('company_id'))
    user = UserContext(user_id=current_user.id)
    result = _service.create_form(data, user)
    if result.success:
        return jsonify({'success': True, **result.data}), result.status_code
    return jsonify({'success': False, 'error': result.error}), result.status_code


# ---- Update ----

@forms_bp.route('/api/forms/<int:form_id>', methods=['PUT'])
@login_required
@form_permission_required('form', 'edit')
@handle_api_errors
def api_update_form(form_id):
    """Update form fields (name, description, schema, settings, etc.)."""
    data, error = get_json_or_error()
    if error:
        return error

    form = _form_repo.get_by_id(form_id)
    if not form or not _check_company_access(form):
        return jsonify({'success': False, 'error': 'Form not found'}), 404

    # Whitelist safe fields only
    safe_data = {k: v for k, v in data.items() if k in _UPDATABLE_FIELDS}
    if not safe_data:
        return jsonify({'success': False, 'error': 'No valid fields to update'}), 400

    _form_repo.update(form_id, **safe_data)
    return jsonify({'success': True})


# ---- Publish / Disable ----

@forms_bp.route('/api/forms/<int:form_id>/publish', methods=['POST'])
@login_required
@form_permission_required('form', 'edit')
@handle_api_errors
def api_publish_form(form_id):
    """Publish form (makes it publicly accessible)."""
    form = _form_repo.get_by_id(form_id)
    if not form or not _check_company_access(form):
        return jsonify({'success': False, 'error': 'Form not found'}), 404

    user = UserContext(user_id=current_user.id)
    result = _service.publish_form(form_id, user)
    if result.success:
        return jsonify({'success': True, **result.data})
    return jsonify({'success': False, 'error': result.error}), result.status_code


@forms_bp.route('/api/forms/<int:form_id>/disable', methods=['POST'])
@login_required
@form_permission_required('form', 'edit')
def api_disable_form(form_id):
    """Disable a published form."""
    form = _form_repo.get_by_id(form_id)
    if not form or not _check_company_access(form):
        return jsonify({'success': False, 'error': 'Form not found'}), 404

    _form_repo.disable(form_id)
    return jsonify({'success': True})


# ---- Duplicate ----

@forms_bp.route('/api/forms/<int:form_id>/duplicate', methods=['POST'])
@login_required
@form_permission_required('form', 'create')
@handle_api_errors
def api_duplicate_form(form_id):
    """Clone a form."""
    form = _form_repo.get_by_id(form_id)
    if not form or not _check_company_access(form):
        return jsonify({'success': False, 'error': 'Form not found'}), 404

    new_id = _form_repo.duplicate(form_id, current_user.id)
    if not new_id:
        return jsonify({'success': False, 'error': 'Failed to duplicate form'}), 500
    return jsonify({'success': True, 'id': new_id}), 201


# ---- Delete ----

@forms_bp.route('/api/forms/<int:form_id>', methods=['DELETE'])
@login_required
@form_permission_required('form', 'delete')
def api_delete_form(form_id):
    """Soft-delete a form."""
    form = _form_repo.get_by_id(form_id)
    if not form or not _check_company_access(form):
        return jsonify({'success': False, 'error': 'Form not found'}), 404

    deleted = _form_repo.soft_delete(form_id)
    if not deleted:
        return jsonify({'success': False, 'error': 'Form not found'}), 404
    return jsonify({'success': True})
