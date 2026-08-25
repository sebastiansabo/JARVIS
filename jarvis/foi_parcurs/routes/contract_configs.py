"""Routes for per-company+brand Service contract templates (fp_contract_configs).
Configuring an active Service template here is what enables the Service context
for that (company, brand)."""
from ._shared import foi_parcurs_bp, jsonify, request, login_required, current_user, logger
from ..repositories.contract_config_repository import ContractConfigRepository

_cc_repo = ContractConfigRepository()


def _is_admin():
    return getattr(current_user, 'role_name', '').lower() in ('admin', 'superadmin')


@foi_parcurs_bp.route('/api/foi-parcurs/contract-configs/<int:company_id>', methods=['GET'])
@login_required
def api_list_contract_configs(company_id):
    """Per-brand Service contract template for a company's active brands."""
    return jsonify({'success': True, 'configs': _cc_repo.list_for_company(company_id)})


@foi_parcurs_bp.route('/api/foi-parcurs/contract-configs/<int:company_id>/<int:brand_id>', methods=['PUT'])
@login_required
def api_put_contract_config(company_id, brand_id):
    """Upsert one (company, brand) Service contract template. Admin only."""
    if not _is_admin():
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    data = request.get_json(silent=True) or {}
    _cc_repo.upsert(
        company_id, brand_id,
        (data.get('title') or '').strip() or None,
        (data.get('body_template') or '').strip() or None,
        (data.get('general_conditions') or '').strip() or None,
        is_active=bool(data.get('is_active', True)),
    )
    logger.info('service contract-config upserted for company=%s brand=%s by %s',
                company_id, brand_id, getattr(current_user, 'email', '?'))
    return jsonify({'success': True})


@foi_parcurs_bp.route('/api/foi-parcurs/service-enabled', methods=['GET'])
@login_required
def api_service_enabled():
    """Which brands (if any) have an active Service contract for a company."""
    company_id = request.args.get('company_id', type=int)
    brands = _cc_repo.service_enabled(company_id) if company_id else []
    return jsonify({'success': True, 'enabled': bool(brands), 'brands': brands})
