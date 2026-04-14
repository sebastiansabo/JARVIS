"""
e-Factura Supplier Mappings and Supplier Types API routes.
"""
from flask import request, jsonify

from core.utils.api_helpers import safe_error_response, api_login_required
from ._shared import efactura_bp, efactura_access_required
from ..repositories.supplier_mapping_repository import SupplierMappingRepository
from ..repositories.supplier_type_repository import SupplierTypeRepository

supplier_mapping_repo = SupplierMappingRepository()
supplier_type_repo = SupplierTypeRepository()


# ============================================================
# API: Supplier Mappings
# ============================================================

@efactura_bp.route('/api/mappings', methods=['GET'])
@api_login_required
@efactura_access_required
def list_supplier_mappings():
    """
    List all supplier mappings.

    Query params:
        active_only: Whether to show only active mappings (default true)
    """
    try:
        active_only = request.args.get('active_only', 'true').lower() == 'true'

        mappings = supplier_mapping_repo.get_all(active_only=active_only)

        return jsonify({
            'success': True,
            'mappings': mappings,
            'count': len(mappings),
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/mappings/<int:mapping_id>', methods=['GET'])
@api_login_required
@efactura_access_required
def get_supplier_mapping(mapping_id: int):
    """Get a single supplier mapping by ID."""
    try:
        mapping = supplier_mapping_repo.get_by_id(mapping_id)

        if not mapping:
            return jsonify({
                'success': False,
                'error': 'Mapping not found',
            }), 404

        return jsonify({
            'success': True,
            'mapping': mapping,
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/mappings', methods=['POST'])
@api_login_required
@efactura_access_required
def create_supplier_mapping():
    """
    Create a new supplier mapping.

    Request body:
        partner_name: The e-Factura partner name (required)
        supplier_name: The standardized supplier name (required)
        partner_cif: Optional VAT number from e-Factura
        supplier_note: Optional notes about the supplier
        supplier_vat: The standardized VAT number
        kod_konto: The accounting code
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': "No data provided",
            }), 400

        partner_name = data.get('partner_name', '').strip()
        supplier_name = data.get('supplier_name', '').strip()

        if not partner_name:
            return jsonify({
                'success': False,
                'error': "partner_name is required",
            }), 400

        if not supplier_name:
            return jsonify({
                'success': False,
                'error': "supplier_name is required",
            }), 400

        # Handle type_ids array (new) or type_id (legacy)
        type_ids = data.get('type_ids')
        type_id = data.get('type_id')

        # Convert type_ids to list of ints
        if type_ids is not None:
            try:
                type_ids = [int(tid) for tid in type_ids if tid]
            except (ValueError, TypeError):
                type_ids = []
        elif type_id is not None:
            # Legacy: convert single type_id to list
            try:
                type_ids = [int(type_id)] if type_id else []
            except (ValueError, TypeError):
                type_ids = []

        # Parse optional company_id
        raw_company_id = data.get('company_id')
        company_id = int(raw_company_id) if raw_company_id else None

        mapping_id = supplier_mapping_repo.create(
            partner_name=partner_name,
            supplier_name=supplier_name,
            partner_cif=data.get('partner_cif', '').strip() or None,
            supplier_note=data.get('supplier_note', '').strip() or None,
            supplier_vat=data.get('supplier_vat', '').strip() or None,
            kod_konto=data.get('kod_konto', '').strip() or None,
            type_ids=type_ids,
            brand=data.get('brand', '').strip() or None,
            department=data.get('department', '').strip() or None,
            subdepartment=data.get('subdepartment', '').strip() or None,
            company_id=company_id,
        )

        # Note: No auto-hide here - visibility is now controlled dynamically
        # by partner type settings (hide_in_filter flag)

        return jsonify({
            'success': True,
            'id': mapping_id,
            'message': 'Mapping created successfully',
        }), 201

    except Exception as e:
        if 'unique constraint' in str(e).lower() or 'duplicate' in str(e).lower():
            return jsonify({
                'success': False,
                'error': 'A mapping for this partner already exists',
            }), 409
        return safe_error_response(e)


@efactura_bp.route('/api/mappings/<int:mapping_id>', methods=['PUT'])
@api_login_required
@efactura_access_required
def update_supplier_mapping(mapping_id: int):
    """
    Update a supplier mapping.

    Request body:
        partner_name: New partner name
        partner_cif: New partner CIF
        supplier_name: New supplier name
        supplier_note: New supplier note
        supplier_vat: New supplier VAT
        kod_konto: New accounting code
        is_active: Whether mapping is active
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': "No data provided",
            }), 400

        # Handle type_ids array (new) or type_id (legacy)
        type_ids = None
        if 'type_ids' in data:
            # type_ids explicitly provided (can be empty array to clear types)
            try:
                type_ids = [int(tid) for tid in data['type_ids'] if tid]
            except (ValueError, TypeError):
                type_ids = []
        elif 'type_id' in data:
            # Legacy: convert single type_id to list
            type_id = data.get('type_id')
            try:
                type_ids = [int(type_id)] if type_id else []
            except (ValueError, TypeError):
                type_ids = []

        # Parse optional company_id (distinguish between not-sent and explicitly null)
        company_id_kwarg = {}
        if 'company_id' in data:
            raw_cid = data['company_id']
            company_id_kwarg['company_id'] = int(raw_cid) if raw_cid else None

        success = supplier_mapping_repo.update(
            mapping_id,
            partner_name=data.get('partner_name'),
            partner_cif=data.get('partner_cif'),
            supplier_name=data.get('supplier_name'),
            supplier_note=data.get('supplier_note'),
            supplier_vat=data.get('supplier_vat'),
            kod_konto=data.get('kod_konto'),
            type_ids=type_ids,
            is_active=data.get('is_active'),
            brand=data.get('brand'),
            department=data.get('department'),
            subdepartment=data.get('subdepartment'),
            **company_id_kwarg,
        )

        if not success:
            return jsonify({
                'success': False,
                'error': 'Mapping not found or update failed',
            }), 404

        # Note: No auto-hide here - visibility is now controlled dynamically
        # by partner type settings (hide_in_filter flag)

        return jsonify({
            'success': True,
            'message': 'Mapping updated successfully',
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/mappings/<int:mapping_id>', methods=['DELETE'])
@api_login_required
@efactura_access_required
def delete_supplier_mapping(mapping_id: int):
    """Delete a supplier mapping."""
    try:
        success = supplier_mapping_repo.delete(mapping_id)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Mapping not found',
            }), 404

        return jsonify({
            'success': True,
            'message': 'Mapping deleted successfully',
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/suppliers/distinct', methods=['GET'])
@efactura_bp.route('/api/partners/distinct', methods=['GET'])  # backward compat
@api_login_required
@efactura_access_required
def get_distinct_suppliers():
    """
    Get distinct supplier names and CIFs from e-Factura invoices.

    Returns list of distinct supplier name/CIF combinations for auto-suggest.
    """
    try:
        suppliers = supplier_mapping_repo.get_distinct_suppliers()

        return jsonify({
            'success': True,
            'partners': suppliers,  # keep key for backward compat
            'count': len(suppliers),
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/mappings/lookup', methods=['GET'])
@api_login_required
@efactura_access_required
def lookup_supplier_mapping():
    """
    Find a mapping for a partner name/CIF combination.

    Query params:
        partner_name: Partner name to look up (required)
        partner_cif: Partner CIF (optional, improves match accuracy)

    Returns:
        The matching mapping if found, or null
    """
    try:
        partner_name = request.args.get('partner_name', '').strip()
        partner_cif = request.args.get('partner_cif', '').strip() or None

        if not partner_name:
            return jsonify({
                'success': False,
                'error': "partner_name is required",
            }), 400

        mapping = supplier_mapping_repo.find_by_supplier(partner_name, partner_cif)

        return jsonify({
            'success': True,
            'mapping': mapping,
            'found': mapping is not None,
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/mappings/bulk-delete', methods=['POST'])
@api_login_required
@efactura_access_required
def bulk_delete_supplier_mappings():
    """
    Bulk delete supplier mappings.

    Request body:
        {
            "ids": [1, 2, 3]
        }

    Returns:
        Number of mappings deleted
    """
    try:
        data = request.get_json() or {}
        ids = data.get('ids', [])

        if not ids:
            return jsonify({
                'success': False,
                'error': "No mapping IDs provided",
            }), 400

        deleted_count = 0
        for mapping_id in ids:
            if supplier_mapping_repo.delete(mapping_id):
                deleted_count += 1

        return jsonify({
            'success': True,
            'deleted_count': deleted_count,
            'message': f"Deleted {deleted_count} mapping(s)",
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/mappings/bulk-set-type', methods=['POST'])
@api_login_required
@efactura_access_required
def bulk_set_mappings_type():
    """
    Bulk set type for supplier mappings.

    Request body:
        {
            "ids": [1, 2, 3],
            "type_name": "Service" or "Merchandise" or null
        }

    Returns:
        Number of mappings updated
    """
    try:
        data = request.get_json() or {}
        ids = data.get('ids', [])
        type_name = data.get('type_name')  # Can be None to clear type

        if not ids:
            return jsonify({
                'success': False,
                'error': "No mapping IDs provided",
            }), 400

        # Get type_id from type_name using repository
        type_id = None
        if type_name:
            found_type = supplier_type_repo.get_by_name(type_name)
            if not found_type:
                return jsonify({
                    'success': False,
                    'error': f"Type '{type_name}' not found",
                }), 400
            type_id = found_type['id']

        # Update all mappings using repository
        updated_count, _ = supplier_mapping_repo.bulk_set_types(ids, type_id)

        # Note: No auto-hide here - visibility is now controlled dynamically
        # by partner type settings (hide_in_filter flag)

        return jsonify({
            'success': True,
            'updated': updated_count,
            'message': f"Updated {updated_count} mapping(s)",
        })

    except Exception as e:
        return safe_error_response(e)


# ============================================================
# API: Supplier Types
# ============================================================

@efactura_bp.route('/api/supplier-types', methods=['GET'])
@efactura_bp.route('/api/partner-types', methods=['GET'])  # backward compat
@api_login_required
@efactura_access_required
def list_supplier_types():
    """
    List all supplier types.

    Query params:
        active_only: Whether to show only active types (default true)
        include_inactive: Include inactive types (overrides active_only to false)
    """
    try:
        # Support both active_only and include_inactive parameters
        include_inactive = request.args.get('include_inactive', '').lower() == 'true'
        active_only = not include_inactive and request.args.get('active_only', 'true').lower() == 'true'

        types = supplier_type_repo.get_all(active_only=active_only)

        return jsonify({
            'success': True,
            'data': types,
            'types': types,
            'count': len(types),
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/supplier-types/<int:type_id>', methods=['GET'])
@efactura_bp.route('/api/partner-types/<int:type_id>', methods=['GET'])  # backward compat
@api_login_required
@efactura_access_required
def get_supplier_type(type_id: int):
    """Get a single supplier type by ID."""
    try:
        supplier_type = supplier_type_repo.get_by_id(type_id)

        if not supplier_type:
            return jsonify({
                'success': False,
                'error': 'Supplier type not found',
            }), 404

        return jsonify({
            'success': True,
            'type': supplier_type,
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/supplier-types', methods=['POST'])
@efactura_bp.route('/api/partner-types', methods=['POST'])  # backward compat
@api_login_required
@efactura_access_required
def create_supplier_type():
    """
    Create a new supplier type.

    Request body:
        name: The type name (required)
        description: Optional description
        hide_in_filter: Whether to hide invoices with this type when "Hide Typed" filter is on (default true)
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': "No data provided",
            }), 400

        name = data.get('name', '').strip()

        if not name:
            return jsonify({
                'success': False,
                'error': "name is required",
            }), 400

        # hide_in_filter defaults to True if not specified
        hide_in_filter = data.get('hide_in_filter', True)
        if isinstance(hide_in_filter, str):
            hide_in_filter = hide_in_filter.lower() == 'true'

        type_id = supplier_type_repo.create(
            name=name,
            description=data.get('description', '').strip() or None,
            hide_in_filter=hide_in_filter,
        )

        return jsonify({
            'success': True,
            'id': type_id,
            'message': 'Supplier type created successfully',
        }), 201

    except Exception as e:
        if 'unique constraint' in str(e).lower() or 'duplicate' in str(e).lower():
            return jsonify({
                'success': False,
                'error': 'A supplier type with this name already exists',
            }), 409
        return safe_error_response(e)


@efactura_bp.route('/api/supplier-types/<int:type_id>', methods=['PUT'])
@efactura_bp.route('/api/partner-types/<int:type_id>', methods=['PUT'])  # backward compat
@api_login_required
@efactura_access_required
def update_supplier_type(type_id: int):
    """
    Update a supplier type.

    Request body:
        name: New name
        description: New description
        is_active: Whether type is active
        hide_in_filter: Whether to hide invoices with this type when "Hide Typed" filter is on
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'success': False,
                'error': "No data provided",
            }), 400

        success = supplier_type_repo.update(
            type_id,
            name=data.get('name'),
            description=data.get('description'),
            is_active=data.get('is_active'),
            hide_in_filter=data.get('hide_in_filter'),
        )

        if not success:
            return jsonify({
                'success': False,
                'error': 'Supplier type not found or update failed',
            }), 404

        return jsonify({
            'success': True,
            'message': 'Supplier type updated successfully',
        })

    except Exception as e:
        return safe_error_response(e)


@efactura_bp.route('/api/supplier-types/<int:type_id>', methods=['DELETE'])
@efactura_bp.route('/api/partner-types/<int:type_id>', methods=['DELETE'])  # backward compat
@api_login_required
@efactura_access_required
def delete_supplier_type(type_id: int):
    """Delete a supplier type (soft delete)."""
    try:
        success = supplier_type_repo.delete(type_id)

        if not success:
            return jsonify({
                'success': False,
                'error': 'Supplier type not found',
            }), 404

        return jsonify({
            'success': True,
            'message': 'Supplier type deleted successfully',
        })

    except Exception as e:
        return safe_error_response(e)
