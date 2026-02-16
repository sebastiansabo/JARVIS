"""Role and permission routes."""
from flask import jsonify, request
from flask_login import login_required

from . import roles_bp
from .repositories import RoleRepository, PermissionRepository
from core.utils.api_helpers import admin_required, safe_error_response

_role_repo = RoleRepository()
_perm_repo = PermissionRepository()


# ============== ROLE MANAGEMENT ==============

@roles_bp.route('/api/roles', methods=['GET'])
@login_required
def api_get_roles():
    """Get all roles with their permissions."""
    roles = _role_repo.get_all()
    for role in roles:
        role['permissions'] = _perm_repo.get_role_permissions_list(role['id'])
    return jsonify(roles)


@roles_bp.route('/api/roles/<int:role_id>', methods=['GET'])
@login_required
def api_get_role(role_id):
    """Get a specific role."""
    role = _role_repo.get(role_id)
    if role:
        return jsonify(role)
    return jsonify({'error': 'Role not found'}), 404


@roles_bp.route('/api/roles', methods=['POST'])
@admin_required
def api_create_role():
    """Create a new role."""
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    try:
        role_id = _role_repo.save(
            name=name,
            description=data.get('description'),
            can_add_invoices=data.get('can_add_invoices', False),
            can_edit_invoices=data.get('can_edit_invoices', False),
            can_delete_invoices=data.get('can_delete_invoices', False),
            can_view_invoices=data.get('can_view_invoices', False),
            can_access_accounting=data.get('can_access_accounting', False),
            can_access_settings=data.get('can_access_settings', False),
            can_access_connectors=data.get('can_access_connectors', False),
            can_access_templates=data.get('can_access_templates', False),
            can_access_hr=data.get('can_access_hr', False),
            is_hr_manager=data.get('is_hr_manager', False)
        )
        return jsonify({'success': True, 'id': role_id})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return safe_error_response(e)


@roles_bp.route('/api/roles/<int:role_id>', methods=['PUT'])
@admin_required
def api_update_role(role_id):
    """Update a role."""
    data = request.get_json()
    try:
        updated = _role_repo.update(
            role_id=role_id,
            name=data.get('name'),
            description=data.get('description'),
            can_add_invoices=data.get('can_add_invoices'),
            can_edit_invoices=data.get('can_edit_invoices'),
            can_delete_invoices=data.get('can_delete_invoices'),
            can_view_invoices=data.get('can_view_invoices'),
            can_access_accounting=data.get('can_access_accounting'),
            can_access_settings=data.get('can_access_settings'),
            can_access_connectors=data.get('can_access_connectors'),
            can_access_templates=data.get('can_access_templates'),
            can_access_hr=data.get('can_access_hr'),
            is_hr_manager=data.get('is_hr_manager')
        )
        if updated:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Role not found'}), 404
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return safe_error_response(e)


@roles_bp.route('/api/roles/<int:role_id>', methods=['DELETE'])
@admin_required
def api_delete_role(role_id):
    """Delete a role."""
    try:
        if _role_repo.delete(role_id):
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Role not found'}), 404
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ============== PERMISSIONS v1 ==============

@roles_bp.route('/api/permissions', methods=['GET'])
@login_required
def api_get_permissions():
    """Get all permissions grouped by module."""
    modules = _perm_repo.get_all()
    return jsonify({'modules': modules})


@roles_bp.route('/api/permissions/flat', methods=['GET'])
@login_required
def api_get_permissions_flat():
    """Get all permissions as flat list."""
    permissions = _perm_repo.get_flat()
    return jsonify({'permissions': permissions})


@roles_bp.route('/api/roles/<int:role_id>/permissions', methods=['GET'])
@login_required
def api_get_role_perms(role_id):
    """Get permissions for a specific role."""
    perms = _perm_repo.get_role_permissions_list(role_id)
    return jsonify({'permissions': perms})


@roles_bp.route('/api/roles/<int:role_id>/permissions', methods=['PUT'])
@admin_required
def api_set_role_perms(role_id):
    """Set permissions for a role."""
    data = request.get_json()
    permissions = data.get('permissions', [])
    try:
        _perm_repo.set_role_permissions(role_id, permissions)
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


# ============== PERMISSIONS v2 (Matrix) ==============

@roles_bp.route('/api/permissions/matrix', methods=['GET'])
@login_required
def api_get_permission_matrix():
    """Get permission matrix structure with modules, entities, actions and roles."""
    matrix = _perm_repo.get_matrix()
    role_perms = _perm_repo.get_all_role_permissions_v2()
    return jsonify({
        'modules': matrix['modules'],
        'roles': matrix['roles'],
        'role_permissions': role_perms
    })


@roles_bp.route('/api/roles/<int:role_id>/permissions/v2', methods=['GET'])
@login_required
def api_get_role_perms_v2(role_id):
    """Get v2 permissions for a specific role."""
    perms = _perm_repo.get_role_permissions_v2(role_id)
    return jsonify({'permissions': perms})


@roles_bp.route('/api/roles/<int:role_id>/permissions/v2', methods=['PUT'])
@admin_required
def api_set_role_perms_v2(role_id):
    """Set v2 permissions for a role."""
    data = request.get_json()
    permissions = data.get('permissions', {})
    try:
        _perm_repo.set_role_permissions_v2_bulk(role_id, permissions)
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@roles_bp.route('/api/permissions/v2/<int:permission_id>/role/<int:role_id>', methods=['PUT'])
@admin_required
def api_set_single_permission_v2(permission_id, role_id):
    """Set a single v2 permission for a role."""
    data = request.get_json()
    try:
        _perm_repo.set_role_permission_v2(
            role_id=role_id,
            permission_id=permission_id,
            scope=data.get('scope'),
            granted=data.get('granted')
        )
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)
