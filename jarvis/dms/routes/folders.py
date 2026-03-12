"""DMS Folder routes — hierarchical folder CRUD."""
import logging
from flask import request, jsonify
from flask_login import login_required, current_user

from dms import dms_bp
from dms.repositories import FolderRepository, FolderAclRepository, AuditRepository
from dms.services.folder_sync_service import FolderSyncService
from dms.services.folder_drive_sync import FolderDriveSyncService
from core.utils.api_helpers import safe_error_response, v2_permission_required

logger = logging.getLogger('jarvis.dms.routes.folders')

_folder_repo = FolderRepository()
_acl_repo = FolderAclRepository()
_audit_repo = AuditRepository()
_folder_sync = FolderSyncService()
_drive_sync = FolderDriveSyncService()


def dms_permission_required(entity, action):
    return v2_permission_required('dms', entity, action)


# ── Tree & Navigation ──

@dms_bp.route('/api/dms/folders', methods=['GET'])
@login_required
@dms_permission_required('folder', 'view')
def api_list_folders():
    """Get root folders for user's company, or children of a parent."""
    try:
        parent_id = request.args.get('parent_id', type=int)
        company_id = current_user.company_id

        if parent_id:
            folders = _folder_repo.get_children(parent_id)
        else:
            folders = _folder_repo.get_tree(company_id)

        return jsonify({'success': True, 'folders': folders})
    except Exception as e:
        logger.exception('Failed to list folders')
        return safe_error_response(e)


@dms_bp.route('/api/dms/folders/<int:folder_id>', methods=['GET'])
@login_required
@dms_permission_required('folder', 'view')
def api_get_folder(folder_id):
    """Get folder details with ancestors (breadcrumb)."""
    try:
        folder = _folder_repo.get_by_id(folder_id)
        if not folder:
            return jsonify({'success': False, 'error': 'Folder not found'}), 404

        ancestors = _folder_repo.get_ancestors(folder_id)
        children = _folder_repo.get_children(folder_id)

        return jsonify({
            'success': True,
            'folder': folder,
            'ancestors': ancestors,
            'children': children
        })
    except Exception as e:
        logger.exception('Failed to get folder')
        return safe_error_response(e)


@dms_bp.route('/api/dms/folders/tree', methods=['GET'])
@login_required
@dms_permission_required('folder', 'view')
def api_get_full_tree():
    """Get full folder tree (for tree sidebar).
    Admin/Manager see all companies; others see only their company."""
    try:
        role_name = getattr(current_user, 'role_name', '')
        if role_name in ('Admin', 'Manager'):
            # Show all companies' folders
            all_folders = _folder_repo.query_all('''
                SELECT f.id, f.name, f.icon, f.color, f.parent_id, f.depth,
                       f.path, f.sort_order, f.inherit_permissions, f.company_id,
                       f.description, f.drive_folder_id, f.drive_folder_url,
                       (SELECT COUNT(*) FROM dms_documents d
                        WHERE d.folder_id = f.id AND d.deleted_at IS NULL) as document_count,
                       (SELECT COUNT(*) FROM dms_folders sf
                        WHERE sf.parent_id = f.id AND sf.deleted_at IS NULL) as subfolder_count
                FROM dms_folders f
                WHERE f.deleted_at IS NULL
                ORDER BY f.depth, f.sort_order, f.name
            ''')
        else:
            company_id = current_user.company_id
            all_folders = _folder_repo.query_all('''
                SELECT f.id, f.name, f.icon, f.color, f.parent_id, f.depth,
                       f.path, f.sort_order, f.inherit_permissions, f.company_id,
                       f.description, f.drive_folder_id, f.drive_folder_url,
                       (SELECT COUNT(*) FROM dms_documents d
                        WHERE d.folder_id = f.id AND d.deleted_at IS NULL) as document_count,
                       (SELECT COUNT(*) FROM dms_folders sf
                        WHERE sf.parent_id = f.id AND sf.deleted_at IS NULL) as subfolder_count
                FROM dms_folders f
                WHERE f.company_id = %s AND f.deleted_at IS NULL
                ORDER BY f.depth, f.sort_order, f.name
            ''', (company_id,))

        return jsonify({'success': True, 'folders': all_folders})
    except Exception as e:
        logger.exception('Failed to get folder tree')
        return safe_error_response(e)


