"""User filter presets routes."""
from flask import jsonify, request
from flask_login import login_required, current_user

from . import presets_bp
from .repositories import PresetRepository
from core.utils.api_helpers import safe_error_response

_preset_repo = PresetRepository()


@presets_bp.route('/api/presets', methods=['GET'])
@login_required
def api_get_presets():
    """Get all filter presets for the current user on a specific page."""
    page_key = request.args.get('page')
    if not page_key:
        return jsonify({'error': 'page parameter is required'}), 400
    presets = _preset_repo.get_presets(current_user.id, page_key)
    return jsonify(presets)


@presets_bp.route('/api/presets', methods=['POST'])
@login_required
def api_create_preset():
    """Create a new filter preset."""
    data = request.get_json()
    page_key = (data.get('page_key') or '').strip()
    name = (data.get('name') or '').strip()
    preset_data = data.get('preset_data', {})
    is_default = data.get('is_default', False)

    if not page_key or not name:
        return jsonify({'success': False, 'error': 'page_key and name are required'}), 400
    if len(name) > 100:
        return jsonify({'success': False, 'error': 'Name must be 100 characters or less'}), 400

    try:
        preset_id = _preset_repo.save(current_user.id, page_key, name, preset_data, is_default)
        return jsonify({'success': True, 'id': preset_id})
    except Exception as e:
        if 'idx_user_filter_presets_unique_name' in str(e):
            return jsonify({'success': False, 'error': f'A preset named "{name}" already exists'}), 409
        return safe_error_response(e)


@presets_bp.route('/api/presets/<int:preset_id>', methods=['PUT'])
@login_required
def api_update_preset(preset_id):
    """Update an existing preset (name, data, or default status)."""
    data = request.get_json()
    try:
        updated = _preset_repo.update(
            preset_id=preset_id,
            user_id=current_user.id,
            name=data.get('name'),
            preset_data=data.get('preset_data'),
            is_default=data.get('is_default')
        )
        if updated:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Preset not found'}), 404
    except Exception as e:
        if 'idx_user_filter_presets_unique_name' in str(e):
            return jsonify({'success': False, 'error': 'A preset with that name already exists'}), 409
        return safe_error_response(e)


@presets_bp.route('/api/presets/<int:preset_id>', methods=['DELETE'])
@login_required
def api_delete_preset(preset_id):
    """Delete a preset."""
    if _preset_repo.delete(preset_id, current_user.id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Preset not found'}), 404
