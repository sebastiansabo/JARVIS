from ._shared import *


# ════════════════════════════════════════════════════════════════
# Stats
# ════════════════════════════════════════════════════════════════

@crm_bp.route('/api/crm/stats', methods=['GET'])
@login_required
@crm_required
def api_stats():
    client_stats = _client_repo.get_stats()
    deal_stats = _deal_repo.get_stats()
    last_imports = {}
    for st in ('nw', 'gw', 'crm_clients', 'clienti'):
        last = _import_repo.get_last_import(st)
        last_imports[st] = last
    return jsonify({
        'clients': client_stats,
        'deals': deal_stats,
        'last_imports': last_imports,
    })


# ════════════════════════════════════════════════════════════════
# Deals
# ════════════════════════════════════════════════════════════════

@crm_bp.route('/api/crm/deals', methods=['GET'])
@login_required
@crm_required
def api_deals():
    rows, total = _deal_repo.search(
        source=request.args.get('source'),
        brand=request.args.get('brand'),
        model=request.args.get('model'),
        buyer=request.args.get('buyer'),
        vin=request.args.get('vin'),
        status=request.args.get('status'),
        dealer=request.args.get('dealer'),
        sales_person=request.args.get('sales_person'),
        date_from=request.args.get('date_from'),
        date_to=request.args.get('date_to'),
        sort_by=request.args.get('sort_by'),
        sort_order=request.args.get('sort_order'),
        limit=request.args.get('limit', 50, type=int),
        offset=request.args.get('offset', 0, type=int),
    )
    return jsonify({'deals': rows, 'total': total})


@crm_bp.route('/api/crm/deals/export', methods=['GET'])
@login_required
@crm_required
def api_deals_export():
    if not getattr(current_user, 'can_export_crm', False):
        return jsonify({'success': False, 'error': 'Export permission denied'}), 403
    rows, _ = _deal_repo.search(
        source=request.args.get('source'), brand=request.args.get('brand'),
        model=request.args.get('model'), buyer=request.args.get('buyer'),
        vin=request.args.get('vin'), status=request.args.get('status'),
        dealer=request.args.get('dealer'), sales_person=request.args.get('sales_person'),
        date_from=request.args.get('date_from'), date_to=request.args.get('date_to'),
        sort_by=request.args.get('sort_by'), sort_order=request.args.get('sort_order'),
        limit=50000, offset=0,
    )
    return _csv_response(rows, 'deals.csv', [
        'id', 'source', 'dossier_number', 'brand', 'model_name', 'buyer_name',
        'dossier_status', 'sale_price_net', 'contract_date', 'vin', 'dealer_name',
        'branch', 'sales_person', 'fuel_type', 'color', 'model_year',
    ])


@crm_bp.route('/api/crm/deals/<int:deal_id>', methods=['GET'])
@login_required
@crm_required
def api_deal_detail(deal_id):
    deal = _deal_repo.get_by_id(deal_id)
    if not deal:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return jsonify({'deal': deal})


@crm_bp.route('/api/crm/deals/<int:deal_id>', methods=['PUT'])
@login_required
@crm_required
def api_deal_update(deal_id):
    if not getattr(current_user, 'can_edit_crm', False):
        return jsonify({'success': False, 'error': 'Edit permission denied'}), 403
    data = request.get_json(silent=True) or {}
    result = _deal_repo.update(deal_id, data)
    if not result:
        return jsonify({'success': False, 'error': 'Not found or no editable fields'}), 404
    return jsonify({'success': True, 'deal': result})


@crm_bp.route('/api/crm/deals/<int:deal_id>', methods=['DELETE'])
@login_required
@crm_required
def api_deal_delete(deal_id):
    if not getattr(current_user, 'can_delete_crm', False):
        return jsonify({'success': False, 'error': 'Delete permission denied'}), 403
    if _deal_repo.delete(deal_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Not found'}), 404


@crm_bp.route('/api/crm/deals/detailed-stats', methods=['GET'])
@login_required
@crm_required
def api_deal_detailed_stats():
    def _split(key):
        v = request.args.get(key)
        return [x for x in v.split(',') if x] if v else None
    return jsonify(_deal_repo.get_detailed_stats(
        dealers=_split('dealers'),
        brands=_split('brands'),
        statuses=_split('statuses'),
        date_from=request.args.get('date_from'),
        date_to=request.args.get('date_to'),
    ))
