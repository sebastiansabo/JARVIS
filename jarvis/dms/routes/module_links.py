"""DMS Module Link routes — universal cross-module linking."""
import logging
from flask import request, jsonify
from flask_login import login_required, current_user

from dms import dms_bp
from dms.repositories import ModuleLinkRepository, AuditRepository
from core.utils.api_helpers import safe_error_response, v2_permission_required

logger = logging.getLogger('jarvis.dms.routes.module_links')

_link_repo = ModuleLinkRepository()
_audit_repo = AuditRepository()

ALLOWED_MODULES = (
    'invoice', 'marketing', 'crm_deal', 'crm_client',
    'hr_event', 'approval', 'statement', 'efactura'
)


def dms_permission_required(entity, action):
    return v2_permission_required('dms', entity, action)


# ── Folder links ──

@dms_bp.route('/api/dms/folders/<int:folder_id>/links', methods=['GET'])
@login_required
@dms_permission_required('folder', 'view')
def api_get_folder_links(folder_id):
    """Get all module links for a folder."""
    try:
        links = _link_repo.get_folder_links(folder_id)
        return jsonify({'success': True, 'links': links})
    except Exception as e:
        logger.exception('Failed to get folder links')
        return safe_error_response(e)


@dms_bp.route('/api/dms/folders/<int:folder_id>/links', methods=['POST'])
@login_required
@dms_permission_required('folder', 'edit')
def api_link_folder(folder_id):
    """Link a folder to a module entity."""
    try:
        data = request.get_json()
        module = data.get('module')
        module_entity_id = data.get('module_entity_id')

        if not module or module not in ALLOWED_MODULES:
            return jsonify({'success': False,
                            'error': f'Invalid module. Allowed: {", ".join(ALLOWED_MODULES)}'}), 400
        if not module_entity_id:
            return jsonify({'success': False, 'error': 'module_entity_id is required'}), 400

        link = _link_repo.link_folder(
            folder_id, module, module_entity_id, current_user.id)

        if link:
            _audit_repo.log('folder', folder_id, 'linked',
                            current_user.id, current_user.company_id,
                            changes={'module': module, 'module_entity_id': module_entity_id},
                            ip_address=request.remote_addr)

        return jsonify({'success': True, 'link': link})
    except Exception as e:
        logger.exception('Failed to link folder')
        return safe_error_response(e)


@dms_bp.route('/api/dms/folders/<int:folder_id>/links/<module>/<int:entity_id>', methods=['DELETE'])
@login_required
@dms_permission_required('folder', 'edit')
def api_unlink_folder(folder_id, module, entity_id):
    """Remove a folder-module link."""
    try:
        _link_repo.unlink_folder(folder_id, module, entity_id)

        _audit_repo.log('folder', folder_id, 'unlinked',
                        current_user.id, current_user.company_id,
                        changes={'module': module, 'module_entity_id': entity_id},
                        ip_address=request.remote_addr)

        return jsonify({'success': True})
    except Exception as e:
        logger.exception('Failed to unlink folder')
        return safe_error_response(e)


# ── Reverse lookup ──

@dms_bp.route('/api/dms/module-links/<module>/<int:entity_id>', methods=['GET'])
@login_required
def api_get_module_links(module, entity_id):
    """Get all DMS links (folders + documents) for a module entity."""
    try:
        if module not in ALLOWED_MODULES:
            return jsonify({'success': False, 'error': 'Invalid module'}), 400

        links = _link_repo.get_by_module(module, entity_id)
        return jsonify({'success': True, 'links': links})
    except Exception as e:
        logger.exception('Failed to get module links')
        return safe_error_response(e)


# ── Search folders for linking ──

@dms_bp.route('/api/dms/folders/search', methods=['GET'])
@login_required
@dms_permission_required('folder', 'view')
def api_search_folders():
    """Search folders for linking picker."""
    try:
        query = request.args.get('q', '')
        if len(query) < 2:
            return jsonify({'success': True, 'folders': []})

        folders = _link_repo.search_folders(
            query, current_user.company_id, limit=20)
        return jsonify({'success': True, 'folders': folders})
    except Exception as e:
        logger.exception('Failed to search folders')
        return safe_error_response(e)
