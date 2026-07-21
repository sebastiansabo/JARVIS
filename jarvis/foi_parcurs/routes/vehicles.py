"""Routes for foi de parcurs vehicle stock management."""

from ._shared import (
    foi_parcurs_bp, jsonify, request, login_required,
    logger, _vehicle_repo, _fp_repo,
)


def _to_int_or_none(value):
    """Coerce to int, or None if empty/invalid."""
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _to_num_or_none(value):
    """Coerce to a number (allows decimals, e.g. 1.8 kWh), or None if empty/invalid."""
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


@foi_parcurs_bp.route('/api/foi-parcurs/vehicles', methods=['GET'])
@login_required
def api_list_vehicles():
    active_only = request.args.get('active_only', 'true').lower() == 'true'
    vehicles = _vehicle_repo.get_all(active_only=active_only)
    return jsonify({'success': True, 'vehicles': vehicles})


@foi_parcurs_bp.route('/api/foi-parcurs/vehicles/<int:vehicle_id>', methods=['GET'])
@login_required
def api_get_vehicle(vehicle_id):
    """Full vehicle incl. the document blobs — used by the edit form. The list
    endpoint is lean (no docs), so the form fetches them here on demand."""
    vehicle = _vehicle_repo.get_by_id(vehicle_id)
    if not vehicle:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return jsonify({'success': True, 'vehicle': vehicle})


@foi_parcurs_bp.route('/api/foi-parcurs/odometer-history', methods=['GET'])
@login_required
def api_odometer_history():
    """Per-car odometer history + KM-gap detection. Query: ?vin=<vin>.

    Returns the car's current stored odometer plus every drive (all route types)
    in chronological order, each annotated with gap_km = this drive's km_start
    minus the previous drive's km_end (km driven between logged drives; > 0 means
    the car moved without a logged drive)."""
    vin = (request.args.get('vin') or '').strip()
    if not vin:
        return jsonify({'success': False, 'error': 'vin is required'}), 400

    vehicle = _vehicle_repo.get_by_vin(vin)
    rows = _fp_repo.get_odometer_readings(vin)

    entries = []
    prev_end = None
    for r in rows:
        route_type = r.get('route_type')
        km_start = r.get('km_start')
        km_end = r.get('km_end')
        # A Test Drive is "returned" only once the return form is submitted
        # (returned_at set / status COMPLETED). Non-TD contracts are historical
        # complete records. Until returned, the km_end/return time are just
        # placeholders, so we blank them and don't advance the gap baseline.
        returned = (
            route_type != 'TD'
            or r.get('returned_at') is not None
            or r.get('status') == 'COMPLETED'
        )
        gap_km = (km_start - prev_end) if (prev_end is not None and km_start is not None) else None
        entries.append({
            'id': r.get('id'),
            'contract_id': r.get('contract_id'),
            'route_type': route_type,
            'status': r.get('status'),
            'returned': returned,
            'km_start': km_start,
            'km_end': km_end if returned else None,
            'departure_datetime': r.get('departure_datetime'),
            'return_datetime': r.get('return_datetime') if returned else None,
            'client_name': r.get('client_name'),
            'gap_km': gap_km,
            'departure_damage': r.get('departure_damage') or [],
            'return_damage': r.get('return_damage') or [],
        })
        if returned and km_end is not None:
            prev_end = km_end

    return jsonify({
        'success': True,
        'vin': vin,
        'current_odometer': (vehicle or {}).get('odometer_km'),
        'entries': entries,
    })


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
    fuel_liters = _to_num_or_none(data.get('fuel_tank_capacity_liters'))
    battery_kwh = _to_num_or_none(data.get('battery_capacity_kwh'))
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
            'odometer_km': _to_int_or_none(data.get('odometer_km')),
            'company_id': company_id,
            'vignette_valid_until': (data.get('vignette_valid_until') or '').strip() or None,
            'itp_valid_until': (data.get('itp_valid_until') or '').strip() or None,
            'insurance_valid_until': (data.get('insurance_valid_until') or '').strip() or None,
            'insurance_doc': data.get('insurance_doc') or None,
            'talon_doc': data.get('talon_doc') or None,
            'civ_doc': data.get('civ_doc') or None,
            'registration_doc': data.get('registration_doc') or None,
            'offer_doc': data.get('offer_doc') or None,
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
    # DATE columns reject '' — coerce blank validity dates to NULL (clears them).
    for _col in ('vignette_valid_until', 'itp_valid_until', 'insurance_valid_until'):
        if _col in data and not (data[_col] or '').strip():
            data[_col] = None
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


@foi_parcurs_bp.route('/api/foi-parcurs/vehicles/<vin>/conflicts', methods=['GET'])
@login_required
def api_vehicle_conflicts(vin):
    """Overlapping open sessions (planned or live) for a VIN in [from, to].
    Used to soft-block double-booking a car."""
    frm = request.args.get('from')
    to = request.args.get('to')
    if not frm or not to:
        return jsonify({'success': False, 'error': 'from and to are required'}), 400
    exclude_id = request.args.get('exclude_id', type=int)
    rows = _fp_repo.find_conflicts(vin, frm, to, exclude_id)
    return jsonify({'success': True, 'conflicts': rows})


@foi_parcurs_bp.route('/api/foi-parcurs/companies', methods=['GET'])
@login_required
def api_list_companies():
    """List companies for vehicle assignment dropdown."""
    from core.base_repository import BaseRepository
    repo = BaseRepository()
    companies = repo.query_all('SELECT id, company FROM companies ORDER BY company')
    return jsonify({'success': True, 'companies': companies})


@foi_parcurs_bp.route('/api/foi-parcurs/brands/<int:company_id>', methods=['GET'])
@login_required
def api_list_brands(company_id):
    """List the car brands a company carries (from the company_brands catalog).

    Deliberately reads the brand catalog rather than structure_nodes L1, because
    some companies use L1 for departments (e.g. Administrativ, Aftersales), not brands.
    """
    from core.base_repository import BaseRepository
    repo = BaseRepository()
    rows = repo.query_all(
        '''SELECT b.name
           FROM company_brands cb
           JOIN brands b ON b.id = cb.brand_id
           LEFT JOIN fp_dealer_config dc
                  ON dc.company_id = cb.company_id AND dc.brand_id = cb.brand_id
           WHERE cb.company_id = %s AND cb.is_active = TRUE AND b.is_active = TRUE
             AND COALESCE(dc.show_in_foi_parcurs, TRUE) = TRUE
           ORDER BY b.name''',
        (company_id,),
    )
    brands = [r['name'] for r in (rows or [])]
    return jsonify({'success': True, 'brands': brands})
