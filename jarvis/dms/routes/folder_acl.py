"""DMS Folder ACL routes — per-user/role permission management."""
import logging
from flask import request, jsonify
from flask_login import login_required, current_user

from dms import dms_bp
from dms.repositories import FolderRepository, FolderAclRepository, AuditRepository
from core.utils.api_helpers import safe_error_response, v2_permission_required

logger = logging.getLogger('jarvis.dms.routes.folder_acl')

_folder_repo = FolderRepository()
_acl_repo = FolderAclRepository()
_audit_repo = AuditRepository()


def dms_permission_required(entity, action):
    return v2_permission_required('dms', entity, action)


@dms_bp.route('/api/dms/folders/<int:folder_id>/acl', methods=['GET'])
@login_required
@dms_permission_required('folder', 'view')
def api_get_folder_acl(folder_id):
    """Get ACL entries for a folder."""
    try:
        folder = _folder_repo.get_by_id(folder_id)
        if not folder:
            return jsonify({'success': False, 'error': 'Folder not found'}), 404

        entries = _acl_repo.get_by_folder(folder_id)
        return jsonify({'success': True, 'acl': entries})
    except Exception as e:
        logger.exception('Failed to get folder ACL')
        return safe_error_response(e)


@dms_bp.route('/api/dms/folders/<int:folder_id>/acl', methods=['POST'])
@login_required
@dms_permission_required('folder', 'manage_acl')
def api_set_folder_acl(folder_id):
    """Set or update an ACL entry for a folder."""
    try:
        folder = _folder_repo.get_by_id(folder_id)
        if not folder:
            return jsonify({'success': False, 'error': 'Folder not found'}), 404

        # Check folder-level manage permission
        perms = _acl_repo.resolve_permissions(
            current_user.id, current_user.role_id,
            current_user.role_name, folder_id)
        if not perms.get('can_manage') and current_user.role_name not in ('Admin', 'Manager'):
            return jsonify({'success': False, 'error': 'No permission to manage ACL'}), 403

        data = request.get_json()
        user_id = data.get('user_id')
        role_id = data.get('role_id')

        if not user_id and not role_id:
            return jsonify({'success': False, 'error': 'Must specify user_id or role_id'}), 400

        entry = _acl_repo.set_acl(
            folder_id=folder_id,
            granted_by=current_user.id,
            user_id=user_id,
            role_id=role_id,
            can_view=data.get('can_view', False),
            can_add=data.get('can_add', False),
            can_edit=data.get('can_edit', False),
            can_delete=data.get('can_delete', False),
            can_manage=data.get('can_manage', False)
        )

        _audit_repo.log('acl', entry['id'], 'permission_granted',
                        current_user.id, current_user.company_id,
                        changes={
                            'folder_id': folder_id,
                            'user_id': user_id, 'role_id': role_id,
                            'can_view': data.get('can_view'),
                            'can_add': data.get('can_add'),
                            'can_edit': data.get('can_edit'),
                            'can_delete': data.get('can_delete'),
                            'can_manage': data.get('can_manage')
                        },
                        ip_address=request.remote_addr)

        return jsonify({'success': True, 'entry': entry})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.exception('Failed to set folder ACL')
        return safe_error_response(e)


@dms_bp.route('/api/dms/folders/<int:folder_id>/acl/batch', methods=['POST'])
@login_required
@dms_permission_required('folder', 'manage_acl')
def api_batch_set_folder_acl(folder_id):
    """Set multiple ACL entries at once."""
    try:
        folder = _folder_repo.get_by_id(folder_id)
        if not folder:
            return jsonify({'success': False, 'error': 'Folder not found'}), 404

        perms = _acl_repo.resolve_permissions(
            current_user.id, current_user.role_id,
            current_user.role_name, folder_id)
        if not perms.get('can_manage') and current_user.role_name not in ('Admin', 'Manager'):
            return jsonify({'success': False, 'error': 'No permission to manage ACL'}), 403

        data = request.get_json()
        entries = data.get('entries', [])
        if not entries:
            return jsonify({'success': False, 'error': 'No entries provided'}), 400

        results = _acl_repo.batch_set_acl(folder_id, entries, current_user.id)

        _audit_repo.log('acl', folder_id, 'batch_permission_update',
                        current_user.id, current_user.company_id,
                        changes={'entries_count': len(entries)},
                        ip_address=request.remote_addr)

        return jsonify({'success': True, 'entries': results})
    except Exception as e:
        logger.exception('Failed to batch set folder ACL')
        return safe_error_response(e)


@dms_bp.route('/api/dms/folders/<int:folder_id>/acl/<int:acl_id>', methods=['DELETE'])
@login_required
@dms_permission_required('folder', 'manage_acl')
def api_remove_folder_acl(folder_id, acl_id):
    """Remove an ACL entry."""
    try:
        perms = _acl_repo.resolve_permissions(
            current_user.id, current_user.role_id,
            current_user.role_name, folder_id)
        if not perms.get('can_manage') and current_user.role_name not in ('Admin', 'Manager'):
            return jsonify({'success': False, 'error': 'No permission to manage ACL'}), 403

        _acl_repo.remove_acl(acl_id)

        _audit_repo.log('acl', acl_id, 'permission_revoked',
                        current_user.id, current_user.company_id,
                        changes={'folder_id': folder_id},
                        ip_address=request.remote_addr)

        return jsonify({'success': True})
    except Exception as e:
        logger.exception('Failed to remove folder ACL')
        return safe_error_response(e)


@dms_bp.route('/api/dms/folders/<int:folder_id>/my-permissions', methods=['GET'])
@login_required
def api_get_my_folder_permissions(folder_id):
    """Get current user's effective permissions on a folder."""
    try:
        perms = _acl_repo.resolve_permissions(
            current_user.id, current_user.role_id,
            current_user.role_name, folder_id)
        return jsonify({'success': True, 'permissions': perms})
    except Exception as e:
        logger.exception('Failed to get folder permissions')
        return safe_error_response(e)
