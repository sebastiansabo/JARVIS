"""Routes for foi de parcurs vehicle stock management."""

from ._shared import (
    foi_parcurs_bp, jsonify, request, login_required,
    logger, _vehicle_repo,
)


@foi_parcurs_bp.route('/api/foi-parcurs/vehicles', methods=['GET'])
@login_required
def api_list_vehicles():
    active_only = request.args.get('active_only', 'true').lower() == 'true'
    vehicles = _vehicle_repo.get_all(active_only=active_only)
    return jsonify({'success': True, 'vehicles': vehicles})


@foi_parcurs_bp.route('/api/foi-parcurs/vehicles', methods=['POST'])
@login_required
def api_create_vehicle():
    data = request.get_json(silent=True) or {}
    vin = (data.get('vin') or '').strip().upper()
    mark = (data.get('mark') or '').strip()
    model = (data.get('model') or '').strip()

    if not vin:
        return jsonify({'success': False, 'error': 'VIN is required'}), 400
    if not mark:
        return jsonify({'success': False, 'error': 'Mark is required'}), 400
    if not model:
        return jsonify({'success': False, 'error': 'Model is required'}), 400

    # Check duplicate VIN
    existing = _vehicle_repo.get_by_vin(vin)
    if existing:
        return jsonify({'success': False, 'error': f'Vehicle with VIN {vin} already exists'}), 409

    fuel_type = (data.get('fuel_type') or 'Diesel').strip()
    if fuel_type not in ('Benzina', 'Diesel', 'Electric'):
        return jsonify({'success': False, 'error': 'fuel_type must be Benzina, Diesel, or Electric'}), 400

    company_id = data.get('company_id')
    if company_id is not None:
        try:
            company_id = int(company_id)
        except (ValueError, TypeError):
            company_id = None

    try:
        vehicle = _vehicle_repo.create({
            'vin': vin,
            'mark': mark,
            'model': model,
            'fuel_type': fuel_type,
            'fuel_tank_capacity_liters': int(data.get('fuel_tank_capacity_liters', 50)),
            'company_id': company_id,
        })
        return jsonify({'success': True, 'vehicle': vehicle})
    except Exception as e:
        logger.exception('Failed to create vehicle')
        return jsonify({'success': False, 'error': str(e)[:300]}), 500


@foi_parcurs_bp.route('/api/foi-parcurs/vehicles/<int:vehicle_id>', methods=['PUT'])
@login_required
def api_update_vehicle(vehicle_id):
    data = request.get_json(silent=True) or {}
    if 'vin' in data:
        data['vin'] = data['vin'].strip().upper()
    try:
        vehicle = _vehicle_repo.update(vehicle_id, data)
        if not vehicle:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        return jsonify({'success': True, 'vehicle': vehicle})
    except Exception as e:
        logger.exception('Failed to update vehicle')
        return jsonify({'success': False, 'error': str(e)[:300]}), 500


@foi_parcurs_bp.route('/api/foi-parcurs/vehicles/<int:vehicle_id>', methods=['DELETE'])
@login_required
def api_delete_vehicle(vehicle_id):
    _vehicle_repo.delete(vehicle_id)
    return jsonify({'success': True})


@foi_parcurs_bp.route('/api/foi-parcurs/companies', methods=['GET'])
@login_required
def api_list_companies():
    """List companies for vehicle assignment dropdown."""
    from core.base_repository import BaseRepository
    repo = BaseRepository()
    companies = repo.query_all('SELECT id, company FROM companies ORDER BY company')
    return jsonify({'success': True, 'companies': companies})
