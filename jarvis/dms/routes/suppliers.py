"""DMS supplier routes (master supplier list)."""
import logging
from flask import request, jsonify
from flask_login import login_required, current_user

from dms import dms_bp
from dms.repositories import SupplierRepository
from dms.routes.documents import dms_permission_required
from core.utils.api_helpers import safe_error_response, get_json_or_error

logger = logging.getLogger('jarvis.dms.routes.suppliers')

_sup_repo = SupplierRepository()


@dms_bp.route('/api/dms/suppliers', methods=['GET'])
@login_required
@dms_permission_required('supplier', 'view')
def api_list_suppliers():
    """List suppliers with search, filters, pagination."""
    company_id = getattr(current_user, 'company_id', None)
    search = request.args.get('search', '').strip() or None
    supplier_type = request.args.get('supplier_type') or None
    active_only = request.args.get('active_only', 'true').lower() != 'false'
    try:
        limit = min(int(request.args.get('limit', 50)), 200)
        offset = int(request.args.get('offset', 0))
    except (ValueError, TypeError):
        limit, offset = 50, 0

    suppliers = _sup_repo.list_all(
        company_id=company_id, active_only=active_only,
        search=search, supplier_type=supplier_type,
        limit=limit, offset=offset,
    )
    total = _sup_repo.count(
        company_id=company_id, active_only=active_only,
        search=search, supplier_type=supplier_type,
    )
    return jsonify({'success': True, 'suppliers': suppliers, 'total': total})


@dms_bp.route('/api/dms/suppliers/<int:sup_id>', methods=['GET'])
@login_required
@dms_permission_required('supplier', 'view')
def api_get_supplier(sup_id):
    """Get a single supplier."""
    sup = _sup_repo.get_by_id(sup_id)
    company_id = getattr(current_user, 'company_id', None)
    if not sup or (company_id and sup.get('company_id') != company_id):
        return jsonify({'success': False, 'error': 'Supplier not found'}), 404
    return jsonify({'success': True, 'supplier': sup})


@dms_bp.route('/api/dms/suppliers', methods=['POST'])
@login_required
@dms_permission_required('supplier', 'manage')
def api_create_supplier():
    """Create a new supplier."""
    data, error = get_json_or_error()
    if error:
        return error

    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Name is required'}), 400

    company_id = getattr(current_user, 'company_id', None)

    try:
        row = _sup_repo.create(
            name=name,
            company_id=company_id,
            created_by=current_user.id,
            supplier_type=data.get('supplier_type', 'company'),
            cui=data.get('cui'),
            j_number=data.get('j_number'),
            address=data.get('address'),
            city=data.get('city'),
            county=data.get('county'),
            nr_reg_com=data.get('nr_reg_com'),
            bank_account=data.get('bank_account'),
            iban=data.get('iban'),
            bank_name=data.get('bank_name'),
            phone=data.get('phone'),
            email=data.get('email'),
        )
        return jsonify({'success': True, 'id': row['id']}), 201
    except Exception as e:
        return safe_error_response(e)


@dms_bp.route('/api/dms/suppliers/<int:sup_id>', methods=['PUT'])
@login_required
@dms_permission_required('supplier', 'manage')
def api_update_supplier(sup_id):
    """Update a supplier."""
    data, error = get_json_or_error()
    if error:
        return error

    sup = _sup_repo.get_by_id(sup_id)
    company_id = getattr(current_user, 'company_id', None)
    if not sup or (company_id and sup.get('company_id') != company_id):
        return jsonify({'success': False, 'error': 'Supplier not found'}), 404

    try:
        fields = {}
        for key in ('name', 'supplier_type', 'cui', 'j_number', 'address', 'city',
                     'county', 'nr_reg_com', 'bank_account', 'iban', 'bank_name',
                     'phone', 'email', 'is_active'):
            if key in data:
                fields[key] = data[key]
        _sup_repo.update(sup_id, **fields)
        return jsonify({'success': True})
    except Exception as e:
        return safe_error_response(e)


@dms_bp.route('/api/dms/suppliers/<int:sup_id>', methods=['DELETE'])
@login_required
@dms_permission_required('supplier', 'manage')
def api_delete_supplier(sup_id):
    """Soft-delete a supplier."""
    sup = _sup_repo.get_by_id(sup_id)
    company_id = getattr(current_user, 'company_id', None)
    if not sup or (company_id and sup.get('company_id') != company_id):
        return jsonify({'success': False, 'error': 'Supplier not found'}), 404
    _sup_repo.delete(sup_id)
    return jsonify({'success': True})
