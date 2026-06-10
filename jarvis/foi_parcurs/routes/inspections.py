"""Routes for vehicle damage inspections."""
from ._shared import foi_parcurs_bp, jsonify, request, login_required, current_user, logger, _inspection_repo


@foi_parcurs_bp.route('/api/foi-parcurs/vehicles/<int:vehicle_id>/inspections', methods=['GET'])
@login_required
def api_get_inspections(vehicle_id):
    rows = _inspection_repo.get_by_vehicle(vehicle_id)
    return jsonify({'inspections': rows})


@foi_parcurs_bp.route('/api/foi-parcurs/vehicles/<int:vehicle_id>/inspections', methods=['POST'])
@login_required
def api_create_inspection(vehicle_id):
    data = request.get_json(silent=True) or {}
    from ..repositories.vehicle_repository import FPVehicleRepository
    vehicle = FPVehicleRepository().get_by_id(vehicle_id)
    if not vehicle:
        return jsonify({'success': False, 'error': 'Vehicle not found'}), 404

    row = _inspection_repo.create({
        'vehicle_id': vehicle_id,
        'vin': vehicle.get('vin', ''),
        'inspection_date': data.get('inspection_date'),
        'condition_notes': data.get('condition_notes', ''),
        'photos': data.get('photos', []),
        'inspector_name': data.get('inspector_name', ''),
        'inspector_signature': data.get('inspector_signature', ''),
        'created_by': current_user.id if current_user else None,
    })
    return jsonify({'success': True, 'inspection': row})


@foi_parcurs_bp.route('/api/foi-parcurs/vehicles/<int:vehicle_id>/inspections/latest', methods=['GET'])
@login_required
def api_latest_inspection(vehicle_id):
    row = _inspection_repo.get_latest(vehicle_id)
    return jsonify({'inspection': row})


@foi_parcurs_bp.route('/api/foi-parcurs/inspections/<int:id>', methods=['DELETE'])
@login_required
def api_delete_inspection(id):
    _inspection_repo.delete(id)
    return jsonify({'success': True})