# ── CRUD ──

@dms_bp.route('/api/dms/folders', methods=['POST'])
@login_required
@dms_permission_required('folder', 'create')
def api_create_folder():
    """Create a new folder."""
    try:
        data = request.get_json()
        if not data or not data.get('name'):
            return jsonify({'success': False, 'error': 'Name is required'}), 400

        parent_id = data.get('parent_id')

        # If creating under a parent, check ACL (can_add)
        if parent_id:
            perms = _acl_repo.resolve_permissions(
                current_user.id, current_user.role_id,
                current_user.role_name, parent_id)
            if not perms.get('can_add') and current_user.role_name not in ('Admin', 'Manager'):
                return jsonify({'success': False, 'error': 'No permission to add to this folder'}), 403

        folder = _folder_repo.create(
            name=data['name'],
            company_id=current_user.company_id,
            created_by=current_user.id,
            parent_id=parent_id,
            description=data.get('description'),
            icon=data.get('icon', 'bi-folder'),
            color=data.get('color', '#6c757d'),
            inherit_permissions=data.get('inherit_permissions', True),
            metadata=data.get('metadata')
        )

        _audit_repo.log('folder', folder['id'], 'created',
                        current_user.id, current_user.company_id,
                        changes={'name': folder['name'], 'parent_id': parent_id},
                        ip_address=request.remote_addr)

        return jsonify({'success': True, 'folder': folder}), 201
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.exception('Failed to create folder')
        return safe_error_response(e)


@dms_bp.route('/api/dms/folders/<int:folder_id>', methods=['PUT'])
@login_required
@dms_permission_required('folder', 'edit')
def api_update_folder(folder_id):
    """Update folder metadata."""
    try:
        folder = _folder_repo.get_by_id(folder_id)
        if not folder:
            return jsonify({'success': False, 'error': 'Folder not found'}), 404

        # Check folder-level ACL
        perms = _acl_repo.resolve_permissions(
            current_user.id, current_user.role_id,
            current_user.role_name, folder_id)
        if not perms.get('can_edit') and current_user.role_name not in ('Admin', 'Manager'):
            return jsonify({'success': False, 'error': 'No permission to edit this folder'}), 403

        data = request.get_json()
        old_values = {k: folder.get(k) for k in data if k in (
            'name', 'description', 'icon', 'color', 'inherit_permissions', 'sort_order')}

        updated = _folder_repo.update(folder_id, **data)

        # Build changes diff
        changes = {}
        for k, old_val in old_values.items():
            new_val = data.get(k)
            if new_val is not None and str(new_val) != str(old_val):
                changes[k] = {'old': old_val, 'new': new_val}

        if changes:
            _audit_repo.log('folder', folder_id, 'updated',
                            current_user.id, current_user.company_id,
                            changes=changes, ip_address=request.remote_addr)

        return jsonify({'success': True, 'folder': updated})
    except Exception as e:
        logger.exception('Failed to update folder')
        return safe_error_response(e)


@dms_bp.route('/api/dms/folders/<int:folder_id>', methods=['DELETE'])
@login_required
@dms_permission_required('folder', 'delete')
def api_delete_folder(folder_id):
    """Soft-delete a folder and all subfolders."""
    try:
        folder = _folder_repo.get_by_id(folder_id)
        if not folder:
            return jsonify({'success': False, 'error': 'Folder not found'}), 404

        perms = _acl_repo.resolve_permissions(
            current_user.id, current_user.role_id,
            current_user.role_name, folder_id)
        if not perms.get('can_delete') and current_user.role_name not in ('Admin', 'Manager'):
            return jsonify({'success': False, 'error': 'No permission to delete this folder'}), 403

        # Soft-delete this folder and all descendants
        _folder_repo.soft_delete(folder_id)
        descendant_ids = _folder_repo.get_descendants_ids(folder_id)
        for did in descendant_ids:
            _folder_repo.soft_delete(did)

        _audit_repo.log('folder', folder_id, 'deleted',
                        current_user.id, current_user.company_id,
                        changes={'name': folder['name'], 'descendants': len(descendant_ids)},
                        ip_address=request.remote_addr)

        return jsonify({'success': True})
    except Exception as e:
        logger.exception('Failed to delete folder')
        return safe_error_response(e)


