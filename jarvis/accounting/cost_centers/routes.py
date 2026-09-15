from functools import wraps
from flask import request, jsonify
from flask_login import current_user

from core.utils.api_helpers import safe_error_response
from accounting.cost_centers import cost_centers_bp
from accounting.cost_centers.repositories.cost_center_repository import CostCenterRepository

_repo = CostCenterRepository()


def _accounting_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'success': False, 'error': 'Autentificare necesară'}), 401
        if getattr(current_user, 'can_access_accounting', False) or \
           getattr(current_user, 'can_access_settings', False):
            return f(*args, **kwargs)
        return jsonify({'success': False, 'error': 'Acces interzis: sunt necesare permisiuni de contabilitate'}), 403
    return decorated


def _is_duplicate(e):
    s = str(e).lower()
    return 'unique' in s or 'duplicate' in s


@cost_centers_bp.route('/api/cost-centers/companies', methods=['GET'])
@_accounting_required
def api_cc_companies():
    try:
        return jsonify({'success': True, 'data': _repo.list_companies()})
    except Exception as e:
        return safe_error_response(e)


@cost_centers_bp.route('/api/cost-centers', methods=['GET'])
@_accounting_required
def api_cc_list():
    company_id = request.args.get('company_id', type=int)
    if not company_id:
        return jsonify({'success': False, 'error': 'company_id este obligatoriu'}), 400
    try:
        return jsonify({'success': True, 'data': _repo.list_by_company(company_id)})
    except Exception as e:
        return safe_error_response(e)


@cost_centers_bp.route('/api/cost-centers/structure-nodes', methods=['GET'])
@_accounting_required
def api_cc_structure_nodes():
    company_id = request.args.get('company_id', type=int)
    if not company_id:
        return jsonify({'success': False, 'error': 'company_id este obligatoriu'}), 400
    try:
        return jsonify({'success': True, 'data': _repo.list_structure_nodes(company_id)})
    except Exception as e:
        return safe_error_response(e)


@cost_centers_bp.route('/api/cost-centers', methods=['POST'])
@_accounting_required
def api_cc_create():
    data = request.get_json(silent=True) or {}
    company_id = data.get('company_id')
    code = (data.get('code') or '').strip()
    name = (data.get('name') or '').strip()
    if not company_id or not code or not name:
        return jsonify({'success': False, 'error': 'company_id, code și name sunt obligatorii'}), 400
    try:
        cc_id = _repo.create(company_id, code, name)
        return jsonify({'success': True, 'data': {'id': cc_id}}), 201
    except Exception as e:
        if _is_duplicate(e):
            return jsonify({'success': False, 'error': 'Un centru de cost cu acest cod există deja'}), 409
        return safe_error_response(e)


@cost_centers_bp.route('/api/cost-centers/<int:cc_id>', methods=['PATCH'])
@_accounting_required
def api_cc_update(cc_id):
    data = request.get_json(silent=True) or {}
    try:
        _repo.update(cc_id, code=data.get('code'), name=data.get('name'), active=data.get('active'))
        return jsonify({'success': True})
    except Exception as e:
        if _is_duplicate(e):
            return jsonify({'success': False, 'error': 'Un centru de cost cu acest cod există deja'}), 409
        return safe_error_response(e)


@cost_centers_bp.route('/api/cost-centers/<int:cc_id>', methods=['DELETE'])
@_accounting_required
def api_cc_delete(cc_id):
    try:
        _repo.delete(cc_id)
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@cost_centers_bp.route('/api/cost-centers/<int:cc_id>/map', methods=['PUT'])
@_accounting_required
def api_cc_set_map(cc_id):
    data = request.get_json(silent=True) or {}
    try:
        _repo.set_map(cc_id, data.get('structure_node_id'))
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@cost_centers_bp.route('/api/cost-centers/seed-map-exact', methods=['POST'])
@_accounting_required
def api_cc_seed_map():
    data = request.get_json(silent=True) or {}
    company_id = data.get('company_id')
    if not company_id:
        return jsonify({'success': False, 'error': 'company_id este obligatoriu'}), 400
    try:
        return jsonify({'success': True, 'data': {'inserted': _repo.auto_seed_map_exact(company_id)}})
    except Exception as e:
        return safe_error_response(e)
