from ._shared import *


# ============== Bonus Types API Routes ==============

@events_bp.route('/api/bonus-types', methods=['GET'])
@login_required
@hr_required
def api_get_bonus_types():
    """API: Get all bonus types."""
    active_only = request.args.get('active_only', 'true').lower() == 'true'
    bonus_types = get_all_bonus_types(active_only=active_only)

    # Strip monetary values if user cannot view amounts
    is_hr_manager = getattr(current_user, 'is_hr_manager', False)
    role_id = getattr(current_user, 'role_id', None)
    can_view = is_hr_manager
    if not can_view and role_id:
        perm = check_permission_v2(role_id, 'hr', 'bonuses', 'view_amounts')
        can_view = perm.get('has_permission', False)

    if not can_view:
        for bt in bonus_types:
            bt.pop('amount', None)

    return jsonify(bonus_types)


@events_bp.route('/api/bonus-types', methods=['POST'])
@login_required
@hr_permission_required('bonuses', 'add')
def api_create_bonus_type():
    """API: Create a new bonus type."""
    data = request.get_json()

    bonus_type_id = save_bonus_type(
        name=data['name'],
        amount=data['amount'],
        days_per_amount=data.get('days_per_amount', 1),
        description=data.get('description'),
        restricted_to_user_id=data.get('restricted_to_user_id') or None
    )

    return jsonify({'success': True, 'id': bonus_type_id})


@events_bp.route('/api/bonus-types/<int:bonus_type_id>', methods=['GET'])
@login_required
@hr_required
def api_get_bonus_type(bonus_type_id):
    """API: Get a single bonus type."""
    bonus_type = get_bonus_type(bonus_type_id)
    if not bonus_type:
        return error_response('Bonus type not found', 404)

    # Strip monetary values if user cannot view amounts
    is_hr_manager = getattr(current_user, 'is_hr_manager', False)
    role_id = getattr(current_user, 'role_id', None)
    can_view = is_hr_manager
    if not can_view and role_id:
        perm = check_permission_v2(role_id, 'hr', 'bonuses', 'view_amounts')
        can_view = perm.get('has_permission', False)
    if not can_view:
        bonus_type.pop('amount', None)

    return jsonify(bonus_type)


@events_bp.route('/api/bonus-types/<int:bonus_type_id>', methods=['PUT'])
@login_required
@hr_permission_required('bonuses', 'edit')
def api_update_bonus_type(bonus_type_id):
    """API: Update a bonus type."""
    data = request.get_json()

    update_bonus_type(
        bonus_type_id=bonus_type_id,
        name=data['name'],
        amount=data['amount'],
        days_per_amount=data.get('days_per_amount', 1),
        description=data.get('description'),
        is_active=data.get('is_active', True),
        restricted_to_user_id=data.get('restricted_to_user_id') or None
    )

    return jsonify({'success': True})


@events_bp.route('/api/bonus-types/<int:bonus_type_id>', methods=['DELETE'])
@login_required
@hr_permission_required('bonuses', 'delete')
def api_delete_bonus_type(bonus_type_id):
    """API: Soft delete a bonus type."""
    delete_bonus_type(bonus_type_id)
    return jsonify({'success': True})
