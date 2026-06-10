"""Routes for Test Drive form submission."""
import time
import uuid
from ._shared import (
    foi_parcurs_bp, jsonify, request, login_required, current_user,
    logger, _fp_repo, _inspection_repo,
)


@foi_parcurs_bp.route('/api/foi-parcurs/test-drive', methods=['POST'])
@login_required
def api_submit_test_drive():
    """Submit test drive form — creates FILLED contract."""
    data = request.get_json(silent=True) or {}

    required = ['company_id', 'vin', 'client_id', 'odometer_start', 'estimated_km',
                'fuel_gauge_start_level', 'departure_datetime', 'itinerary',
                'advisor_name', 'client_signature', 'gdpr_consent']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({'success': False, 'error': f'Missing: {", ".join(missing)}'}), 400

    if not data.get('gdpr_consent'):
        return jsonify({'success': False, 'error': 'GDPR consent is required'}), 400

    contract_id = f"TD-{data['vin'][:8]}-{int(time.time())}-{uuid.uuid4().hex[:4]}"

    try:
        contract_data = {
            'contract_id': contract_id,
            'vin': data['vin'],
            'registration_number': data.get('registration_number', ''),
            'company_id': int(data['company_id']),
            'client_id': int(data['client_id']),
            'route_type': 'TD',
            'slot_number': 0,
            'km_start': int(data['odometer_start']),
            'km_end': int(data.get('odometer_end', 0)) or int(data['odometer_start']),
            'distance_km': int(data.get('estimated_km', 0)),
            'fuel_tank_capacity_liters': int(data.get('fuel_tank_capacity_liters', 0)),
            'fuel_gauge_start_level': data['fuel_gauge_start_level'],
            'fuel_gauge_end_level': data.get('fuel_gauge_end_level', data['fuel_gauge_start_level']),
            'fuel_start_liters': float(data.get('fuel_start_liters', 0)),
            'fuel_end_liters': float(data.get('fuel_end_liters', 0)),
            'fuel_consumed_liters': float(data.get('fuel_consumed_liters', 0)),
            'itinerary': data.get('itinerary', ''),
            'advisor_name': data['advisor_name'],
            'signature_ai_generated': data.get('advisor_signature', ''),
            'client_signature': data['client_signature'],
            'departure_datetime': data['departure_datetime'],
            'return_datetime': data.get('return_datetime'),
            'gdpr_consent': True,
            'inspection_acceptance': bool(data.get('inspection_acceptance')),
            'inspection_id': data.get('inspection_id'),
            'source': 'td_form',
            'status': 'FILLED',
        }

        contract = _fp_repo.create_from_td_form(contract_data)
        return jsonify({'success': True, 'contract': contract})

    except Exception as e:
        logger.exception('Failed to submit test drive form')
        return jsonify({'success': False, 'error': str(e)[:300]}), 500


@foi_parcurs_bp.route('/api/foi-parcurs/test-drive/<int:id>', methods=['GET'])
@login_required
def api_get_test_drive(id):
    """Get test drive form data for a contract."""
    contract = _fp_repo.get_contract_by_id(id)
    if not contract:
        return jsonify({'success': False, 'error': 'Not found'}), 404

    inspection = None
    if contract.get('inspection_id'):
        inspection = _inspection_repo.get_latest(contract['inspection_id'])

    return jsonify({
        'success': True,
        'contract': contract,
        'inspection': inspection,
    })
