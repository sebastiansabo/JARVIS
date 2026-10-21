"""Admin-only per-company×brand contract-template routes.

GET /api/buyback/contract-templates?company_id=<id>            -> {templates: [...]}
PUT /api/buyback/contract-templates/<brand_id>?company_id=<id> -> upsert one
    body: {document_type, title, body_template, general_conditions, is_active}

Both @login_required + admin-only (current_user.can_access_settings), mirroring
buyback/routes/settings.py. Edited by a global admin via a company switcher in
the Settings → BuyBack → Contracte zone.
"""
from flask import request, jsonify
from flask_login import login_required, current_user

from buyback import buyback_bp
from buyback.routes import _shared
from buyback.repositories.contract_template_repository import ContractTemplateRepository

_repo = ContractTemplateRepository()
_DOC_TYPES = ('purchase', 'consignment')


def _require_admin():
    if not getattr(current_user, 'can_access_settings', False):
        return jsonify({'success': False, 'error': 'Admin permission required'}), 403
    return None


def _company_id():
    try:
        return int(request.args.get('company_id'))
    except (TypeError, ValueError):
        return None


@buyback_bp.route('/contract-templates', methods=['GET'])
@login_required
def list_contract_templates():
    err = _require_admin()
    if err:
        return err
    company_id = _company_id()
    if company_id is None:
        return jsonify({'success': False, 'error': 'company_id required'}), 400
    return jsonify({'templates': _shared._serialize(_repo.list_for_company(company_id))})


@buyback_bp.route('/contract-templates/<int:brand_id>', methods=['PUT'])
@login_required
def put_contract_template(brand_id):
    err = _require_admin()
    if err:
        return err
    company_id = _company_id()
    if company_id is None:
        return jsonify({'success': False, 'error': 'company_id required'}), 400
    data = request.get_json(silent=True) or {}
    document_type = data.get('document_type')
    if document_type not in _DOC_TYPES:
        return jsonify({'success': False,
                        'error': f'document_type must be one of {_DOC_TYPES!r}'}), 400
    row = _repo.upsert(
        company_id, brand_id, document_type,
        data.get('title'), data.get('body_template'), data.get('general_conditions'),
        bool(data.get('is_active', True)), getattr(current_user, 'id', None),
    )
    return jsonify({'template': _shared._serialize(row)})
