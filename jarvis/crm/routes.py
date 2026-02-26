"""CRM API routes — import, search, stats, detail, CRUD, export endpoints."""

import io
import csv
import os
import tempfile
import logging
from functools import wraps
from flask import jsonify, request, Response, send_file
from flask_login import login_required, current_user

from . import crm_bp
from .repositories import ClientRepository, DealRepository, ImportRepository
from .services.import_service import IMPORT_HANDLERS

logger = logging.getLogger('jarvis.crm.routes')

_client_repo = ClientRepository()
_deal_repo = DealRepository()
_import_repo = ImportRepository()


def crm_required(f):
    """Require can_access_crm permission."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        if not getattr(current_user, 'can_access_crm', False):
            return jsonify({'success': False, 'error': 'CRM access denied'}), 403
        return f(*args, **kwargs)
    return decorated


# ════════════════════════════════════════════════════════════════
# Import
# ════════════════════════════════════════════════════════════════

@crm_bp.route('/api/crm/import', methods=['POST'])
@login_required
@crm_required
def api_import():
    """Upload and import an Excel/CSV file.
    Form data: file (multipart), source_type (deals|clients|nw|gw|crm_clients)
    """
    source_type = request.form.get('source_type')
    if source_type not in IMPORT_HANDLERS:
        return jsonify({'success': False,
                        'error': f'Invalid source_type. Use: {", ".join(IMPORT_HANDLERS.keys())}'}), 400

    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ('.xlsx', '.xls', '.csv'):
        return jsonify({'success': False, 'error': 'Only .xlsx, .xls, .csv files supported'}), 400

    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        file.save(tmp)
        tmp_path = tmp.name

    try:
        handler = IMPORT_HANDLERS[source_type]
        stats = handler(tmp_path, current_user.id)
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        logger.exception(f'Import failed: {e}')
        return jsonify({'success': False, 'error': str(e)[:500]}), 500
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@crm_bp.route('/api/crm/import/template', methods=['GET'])
@login_required
@crm_required
def api_import_template():
    """Download the Samsaru import template (.xlsx)."""
    template_path = os.path.join(os.path.dirname(__file__), '..', '..', 'docs', 'import-templates', 'Samsaru_Import_Template.xlsx')
    template_path = os.path.abspath(template_path)
    if not os.path.exists(template_path):
        return jsonify({'success': False, 'error': 'Template file not found'}), 404
    return send_file(template_path, as_attachment=True, download_name='Samsaru_Import_Template.xlsx')


@crm_bp.route('/api/crm/import/batches', methods=['GET'])
@login_required
@crm_required
def api_import_batches():
    source_type = request.args.get('source_type')
    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', 0, type=int)
    batches = _import_repo.list_batches(source_type, limit, offset)
    return jsonify({'batches': batches})


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
    for st in ('nw', 'gw', 'crm_clients'):
        last = _import_repo.get_last_import(st)
        last_imports[st] = last
    return jsonify({
        'clients': client_stats,
        'deals': deal_stats,
        'last_imports': last_imports,
    })


# ════════════════════════════════════════════════════════════════
# Clients
# ════════════════════════════════════════════════════════════════

@crm_bp.route('/api/crm/clients', methods=['GET'])
@login_required
@crm_required
def api_clients():
    rows, total = _client_repo.search(
        name=request.args.get('name'),
        phone=request.args.get('phone'),
        email=request.args.get('email'),
        client_type=request.args.get('client_type'),
        responsible=request.args.get('responsible'),
        city=request.args.get('city'),
        date_from=request.args.get('date_from'),
        date_to=request.args.get('date_to'),
        sort_by=request.args.get('sort_by'),
        sort_order=request.args.get('sort_order'),
        show_blacklisted=request.args.get('show_blacklisted'),
        limit=request.args.get('limit', 50, type=int),
        offset=request.args.get('offset', 0, type=int),
    )
    return jsonify({'clients': rows, 'total': total})


@crm_bp.route('/api/crm/clients/export', methods=['GET'])
@login_required
@crm_required
def api_clients_export():
    if not getattr(current_user, 'can_export_crm', False):
        return jsonify({'success': False, 'error': 'Export permission denied'}), 403
    rows, _ = _client_repo.search(
        name=request.args.get('name'), phone=request.args.get('phone'),
        email=request.args.get('email'), client_type=request.args.get('client_type'),
        responsible=request.args.get('responsible'), city=request.args.get('city'),
        date_from=request.args.get('date_from'), date_to=request.args.get('date_to'),
        show_blacklisted=request.args.get('show_blacklisted'),
        limit=50000, offset=0,
    )
    return _csv_response(rows, 'clients.csv', [
        'id', 'display_name', 'client_type', 'phone', 'email', 'street', 'city',
        'region', 'company_name', 'responsible', 'created_at',
    ])


@crm_bp.route('/api/crm/clients/<int:client_id>', methods=['GET'])
@login_required
@crm_required
def api_client_detail(client_id):
    client = _client_repo.get_by_id(client_id)
    if not client:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    deals, _ = _deal_repo.search(client_id=client_id, limit=100)
    return jsonify({'client': client, 'deals': deals})


@crm_bp.route('/api/crm/clients/<int:client_id>', methods=['PUT'])
@login_required
@crm_required
def api_client_update(client_id):
    if not getattr(current_user, 'can_edit_crm', False):
        return jsonify({'success': False, 'error': 'Edit permission denied'}), 403
    data = request.get_json(silent=True) or {}
    result = _client_repo.update(client_id, data)
    if not result:
        return jsonify({'success': False, 'error': 'Not found or no editable fields'}), 404
    return jsonify({'success': True, 'client': result})


@crm_bp.route('/api/crm/clients/<int:client_id>', methods=['DELETE'])
@login_required
@crm_required
def api_client_delete(client_id):
    if not getattr(current_user, 'can_delete_crm', False):
        return jsonify({'success': False, 'error': 'Delete permission denied'}), 403
    if _client_repo.delete(client_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Not found'}), 404


@crm_bp.route('/api/crm/clients/merge', methods=['POST'])
@login_required
@crm_required
def api_merge_clients():
    data = request.get_json(silent=True) or {}
    keep_id = data.get('keep_id')
    remove_id = data.get('remove_id')
    if not keep_id or not remove_id:
        return jsonify({'success': False, 'error': 'keep_id and remove_id required'}), 400
    _client_repo.merge(keep_id, remove_id)
    return jsonify({'success': True})


@crm_bp.route('/api/crm/clients/<int:client_id>/blacklist', methods=['POST'])
@login_required
@crm_required
def api_client_toggle_blacklist(client_id):
    if not getattr(current_user, 'can_edit_crm', False):
        return jsonify({'success': False, 'error': 'Edit permission denied'}), 403
    data = request.get_json(silent=True) or {}
    is_blacklisted = bool(data.get('is_blacklisted', False))
    result = _client_repo.toggle_blacklist(client_id, is_blacklisted)
    if not result:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return jsonify({'success': True, 'client': result})


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


# ════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════

def _csv_response(rows, filename, columns):
    """Stream rows as CSV download."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(c, '') for c in columns])
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'},
    )
