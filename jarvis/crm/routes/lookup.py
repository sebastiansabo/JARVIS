from ._shared import *


# ════════════════════════════════════════════════════════════════
# Lookup / Reference data
# ════════════════════════════════════════════════════════════════

@crm_bp.route('/api/crm/clients/cities', methods=['GET'])
@login_required
@crm_required
def api_client_cities():
    cities = _client_repo.get_cities()
    return jsonify({'cities': [c['city'] for c in cities]})


@crm_bp.route('/api/crm/clients/responsibles', methods=['GET'])
@login_required
@crm_required
def api_client_responsibles():
    responsibles = _client_repo.get_responsibles()
    return jsonify({'responsibles': [r['responsible'] for r in responsibles]})


@crm_bp.route('/api/crm/clients/detailed-stats', methods=['GET'])
@login_required
@crm_required
def api_client_detailed_stats():
    return jsonify(_client_repo.get_detailed_stats())


@crm_bp.route('/api/crm/deals/brands', methods=['GET'])
@login_required
@crm_required
def api_deal_brands():
    brands = _deal_repo.get_brands()
    return jsonify({'brands': [b['brand'] for b in brands]})


@crm_bp.route('/api/crm/deals/dealers', methods=['GET'])
@login_required
@crm_required
def api_deal_dealers():
    return jsonify({'dealers': _deal_repo.get_dealers()})


@crm_bp.route('/api/crm/deals/sales-persons', methods=['GET'])
@login_required
@crm_required
def api_deal_sales_persons():
    return jsonify({'sales_persons': _deal_repo.get_sales_persons()})


@crm_bp.route('/api/crm/deals/statuses', methods=['GET'])
@login_required
@crm_required
def api_deal_statuses():
    statuses = _deal_repo.get_statuses()
    return jsonify({'statuses': statuses})


@crm_bp.route('/api/crm/deals/order-statuses', methods=['GET'])
@login_required
@crm_required
def api_deal_order_statuses():
    return jsonify({'statuses': _deal_repo.get_order_statuses()})


@crm_bp.route('/api/crm/deals/contract-statuses', methods=['GET'])
@login_required
@crm_required
def api_deal_contract_statuses():
    return jsonify({'statuses': _deal_repo.get_contract_statuses()})