@dms_bp.route('/api/dms/folders/<int:folder_id>/move', methods=['POST'])
@login_required
@dms_permission_required('folder', 'edit')
def api_move_folder(folder_id):
    """Move a folder to a new parent."""
    try:
        data = request.get_json()
        new_parent_id = data.get('parent_id')  # None = move to root

        folder = _folder_repo.get_by_id(folder_id)
        if not folder:
            return jsonify({'success': False, 'error': 'Folder not found'}), 404

        old_parent_id = folder.get('parent_id')
        moved = _folder_repo.move(folder_id, new_parent_id)

        _audit_repo.log('folder', folder_id, 'moved',
                        current_user.id, current_user.company_id,
                        changes={'parent_id': {'old': old_parent_id, 'new': new_parent_id}},
                        ip_address=request.remote_addr)

        return jsonify({'success': True, 'folder': moved})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.exception('Failed to move folder')
        return safe_error_response(e)


@dms_bp.route('/api/dms/folders/reorder', methods=['PUT'])
@login_required
@dms_permission_required('folder', 'edit')
def api_reorder_folders():
    """Reorder folders within the same parent."""
    try:
        data = request.get_json()
        folder_ids = data.get('folder_ids', [])
        if not folder_ids:
            return jsonify({'success': False, 'error': 'No folder IDs provided'}), 400

        _folder_repo.reorder(folder_ids)
        return jsonify({'success': True})
    except Exception as e:
        logger.exception('Failed to reorder folders')
        return safe_error_response(e)


@dms_bp.route('/api/dms/folders/sync-structure', methods=['POST'])
@login_required
@dms_permission_required('folder', 'create')
def api_sync_folder_structure():
    """Sync folder structure: ensure Company > Year > Category folders exist.
    Admin-only operation."""
    try:
        if getattr(current_user, 'role_name', '') not in ('Admin', 'Manager'):
            return jsonify({'success': False, 'error': 'Admin/Manager only'}), 403

        data = request.get_json() or {}
        years = data.get('years')  # optional: [2025, 2026]

        result = _folder_sync.sync_all(
            created_by=current_user.id,
            years=years,
        )
        return jsonify({'success': True, **result})
    except Exception as e:
        logger.exception('Failed to sync folder structure')
        return safe_error_response(e)


# ── Google Drive Sync ──

@dms_bp.route('/api/dms/folders/<int:folder_id>/drive-sync', methods=['POST'])
@login_required
@dms_permission_required('folder', 'edit')
def api_sync_folder_drive(folder_id):
    """Sync a single folder (and ancestors) to Google Drive."""
    try:
        result = _drive_sync.sync_folder_to_drive(folder_id)
        status = 200 if result.get('success') else 500
        return jsonify(result), status
    except Exception as e:
        logger.exception('Failed to sync folder %d to Drive', folder_id)
        return safe_error_response(e)


@dms_bp.route('/api/dms/folders/<int:folder_id>/drive-sync', methods=['GET'])
@login_required
@dms_permission_required('folder', 'view')
def api_get_folder_drive_status(folder_id):
    """Get Drive sync status for a folder."""
    try:
        folder = _folder_repo.get_by_id(folder_id)
        if not folder:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        return jsonify({
            'success': True,
            'synced': bool(folder.get('drive_folder_id')),
            'drive_folder_id': folder.get('drive_folder_id'),
            'drive_folder_url': folder.get('drive_folder_url'),
            'drive_synced_at': folder.get('drive_synced_at'),
        })
    except Exception as e:
        return safe_error_response(e)


@dms_bp.route('/api/dms/folders/drive-sync-all', methods=['POST'])
@login_required
@dms_permission_required('folder', 'edit')
def api_sync_all_folders_drive():
    """Sync entire folder tree to Google Drive. Admin-only."""
    try:
        if getattr(current_user, 'role_name', '') not in ('Admin', 'Manager'):
            return jsonify({'success': False, 'error': 'Admin/Manager only'}), 403

        data = request.get_json() or {}
        company_id = data.get('company_id')

        result = _drive_sync.sync_tree_to_drive(company_id=company_id)
        return jsonify(result)
    except Exception as e:
        logger.exception('Failed to sync all folders to Drive')
        return safe_error_response(e)
