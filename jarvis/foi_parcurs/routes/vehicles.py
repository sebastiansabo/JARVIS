"""Routes for foi de parcurs vehicle stock management."""

from ._shared import (
    foi_parcurs_bp, jsonify, request, login_required,
    logger, _vehicle_repo,
)


def _to_int_or_none(value):
    """Coerce to int, or None if empty/invalid."""
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


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
    if fuel_type not in ('Benzina', 'Diesel', 'Electric', 'Hybrid'):
        return jsonify({'success': False, 'error': 'fuel_type must be Benzina, Diesel, Electric, or Hybrid'}), 400

    # Capacity depends on fuel type: combustion → liters, Electric → kWh, Hybrid → both
    fuel_liters = _to_int_or_none(data.get('fuel_tank_capacity_liters'))
    battery_kwh = _to_int_or_none(data.get('battery_capacity_kwh'))
    if fuel_type in ('Benzina', 'Diesel', 'Hybrid') and not fuel_liters:
        return jsonify({'success': False, 'error': 'Fuel capacity (L) is required for this fuel type'}), 400
    if fuel_type in ('Electric', 'Hybrid') and not battery_kwh:
        return jsonify({'success': False, 'error': 'Battery capacity (kWh) is required for this fuel type'}), 400
    if fuel_type == 'Electric':
        fuel_liters = None
    if fuel_type in ('Benzina', 'Diesel'):
        battery_kwh = None

    company_id = data.get('company_id')
    if company_id is not None:
        try:
            company_id = int(company_id)
        except (ValueError, TypeError):
            company_id = None

    try:
        vehicle = _vehicle_repo.create({
            'vin': vin,
            'registration_number': (data.get('registration_number') or '').strip().upper() or None,
            'car_id': (data.get('car_id') or '').strip() or None,
            'mark': mark,
            'brand': (data.get('brand') or '').strip() or None,
            'model': model,
            'color': (data.get('color') or '').strip() or None,
            'fuel_type': fuel_type,
            'fuel_tank_capacity_liters': fuel_liters,
            'battery_capacity_kwh': battery_kwh,
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
