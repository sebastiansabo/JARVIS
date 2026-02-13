"""Tag system routes.

Tag groups, tags, and entity tag management.
"""
from flask import jsonify, request
from flask_login import login_required, current_user

from . import tags_bp
from .repositories import TagRepository, AutoTagRepository
from .auto_tag_service import AutoTagService, ENTITY_FIELDS

_tag_repo = TagRepository()
_auto_tag_repo = AutoTagRepository()
_auto_tag_service = AutoTagService()

VALID_ENTITY_TYPES = {'invoice', 'efactura_invoice', 'transaction', 'employee', 'event', 'event_bonus'}


# ============== TAG GROUP ENDPOINTS ==============

@tags_bp.route('/api/tag-groups', methods=['GET'])
@login_required
def api_get_tag_groups():
    active_only = request.args.get('active_only', 'true').lower() != 'false'
    groups = _tag_repo.get_groups(active_only=active_only)
    return jsonify(groups)


@tags_bp.route('/api/tag-groups', methods=['POST'])
@login_required
def api_create_tag_group():
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name is required'}), 400
    try:
        group_id = _tag_repo.save_group(
            name=name,
            description=data.get('description'),
            color=data.get('color', '#6c757d'),
            sort_order=data.get('sort_order', 0)
        )
        return jsonify({'success': True, 'id': group_id})
    except Exception as e:
        if 'idx_tag_groups_name_unique' in str(e):
            return jsonify({'success': False, 'error': f'A group named "{name}" already exists'}), 409
        return jsonify({'success': False, 'error': str(e)}), 500


@tags_bp.route('/api/tag-groups/<int:group_id>', methods=['PUT'])
@login_required
def api_update_tag_group(group_id):
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    data = request.get_json()
    try:
        updated = _tag_repo.update_group(group_id, **{k: v for k, v in data.items() if k in ('name', 'description', 'color', 'sort_order', 'is_active')})
        if updated:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Group not found'}), 404
    except Exception as e:
        if 'idx_tag_groups_name_unique' in str(e):
            return jsonify({'success': False, 'error': f'A group with that name already exists'}), 409
        return jsonify({'success': False, 'error': str(e)}), 500


@tags_bp.route('/api/tag-groups/<int:group_id>', methods=['DELETE'])
@login_required
def api_delete_tag_group(group_id):
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    if _tag_repo.delete_group(group_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Group not found'}), 404


# ============== TAG ENDPOINTS ==============

@tags_bp.route('/api/tags', methods=['GET'])
@login_required
def api_get_tags():
    group_id = request.args.get('group_id', type=int)
    tags = _tag_repo.get_tags(current_user.id, group_id=group_id)
    return jsonify(tags)


@tags_bp.route('/api/tags', methods=['POST'])
@login_required
def api_create_tag():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name is required'}), 400
    is_global = data.get('is_global', False)
    if is_global and not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Only admins can create global tags'}), 403
    try:
        tag_id = _tag_repo.save_tag(
            name=name,
            is_global=is_global,
            created_by=current_user.id,
            group_id=data.get('group_id'),
            color=data.get('color', '#0d6efd'),
            icon=data.get('icon'),
            sort_order=data.get('sort_order', 0)
        )
        return jsonify({'success': True, 'id': tag_id})
    except Exception as e:
        if 'idx_tags_global_name_unique' in str(e) or 'idx_tags_user_name_unique' in str(e):
            return jsonify({'success': False, 'error': f'A tag named "{name}" already exists'}), 409
        return jsonify({'success': False, 'error': str(e)}), 500


@tags_bp.route('/api/tags/<int:tag_id>', methods=['PUT'])
@login_required
def api_update_tag(tag_id):
    tag = _tag_repo.get_tag(tag_id)
    if not tag:
        return jsonify({'success': False, 'error': 'Tag not found'}), 404
    if tag['is_global'] and not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Only admins can edit global tags'}), 403
    if not tag['is_global'] and tag['created_by'] != current_user.id:
        return jsonify({'success': False, 'error': 'Not your tag'}), 403
    data = request.get_json()
    try:
        updated = _tag_repo.update_tag(tag_id, **{k: v for k, v in data.items() if k in ('name', 'group_id', 'color', 'icon', 'sort_order', 'is_active')})
        if updated:
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'No changes'}), 400
    except Exception as e:
        if 'idx_tags_global_name_unique' in str(e) or 'idx_tags_user_name_unique' in str(e):
            return jsonify({'success': False, 'error': 'A tag with that name already exists'}), 409
        return jsonify({'success': False, 'error': str(e)}), 500


