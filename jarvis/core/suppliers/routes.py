"""Supplier master + Procesare resolution API."""
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

from core.roles.repositories.permission_repository import PermissionRepository
from core.suppliers.repository import SupplierMasterRepository
from core.suppliers.resolver import SupplierResolver

suppliers_bp = Blueprint('suppliers', __name__)
_perm_repo = PermissionRepository()
_repo = SupplierMasterRepository()
_resolver = SupplierResolver(_repo)


def _check_supplier_perm(action: str) -> bool:
    if getattr(current_user, 'role_name', '').lower() in ('admin', 'superadmin'):
        return True
    role_id = getattr(current_user, 'role_id', None)
    if not role_id:
        return False
    perm = _perm_repo.check_permission_v2(role_id, 'suppliers', 'master', action)
    return perm.get('has_permission', False)


@suppliers_bp.route('/api/suppliers', methods=['GET'])
@login_required
def api_list_suppliers():
    if not _check_supplier_perm('view'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    suppliers = _repo.list_master(
        search=request.args.get('search'),
        limit=min(int(request.args.get('limit', 100)), 500),
        offset=int(request.args.get('offset', 0)))
    return jsonify({'success': True, 'suppliers': suppliers})


@suppliers_bp.route('/api/suppliers/<int:supplier_id>', methods=['GET'])
@login_required
def api_get_supplier(supplier_id):
    if not _check_supplier_perm('view'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    sup = _repo.get_master(supplier_id)
    if not sup:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return jsonify({'success': True, 'supplier': sup})


@suppliers_bp.route('/api/suppliers', methods=['POST'])
@login_required
def api_create_supplier():
    if not _check_supplier_perm('edit'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json(force=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'name is required'}), 400
    sid = _repo.create_master(name, created_by=getattr(current_user, 'id', None),
                              **{k: v for k, v in data.items() if k != 'name'})
    return jsonify({'success': True, 'id': sid}), 201


@suppliers_bp.route('/api/suppliers/<int:supplier_id>', methods=['PUT'])
@login_required
def api_update_supplier(supplier_id):
    if not _check_supplier_perm('edit'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json(force=True) or {}
    _repo.update_master(supplier_id, **data)
    return jsonify({'success': True})


@suppliers_bp.route('/api/suppliers/<int:supplier_id>/aliases', methods=['POST'])
@login_required
def api_add_alias(supplier_id):
    if not _check_supplier_perm('resolve'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json(force=True) or {}
    alias_id = _repo.add_alias(supplier_id, alias_name=data.get('alias_name'),
                               alias_cui=data.get('alias_cui'), source=data.get('source', 'manual'),
                               created_by=getattr(current_user, 'id', None))
    return jsonify({'success': True, 'id': alias_id}), 201


@suppliers_bp.route('/api/suppliers/merge', methods=['POST'])
@login_required
def api_merge_suppliers():
    if not _check_supplier_perm('merge'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json(force=True) or {}
    survivor, dup = data.get('survivor_id'), data.get('duplicate_id')
    if not survivor or not dup or survivor == dup:
        return jsonify({'success': False, 'error': 'survivor_id and distinct duplicate_id are required'}), 400
    _repo.merge(survivor, dup, created_by=getattr(current_user, 'id', None))
    return jsonify({'success': True})


@suppliers_bp.route('/api/suppliers/worklist', methods=['GET'])
@login_required
def api_worklist():
    if not _check_supplier_perm('view'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    items = []
    for row in _repo.unresolved_efactura():
        res = _resolver.resolve(name=row['partner_name'], cui=row['partner_cif'])
        if res.confidence != 'high':
            items.append({'source': 'efactura', 'partner_name': row['partner_name'],
                          'partner_cif': row['partner_cif'],
                          'candidate_id': res.supplier_id, 'confidence': res.confidence, 'method': res.method})
    for row in _repo.unresolved_invoice_suppliers():
        res = _resolver.resolve(name=row['partner_name'])
        if res.confidence != 'high':
            items.append({'source': 'invoice', 'partner_name': row['partner_name'], 'partner_cif': None,
                          'count': row['n'], 'candidate_id': res.supplier_id,
                          'confidence': res.confidence, 'method': res.method})
    return jsonify({'success': True, 'items': items})


@suppliers_bp.route('/api/suppliers/resolve', methods=['POST'])
@login_required
def api_resolve():
    if not _check_supplier_perm('resolve'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    data = request.get_json(force=True) or {}
    action = data.get('action')          # 'link' | 'create' | 'ignore'
    partner_name = data.get('partner_name')
    partner_cif = data.get('partner_cif')
    uid = getattr(current_user, 'id', None)

    if action == 'link':
        sid = data.get('supplier_id')
        if not sid:
            return jsonify({'success': False, 'error': 'supplier_id required for link'}), 400
    elif action == 'create':
        sid = _repo.create_master(partner_name, created_by=uid, cui=partner_cif)
    elif action == 'ignore':
        return jsonify({'success': True, 'ignored': True})
    else:
        return jsonify({'success': False, 'error': 'unknown action'}), 400

    _repo.add_alias(sid, alias_name=partner_name, alias_cui=partner_cif, source='resolve', created_by=uid)
    linked = _repo.set_efactura_supplier_id(sid, partner_name=partner_name, partner_cif=partner_cif)
    return jsonify({'success': True, 'supplier_id': sid, 'efactura_linked': linked})


@suppliers_bp.route('/api/suppliers/backfill-efactura', methods=['POST'])
@login_required
def api_backfill_efactura():
    if not _check_supplier_perm('resolve'):
        return jsonify({'success': False, 'error': 'Permission denied'}), 403
    bound = 0
    for row in _repo.unresolved_efactura(limit=5000):
        res = _resolver.resolve(name=row['partner_name'], cui=row['partner_cif'])
        if res.confidence == 'high' and res.supplier_id:
            bound += _repo.set_efactura_supplier_id(res.supplier_id,
                                                    partner_name=row['partner_name'],
                                                    partner_cif=row['partner_cif'])
    return jsonify({'success': True, 'bound': bound})
