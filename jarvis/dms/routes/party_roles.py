"""DMS party role configuration routes."""
import re
import logging
import psycopg2
from flask import request, jsonify
from flask_login import login_required

from dms import dms_bp
from dms.repositories import PartyRoleRepository
from dms.routes.documents import dms_permission_required
from core.utils.api_helpers import safe_error_response, get_json_or_error

logger = logging.getLogger('jarvis.dms.routes.party_roles')

_repo = PartyRoleRepository()
_SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,62}[a-z0-9]$|^[a-z0-9]$')


@dms_bp.route('/api/dms/party-roles', methods=['GET'])
@login_required
@dms_permission_required('category', 'view')
def api_list_party_roles():
    """List party roles."""
    active_only = request.args.get('active_only', 'true').lower() != 'false'
    roles = _repo.list_all(active_only=active_only)
    return jsonify({'success': True, 'roles': roles})


@dms_bp.route('/api/dms/party-roles', methods=['POST'])
@login_required
@dms_permission_required('category', 'manage')
def api_create_party_role():
    """Create a new party role."""
    data, error = get_json_or_error()
    if error:
        return error

    label = data.get('label', '').strip()
    if not label:
        return jsonify({'success': False, 'error': 'Label is required'}), 400
    if len(label) > 100:
        return jsonify({'success': False, 'error': 'Label too long (max 100)'}), 400

    slug = data.get('slug', '').strip()
    if not slug:
        slug = re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-')

    if not _SLUG_RE.match(slug):
        return jsonify({'success': False, 'error': 'Invalid slug format (lowercase alphanumeric, hyphens, underscores)'}), 400

    sort_order = data.get('sort_order', 0)
    try:
        sort_order = int(sort_order)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'sort_order must be a number'}), 400

    try:
        row = _repo.create(slug=slug, label=label, sort_order=sort_order)
        return jsonify({'success': True, 'id': row['id']}), 201
    except psycopg2.IntegrityError:
        return jsonify({'success': False, 'error': f'Slug "{slug}" already exists'}), 409
    except Exception as e:
        return safe_error_response(e)


@dms_bp.route('/api/dms/party-roles/<int:role_id>', methods=['PUT'])
@login_required
@dms_permission_required('category', 'manage')
def api_update_party_role(role_id):
    """Update a party role."""
    data, error = get_json_or_error()
    if error:
        return error

    rt = _repo.get_by_id(role_id)
    if not rt:
        return jsonify({'success': False, 'error': 'Party role not found'}), 404

    if 'slug' in data:
        slug = data['slug'].strip()
        if not _SLUG_RE.match(slug):
            return jsonify({'success': False, 'error': 'Invalid slug format'}), 400
        data['slug'] = slug

    if 'sort_order' in data:
        try:
            data['sort_order'] = int(data['sort_order'])
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'sort_order must be a number'}), 400

    try:
        fields = {}
        for key in ('label', 'slug', 'sort_order', 'is_active'):
            if key in data:
                fields[key] = data[key]
        _repo.update(role_id, **fields)
        return jsonify({'success': True})
    except psycopg2.IntegrityError:
        return jsonify({'success': False, 'error': f'Slug "{data.get("slug")}" already exists'}), 409
    except Exception as e:
        return safe_error_response(e)


@dms_bp.route('/api/dms/party-roles/<int:role_id>', methods=['DELETE'])
@login_required
@dms_permission_required('category', 'manage')
def api_delete_party_role(role_id):
    """Soft-delete a party role."""
    rt = _repo.get_by_id(role_id)
    if not rt:
        return jsonify({'success': False, 'error': 'Party role not found'}), 404
    _repo.delete(role_id)
    return jsonify({'success': True})


@dms_bp.route('/api/dms/party-roles/reorder', methods=['PUT'])
@login_required
@dms_permission_required('category', 'manage')
def api_reorder_party_roles():
    """Bulk reorder party roles."""
    data, error = get_json_or_error()
    if error:
        return error

    ids = data.get('ids', [])
    if not ids or not isinstance(ids, list):
        return jsonify({'success': False, 'error': 'ids array required'}), 400

    try:
        ids = [int(i) for i in ids]
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'All ids must be integers'}), 400

    try:
        _repo.reorder(ids)
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)
