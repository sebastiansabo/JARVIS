"""Routes for the user-defined document-type registry (fp_document_types).

A document type is a per-company row carrying its own contract template and an
is_rental flag. GET feeds the header type selector + the vehicle "Parc / Tip
document" selector; PUT/POST manage them (admin only). Supersedes the per-brand
/contract-configs + /service-enabled endpoints."""
from ._shared import foi_parcurs_bp, jsonify, request, login_required, current_user, logger
from ..repositories.document_type_repository import DocumentTypeRepository

_dt_repo = DocumentTypeRepository()


def _is_admin():
    return getattr(current_user, 'role_name', '').lower() in ('admin', 'superadmin')


@foi_parcurs_bp.route('/api/foi-parcurs/document-types', methods=['GET'])
@login_required
def api_list_document_types():
    """Document types for a company. Active-only by default (selectors);
    `?include_inactive=1` returns all (Settings management view)."""
    company_id = request.args.get('company_id', type=int)
    include_inactive = request.args.get('include_inactive') in ('1', 'true', 'True')
    types = _dt_repo.list_for_company(company_id, active_only=not include_inactive) if company_id else []
    return jsonify({'success': True, 'types': types})


@foi_parcurs_bp.route('/api/foi-parcurs/document-types', methods=['POST'])
@login_required
def api_add_document_type():
    """Add a new document type for a company (label ⇒ slug key). Admin only."""
    if not _is_admin():
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    data = request.get_json(silent=True) or {}
    company_id = data.get('company_id')
    try:
        key = _dt_repo.add(company_id, data.get('label'), is_rental=bool(data.get('is_rental', False)))
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    logger.info('document-type added company=%s key=%s by %s',
                company_id, key, getattr(current_user, 'email', '?'))
    return jsonify({'success': True, 'key': key})


@foi_parcurs_bp.route('/api/foi-parcurs/document-types', methods=['PUT'])
@login_required
def api_put_document_type():
    """Upsert a document type's label/template/flags. Admin only. The default
    (sales) row is immutable and returns 400."""
    if not _is_admin():
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    data = request.get_json(silent=True) or {}
    company_id = data.get('company_id')
    key = data.get('key')
    try:
        _dt_repo.upsert(
            company_id, key,
            data.get('label'),
            (data.get('title') or '').strip() or None,
            (data.get('body_template') or '').strip() or None,
            (data.get('general_conditions') or '').strip() or None,
            is_rental=bool(data.get('is_rental', False)),
            is_active=bool(data.get('is_active', True)),
        )
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    logger.info('document-type upserted company=%s key=%s by %s',
                company_id, key, getattr(current_user, 'email', '?'))
    return jsonify({'success': True})


@foi_parcurs_bp.route('/api/foi-parcurs/document-types', methods=['DELETE'])
@login_required
def api_delete_document_type():
    """Delete a document type. Admin only; the default (sales) and in-use types
    are refused (400 with a message)."""
    if not _is_admin():
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    data = request.get_json(silent=True) or {}
    try:
        _dt_repo.delete(data.get('company_id'), data.get('key'))
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    logger.info('document-type deleted company=%s key=%s by %s',
                data.get('company_id'), data.get('key'), getattr(current_user, 'email', '?'))
    return jsonify({'success': True})
