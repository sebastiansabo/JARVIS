"""DMS document party routes."""
import logging
from flask import request, jsonify
from flask_login import login_required, current_user

from dms import dms_bp
from dms.repositories import DocumentRepository, PartyRepository, PartyRoleRepository
from dms.routes.documents import dms_permission_required
from core.utils.api_helpers import safe_error_response, get_json_or_error

logger = logging.getLogger('jarvis.dms.routes.parties')

_doc_repo = DocumentRepository()
_party_repo = PartyRepository()
_party_role_repo = PartyRoleRepository()

_VALID_ENTITY_TYPES = ('company', 'person', 'external')


def _valid_roles():
    """Get active party role slugs from the database."""
    return [r['slug'] for r in _party_role_repo.list_all(active_only=True)]


def _check_doc_access(doc_id):
    """Check document exists and user has access. Returns (doc, error_response)."""
    doc = _doc_repo.get_by_id(doc_id)
    if not doc:
        return None, (jsonify({'success': False, 'error': 'Document not found'}), 404)
    user_company = getattr(current_user, 'company_id', None)
    if user_company and doc['company_id'] != user_company:
        return None, (jsonify({'success': False, 'error': 'Document not found'}), 404)
    return doc, None


@dms_bp.route('/api/documents/<int:doc_id>/parties', methods=['GET'])
@login_required
@dms_permission_required('document', 'view')
def api_list_parties(doc_id):
    """List parties for a document."""
    doc, err = _check_doc_access(doc_id)
    if err:
        return err
    parties = _party_repo.get_by_document(doc_id)
    return jsonify({'success': True, 'parties': parties})


@dms_bp.route('/api/documents/<int:doc_id>/parties', methods=['POST'])
@login_required
@dms_permission_required('document', 'edit')
def api_create_party(doc_id):
    """Add a party to a document."""
    doc, err = _check_doc_access(doc_id)
    if err:
        return err

    data, error = get_json_or_error()
    if error:
        return error

    party_role = data.get('party_role', '').strip()
    valid_roles = _valid_roles()
    if not party_role or party_role not in valid_roles:
        return jsonify({'success': False, 'error': f'Invalid party_role. Must be one of: {", ".join(valid_roles)}'}), 400

    entity_name = data.get('entity_name', '').strip()
    if not entity_name:
        return jsonify({'success': False, 'error': 'entity_name is required'}), 400
    if len(entity_name) > 200:
        return jsonify({'success': False, 'error': 'entity_name too long (max 200)'}), 400

    entity_type = data.get('entity_type', 'company')
    if entity_type not in _VALID_ENTITY_TYPES:
        return jsonify({'success': False, 'error': f'Invalid entity_type. Must be one of: {", ".join(_VALID_ENTITY_TYPES)}'}), 400

    entity_id = data.get('entity_id')
    if entity_id is not None and not isinstance(entity_id, int):
        return jsonify({'success': False, 'error': 'entity_id must be an integer or null'}), 400

    entity_details = data.get('entity_details', {})
    if not isinstance(entity_details, dict):
        return jsonify({'success': False, 'error': 'entity_details must be an object'}), 400

    sort_order = data.get('sort_order', 0)
    if not isinstance(sort_order, int) or sort_order < 0 or sort_order > 999:
        return jsonify({'success': False, 'error': 'sort_order must be 0-999'}), 400

    try:
        row = _party_repo.create(
            document_id=doc_id,
            party_role=party_role,
            entity_name=entity_name,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_details=entity_details,
            sort_order=sort_order,
        )
        return jsonify({'success': True, 'id': row['id']}), 201
    except Exception as e:
        return safe_error_response(e)


@dms_bp.route('/api/dms/parties/<int:party_id>', methods=['PUT'])
@login_required
@dms_permission_required('document', 'edit')
def api_update_party(party_id):
    """Update a party."""
    party = _party_repo.get_by_id(party_id)
    if not party:
        return jsonify({'success': False, 'error': 'Party not found'}), 404

    doc, err = _check_doc_access(party['document_id'])
    if err:
        return err

    data, error = get_json_or_error()
    if error:
        return error

    fields = {}
    if 'party_role' in data:
        if data['party_role'] not in _valid_roles():
            return jsonify({'success': False, 'error': 'Invalid party_role'}), 400
        fields['party_role'] = data['party_role']
    if 'entity_name' in data:
        name = data['entity_name'].strip()
        if not name or len(name) > 200:
            return jsonify({'success': False, 'error': 'Invalid entity_name'}), 400
        fields['entity_name'] = name
    if 'entity_type' in data:
        if data['entity_type'] not in _VALID_ENTITY_TYPES:
            return jsonify({'success': False, 'error': 'Invalid entity_type'}), 400
        fields['entity_type'] = data['entity_type']
    if 'entity_id' in data:
        eid = data['entity_id']
        if eid is not None and not isinstance(eid, int):
            return jsonify({'success': False, 'error': 'entity_id must be an integer or null'}), 400
        fields['entity_id'] = eid
    if 'entity_details' in data:
        ed = data['entity_details']
        if ed is not None and not isinstance(ed, dict):
            return jsonify({'success': False, 'error': 'entity_details must be an object or null'}), 400
        fields['entity_details'] = ed
    if 'sort_order' in data:
        so = data['sort_order']
        if not isinstance(so, int) or so < 0 or so > 999:
            return jsonify({'success': False, 'error': 'sort_order must be 0-999'}), 400
        fields['sort_order'] = so

    try:
        _party_repo.update(party_id, **fields)
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@dms_bp.route('/api/dms/parties/<int:party_id>', methods=['DELETE'])
@login_required
@dms_permission_required('document', 'edit')
def api_delete_party(party_id):
    """Remove a party."""
    party = _party_repo.get_by_id(party_id)
    if not party:
        return jsonify({'success': False, 'error': 'Party not found'}), 404

    doc, err = _check_doc_access(party['document_id'])
    if err:
        return err

    _party_repo.delete(party_id)
    return jsonify({'success': True})


@dms_bp.route('/api/dms/parties/suggest', methods=['GET'])
@login_required
@dms_permission_required('document', 'view')
def api_suggest_parties():
    """Auto-suggest parties from companies and users."""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify({'success': True, 'suggestions': []})
    company_id = getattr(current_user, 'company_id', None)
    suggestions = _party_repo.suggest(q, company_id=company_id, limit=10)
    return jsonify({'success': True, 'suggestions': suggestions})
