"""CarPark -> Driving Hub fleet push — HTTP routes.

Thin glue only: both routes reuse the existing CarPark vehicle guards
(carpark_edit_required for the permission check, _verify_vehicle_ownership
for the tenant/IDOR guard — see carpark/routes/vehicles.py) and delegate all
mapping/validation/DB work to the Task 2 service
(carpark/services/driving_hub_push_service.py). No SQL or business logic
lives here.
"""
from flask import request, jsonify
from flask_login import login_required, current_user

from carpark import carpark_bp
from carpark.routes.vehicles import carpark_edit_required, _verify_vehicle_ownership
from core.organization.manager_utils import get_actable_company_ids
from carpark.services.driving_hub_push_service import get_fleet_status, push_to_fleet


@carpark_bp.route('/vehicles/<int:vehicle_id>/driving-hub/status', methods=['GET'])
@login_required
@carpark_edit_required
def driving_hub_status(vehicle_id):
    """Is this vehicle already in the Driving Hub fleet (by VIN)? Always
    includes a `suggested` prefill for the push dialog (Task 4)."""
    vehicle, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err
    return jsonify({'success': True, **get_fleet_status(vehicle)})


@carpark_bp.route('/vehicles/<int:vehicle_id>/driving-hub/push', methods=['POST'])
@login_required
@carpark_edit_required
def push_to_driving_hub(vehicle_id):
    """Create a Driving Hub fp_vehicles row from this vehicle, applying any
    overrides (company_id / fuel_type / capacity / plate corrections) the
    push dialog sends in the request body."""
    vehicle, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    is_admin = getattr(current_user, 'can_access_settings', False)
    actable = get_actable_company_ids(current_user.id)

    result, perr = push_to_fleet(vehicle, data, actable, is_admin=is_admin)
    if perr:
        return jsonify({
            'success': False,
            'error': perr['message'],
            **{k: v for k, v in perr.items() if k not in ('status', 'message')},
        }), perr['status']
    return jsonify({'success': True, **result})
