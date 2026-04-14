"""Mapping CRUD routes."""
from ._shared import *  # noqa: F401, F403


# ============== VENDOR MAPPINGS ==============

@statements_bp.route('/api/mappings', methods=['GET'])
@api_login_required
@statements_access_required
def list_mappings():
    """List all vendor mappings."""
    active_only = request.args.get('active_only', 'true').lower() == 'true'
    mappings = statements_service.get_all_mappings(active_only=active_only)

    return jsonify({
        'success': True,
        'mappings': mappings
    })


@statements_bp.route('/api/mappings', methods=['POST'])
@api_login_required
@statements_access_required
def create_mapping():
    """Create a new vendor mapping."""
    data, error = get_json_or_error()
    if error:
        return error

    # Validate required fields
    errors = {}
    if not data.get('pattern'):
        errors['pattern'] = 'Pattern is required'
    if not data.get('supplier_name'):
        errors['supplier_name'] = 'Supplier name is required'

    if errors:
        return jsonify({
            'success': False,
            'error': 'Validation failed',
            'details': errors
        }), 400

    # Validate regex pattern
    is_valid, regex_error = validate_regex(data['pattern'])
    if not is_valid:
        logger.warning(f"Invalid regex pattern: {data['pattern']} - {regex_error}")
        return jsonify({
            'success': False,
            'error': 'Invalid regex pattern',
            'details': {'pattern': regex_error}
        }), 422

    result = statements_service.create_mapping(
        pattern=data['pattern'],
        supplier_name=data['supplier_name'],
        supplier_vat=data.get('supplier_vat'),
        template_id=data.get('template_id')
    )

    if result.success:
        return jsonify({
            'success': True,
            'mapping_id': result.data['mapping_id']
        })
    return jsonify({
        'success': False,
        'error': 'Database error',
        'details': {'message': result.error}
    }), 500


@statements_bp.route('/api/mappings/<int:mapping_id>', methods=['GET'])
@api_login_required
@statements_access_required
def get_single_mapping(mapping_id):
    """Get a single vendor mapping by ID."""
    mapping = statements_service.get_mapping(mapping_id)
    if not mapping:
        return jsonify({'success': False, 'error': 'Mapping not found'}), 404

    return jsonify({'success': True, 'mapping': mapping})


@statements_bp.route('/api/mappings/<int:mapping_id>', methods=['PUT'])
@api_login_required
@statements_access_required
def update_single_mapping(mapping_id):
    """Update a vendor mapping."""
    data, error = get_json_or_error()
    if error:
        return error

    # Validate regex pattern if provided
    if data.get('pattern'):
        is_valid, regex_error = validate_regex(data['pattern'])
        if not is_valid:
            logger.warning(f"Invalid regex pattern for mapping {mapping_id}: {data['pattern']} - {regex_error}")
            return jsonify({
                'success': False,
                'error': 'Invalid regex pattern',
                'details': {'pattern': regex_error}
            }), 422

    result = statements_service.update_mapping(
        mapping_id,
        pattern=data.get('pattern'),
        supplier_name=data.get('supplier_name'),
        supplier_vat=data.get('supplier_vat'),
        template_id=data.get('template_id'),
        is_active=data.get('is_active')
    )

    if result.success:
        return jsonify({'success': True})
    return jsonify({
        'success': False,
        'error': result.error
    }), 404 if 'not found' in (result.error or '') else 500


@statements_bp.route('/api/mappings/<int:mapping_id>', methods=['DELETE'])
@api_login_required
@statements_access_required
def delete_single_mapping(mapping_id):
    """Delete a vendor mapping."""
    result = statements_service.delete_mapping(mapping_id)

    if result.success:
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': result.error}), 400