@tags_bp.route('/api/tags/<int:tag_id>', methods=['DELETE'])
@login_required
def api_delete_tag(tag_id):
    tag = _tag_repo.get_tag(tag_id)
    if not tag:
        return jsonify({'success': False, 'error': 'Tag not found'}), 404
    if tag['is_global'] and not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Only admins can delete global tags'}), 403
    if not tag['is_global'] and tag['created_by'] != current_user.id:
        return jsonify({'success': False, 'error': 'Not your tag'}), 403
    if _tag_repo.delete_tag(tag_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Tag not found'}), 404


# ============== ENTITY TAG ENDPOINTS ==============

@tags_bp.route('/api/entity-tags', methods=['GET'])
@login_required
def api_get_entity_tags():
    entity_type = request.args.get('entity_type', '')
    if entity_type not in VALID_ENTITY_TYPES:
        return jsonify({'error': f'Invalid entity_type. Must be one of: {", ".join(sorted(VALID_ENTITY_TYPES))}'}), 400
    entity_id = request.args.get('entity_id', type=int)
    if not entity_id:
        return jsonify({'error': 'entity_id is required'}), 400
    tags = _tag_repo.get_entity_tags(entity_type, entity_id, current_user.id)
    return jsonify(tags)


@tags_bp.route('/api/entity-tags/bulk', methods=['GET'])
@login_required
def api_get_entity_tags_bulk():
    entity_type = request.args.get('entity_type', '')
    if entity_type not in VALID_ENTITY_TYPES:
        return jsonify({'error': f'Invalid entity_type'}), 400
    ids_str = request.args.get('entity_ids', '')
    entity_ids = [int(x) for x in ids_str.split(',') if x.strip()] if ids_str else []
    if not entity_ids:
        return jsonify({})
    tags_map = _tag_repo.get_entities_tags_bulk(entity_type, entity_ids, current_user.id)
    return jsonify({str(k): v for k, v in tags_map.items()})


@tags_bp.route('/api/entity-tags', methods=['POST'])
@login_required
def api_add_entity_tag():
    data = request.get_json()
    entity_type = data.get('entity_type', '')
    if entity_type not in VALID_ENTITY_TYPES:
        return jsonify({'success': False, 'error': 'Invalid entity_type'}), 400
    tag_id = data.get('tag_id')
    entity_id = data.get('entity_id')
    if not tag_id or not entity_id:
        return jsonify({'success': False, 'error': 'tag_id and entity_id are required'}), 400
    tag = _tag_repo.get_tag(tag_id)
    if not tag or (not tag['is_global'] and tag['created_by'] != current_user.id):
        return jsonify({'success': False, 'error': 'Tag not found'}), 404
    added = _tag_repo.add_entity_tag(tag_id, entity_type, entity_id, current_user.id)
    return jsonify({'success': True, 'added': added})


@tags_bp.route('/api/entity-tags', methods=['DELETE'])
@login_required
def api_remove_entity_tag():
    data = request.get_json()
    entity_type = data.get('entity_type', '')
    if entity_type not in VALID_ENTITY_TYPES:
        return jsonify({'success': False, 'error': 'Invalid entity_type'}), 400
    tag_id = data.get('tag_id')
    entity_id = data.get('entity_id')
    if not tag_id or not entity_id:
        return jsonify({'success': False, 'error': 'tag_id and entity_id are required'}), 400
    removed = _tag_repo.remove_entity_tag(tag_id, entity_type, entity_id)
    return jsonify({'success': True, 'removed': removed})


@tags_bp.route('/api/entity-tags/bulk', methods=['POST'])
@login_required
def api_bulk_entity_tags():
    data = request.get_json()
    entity_type = data.get('entity_type', '')
    if entity_type not in VALID_ENTITY_TYPES:
        return jsonify({'success': False, 'error': 'Invalid entity_type'}), 400
    tag_id = data.get('tag_id')
    entity_ids = data.get('entity_ids', [])
    action = data.get('action', 'add')
    if not tag_id or not entity_ids:
        return jsonify({'success': False, 'error': 'tag_id and entity_ids are required'}), 400
    if action == 'remove':
        count = _tag_repo.bulk_remove_entity_tags(tag_id, entity_type, entity_ids)
    else:
        tag = _tag_repo.get_tag(tag_id)
        if not tag or (not tag['is_global'] and tag['created_by'] != current_user.id):
            return jsonify({'success': False, 'error': 'Tag not found'}), 404
        count = _tag_repo.bulk_add_entity_tags(tag_id, entity_type, entity_ids, current_user.id)
    return jsonify({'success': True, 'count': count})


# ============== AUTO-TAG RULE ENDPOINTS ==============

@tags_bp.route('/api/auto-tag-rules', methods=['GET'])
@login_required
def api_get_auto_tag_rules():
    entity_type = request.args.get('entity_type')
    rules = _auto_tag_repo.get_rules(entity_type=entity_type, active_only=False)
    return jsonify(rules)


@tags_bp.route('/api/auto-tag-rules', methods=['POST'])
@login_required
def api_create_auto_tag_rule():
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    data = request.get_json()
    name = (data.get('name') or '').strip()
    entity_type = data.get('entity_type', '')
    tag_id = data.get('tag_id')
    conditions = data.get('conditions', [])
    if not name:
        return jsonify({'success': False, 'error': 'Name is required'}), 400
    if entity_type not in VALID_ENTITY_TYPES:
        return jsonify({'success': False, 'error': 'Invalid entity_type'}), 400
    if not tag_id:
        return jsonify({'success': False, 'error': 'tag_id is required'}), 400
    rule_id = _auto_tag_repo.create_rule(
        name=name,
        entity_type=entity_type,
        tag_id=tag_id,
        conditions=conditions,
        run_on_create=data.get('run_on_create', True),
        created_by=current_user.id,
    )
    return jsonify({'success': True, 'id': rule_id})


@tags_bp.route('/api/auto-tag-rules/<int:rule_id>', methods=['PUT'])
@login_required
def api_update_auto_tag_rule(rule_id):
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    data = request.get_json()
    allowed = {k: v for k, v in data.items()
               if k in ('name', 'entity_type', 'tag_id', 'conditions', 'is_active', 'run_on_create')}
    if not allowed:
        return jsonify({'success': False, 'error': 'No valid fields'}), 400
    updated = _auto_tag_repo.update_rule(rule_id, **allowed)
    if updated:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Rule not found'}), 404


@tags_bp.route('/api/auto-tag-rules/<int:rule_id>', methods=['DELETE'])
@login_required
def api_delete_auto_tag_rule(rule_id):
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    if _auto_tag_repo.delete_rule(rule_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Rule not found'}), 404


@tags_bp.route('/api/auto-tag-rules/<int:rule_id>/run', methods=['POST'])
@login_required
def api_run_auto_tag_rule(rule_id):
    if not current_user.can_access_settings:
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    result = _auto_tag_service.run_rule(rule_id, current_user.id)
    return jsonify({'success': True, **result})


@tags_bp.route('/api/auto-tag-rules/entity-fields', methods=['GET'])
@login_required
def api_get_entity_fields():
    return jsonify(ENTITY_FIELDS)
