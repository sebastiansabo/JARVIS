"""DMS category routes."""
import re
import logging
from flask import request, jsonify
from flask_login import login_required, current_user

from dms import dms_bp
from dms.repositories import CategoryRepository
from dms.routes.documents import dms_permission_required
from core.utils.api_helpers import safe_error_response, get_json_or_error

logger = logging.getLogger('jarvis.dms.routes.categories')

_cat_repo = CategoryRepository()


@dms_bp.route('/api/dms/categories', methods=['GET'])
@login_required
@dms_permission_required('category', 'view')
def api_list_categories():
    """List categories (filtered by role for non-admin users)."""
    company_id = getattr(current_user, 'company_id', None)
    active_only = request.args.get('active_only', 'true').lower() != 'false'
    # Non-admin users only see categories their role has access to
    role_id = getattr(current_user, 'role_id', None) if company_id else None
    categories = _cat_repo.list_all(company_id=company_id, active_only=active_only, role_id=role_id)
    return jsonify({'success': True, 'categories': categories})


@dms_bp.route('/api/dms/categories/<int:cat_id>', methods=['GET'])
@login_required
@dms_permission_required('category', 'view')
def api_get_category(cat_id):
    """Get a single category."""
    cat = _cat_repo.get_by_id(cat_id)
    if not cat:
        return jsonify({'success': False, 'error': 'Category not found'}), 404
    return jsonify({'success': True, 'category': cat})


@dms_bp.route('/api/dms/categories', methods=['POST'])
@login_required
@dms_permission_required('category', 'manage')
def api_create_category():
    """Create a new category."""
    data, error = get_json_or_error()
    if error:
        return error

    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name is required'}), 400

    slug = data.get('slug', '').strip()
    if not slug:
        slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

    company_id = getattr(current_user, 'company_id', None)

    try:
        allowed_role_ids = data.get('allowed_role_ids')
        if isinstance(allowed_role_ids, list):
            allowed_role_ids = [int(r) for r in allowed_role_ids] or None
        else:
            allowed_role_ids = None
        row = _cat_repo.create(
            name=name, slug=slug, company_id=company_id,
            icon=data.get('icon', 'bi-folder'),
            color=data.get('color', '#6c757d'),
            description=data.get('description'),
            sort_order=data.get('sort_order', 0),
            created_by=current_user.id,
            allowed_role_ids=allowed_role_ids,
        )
        return jsonify({'success': True, 'id': row['id']}), 201
    except Exception as e:
        return safe_error_response(e)


@dms_bp.route('/api/dms/categories/<int:cat_id>', methods=['PUT'])
@login_required
@dms_permission_required('category', 'manage')
def api_update_category(cat_id):
    """Update a category."""
    data, error = get_json_or_error()
    if error:
        return error

    cat = _cat_repo.get_by_id(cat_id)
    if not cat:
        return jsonify({'success': False, 'error': 'Category not found'}), 404

    try:
        fields = {}
        for key in ('name', 'slug', 'icon', 'color', 'description', 'sort_order', 'is_active'):
            if key in data:
                fields[key] = data[key]
        if 'allowed_role_ids' in data:
            val = data['allowed_role_ids']
            fields['allowed_role_ids'] = [int(r) for r in val] if isinstance(val, list) and val else None
        _cat_repo.update(cat_id, **fields)
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@dms_bp.route('/api/dms/categories/<int:cat_id>', methods=['DELETE'])
@login_required
@dms_permission_required('category', 'manage')
def api_delete_category(cat_id):
    """Soft-delete a category (set inactive)."""
    cat = _cat_repo.get_by_id(cat_id)
    if not cat:
        return jsonify({'success': False, 'error': 'Category not found'}), 404
    _cat_repo.delete(cat_id)
    return jsonify({'success': True})


@dms_bp.route('/api/dms/categories/reorder', methods=['PUT'])
@login_required
@dms_permission_required('category', 'manage')
def api_reorder_categories():
    """Bulk reorder categories."""
    data, error = get_json_or_error()
    if error:
        return error

    ids = data.get('ids', [])
    if not ids or not isinstance(ids, list):
        return jsonify({'success': False, 'error': 'ids array required'}), 400

    try:
        _cat_repo.reorder(ids)
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)
