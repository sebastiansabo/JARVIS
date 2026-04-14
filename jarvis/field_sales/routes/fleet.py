"""Field Sales fleet routes — get_fleet, add_vehicle, update_vehicle."""

from ._shared import *  # noqa: F401, F403


@field_sales_bp.route('/api/field-sales/clients/<int:client_id>/fleet', methods=['GET'])
@jwt_or_login_required
@field_sales_required
def api_client_fleet(client_id):
    """Get fleet vehicles for a client."""
    try:
        fleet = _client_repo.get_fleet(client_id)
        return jsonify({'success': True, 'fleet': fleet})
    except Exception as e:
        logger.exception('Error fetching fleet')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/clients/<int:client_id>/fleet', methods=['POST'])
@jwt_or_login_required
@field_sales_required
def api_add_fleet_vehicle(client_id):
    """Add a vehicle to a client's fleet. Requires field_sales.fleet.manage."""
    try:
        perm_err = _require_fleet_permission()
        if perm_err:
            return perm_err

        # Verify client exists
        client = _client_repo.get_by_id(client_id)
        if not client:
            return jsonify({'success': False, 'error': 'Client not found'}), 404

        data = request.get_json(silent=True) or {}
        data['client_id'] = client_id

        vehicle = _client_repo.upsert_fleet_vehicle(data)

        # Update fleet_size on profile
        try:
            fleet = _client_repo.get_fleet(client_id)
            active_count = len([v for v in fleet if v.get('status') == 'active']) if fleet else 0
            _client_repo.update_profile(client_id, {'fleet_size': active_count})
        except Exception:
            pass

        return jsonify({'success': True, 'vehicle': vehicle}), 201
    except Exception as e:
        logger.exception('Error adding fleet vehicle')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


@field_sales_bp.route('/api/field-sales/fleet/<int:vehicle_id>', methods=['PUT'])
@jwt_or_login_required
@field_sales_required
def api_update_fleet_vehicle(vehicle_id):
    """Update a fleet vehicle. Requires field_sales.fleet.manage."""
    try:
        perm_err = _require_fleet_permission()
        if perm_err:
            return perm_err

        data = request.get_json(silent=True) or {}
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400

        vehicle = _client_repo.update_fleet_vehicle(vehicle_id, data)
        if not vehicle:
            return jsonify({'success': False, 'error': 'Vehicle not found or no editable fields'}), 404

        # Update fleet_size on profile
        try:
            client_id = vehicle.get('client_id')
            if client_id:
                fleet = _client_repo.get_fleet(client_id)
                active_count = len([v for v in fleet if v.get('status') == 'active']) if fleet else 0
                _client_repo.update_profile(client_id, {'fleet_size': active_count})
        except Exception:
            pass

        return jsonify({'success': True, 'vehicle': vehicle})
    except Exception as e:
        logger.exception('Error updating fleet vehicle')
        return jsonify({'success': False, 'error': _safe_error(e)}), 500
