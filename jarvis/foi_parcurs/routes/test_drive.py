"""Routes for Test Drive form submission."""
import json
import re
import time
import uuid
from ._shared import (
    foi_parcurs_bp, jsonify, request, login_required, current_user,
    logger, _fp_repo, _inspection_repo, _crm_client_repo, _vehicle_repo,
)
from ..services.fuel_service import parse_fuel_level

_PHONE_RE = re.compile(r'^(07\d{8}|\+40\d{9}|004\d{10})$')


def _normalize_name(name: str) -> str:
    """Lowercase + collapse whitespace for crm_clients.name_normalized (trigram-indexed)."""
    return re.sub(r'\s+', ' ', (name or '').strip().lower())


@foi_parcurs_bp.route('/api/foi-parcurs/test-drive', methods=['POST'])
@login_required
def api_submit_test_drive():
    """Submit test drive form — creates FILLED contract."""
    data = request.get_json(silent=True) or {}

    # `itinerary` is intentionally NOT required — the mobile Test Drive form
    # dropped the Traseu/Itinerariu field. It's still stored when provided
    # (e.g. by the web form) via data.get('itinerary', '') below.
    required = ['company_id', 'vin', 'client_id', 'odometer_start', 'estimated_km',
                'fuel_gauge_start_level', 'departure_datetime',
                'advisor_name', 'client_signature', 'gdpr_consent']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({'success': False, 'error': f'Missing: {", ".join(missing)}'}), 400

    if not data.get('gdpr_consent'):
        return jsonify({'success': False, 'error': 'GDPR consent is required'}), 400

    contract_id = f"TD-{data['vin'][:8]}-{int(time.time())}-{uuid.uuid4().hex[:4]}"

    try:
        # Derive fuel liters from gauge levels × tank capacity (single source of truth).
        tank = int(data.get('fuel_tank_capacity_liters', 0))
        start_level = data['fuel_gauge_start_level']
        end_level = data.get('fuel_gauge_end_level', start_level)
        try:
            start_fraction = parse_fuel_level(str(start_level))
            end_fraction = parse_fuel_level(str(end_level))
        except ValueError:
            start_fraction, end_fraction = 1.0, 1.0
        fuel_start_liters = round(start_fraction * tank, 2)
        fuel_end_liters = round(end_fraction * tank, 2)
        fuel_consumed_liters = round(max(0.0, fuel_start_liters - fuel_end_liters), 2)

        # Client comes from the CRM (crm_clients), not the legacy fp_clients table.
        # Resolve name/phone now and store them directly on the contract so old
        # contracts (joined via fp_clients) and new ones (CRM-sourced) both resolve.
        client_id = int(data['client_id'])
        crm_client = _crm_client_repo.get_by_id(client_id)
        client_name = crm_client.get('display_name') if crm_client else None
        client_phone = crm_client.get('phone') if crm_client else None

        # Structured vehicle-condition report captured at handover (optional).
        departure_damage = data.get('departure_damage') or []
        if not isinstance(departure_damage, list):
            return jsonify({'success': False, 'error': 'departure_damage must be a list'}), 400

        contract_data = {
            'contract_id': contract_id,
            'vin': data['vin'],
            'registration_number': data.get('registration_number', ''),
            'company_id': int(data['company_id']),
            'client_id': client_id,
            'client_name': client_name,
            'client_phone': client_phone,
            'route_type': 'TD',
            'slot_number': 0,
            'km_start': int(data['odometer_start']),
            'km_end': int(data.get('odometer_end', 0)) or int(data['odometer_start']),
            'distance_km': int(data.get('estimated_km', 0)),
            'fuel_tank_capacity_liters': tank,
            'fuel_gauge_start_level': start_level,
            'fuel_gauge_end_level': end_level,
            'fuel_start_liters': fuel_start_liters,
            'fuel_end_liters': fuel_end_liters,
            'fuel_consumed_liters': fuel_consumed_liters,
            'itinerary': data.get('itinerary', ''),
            'advisor_name': data['advisor_name'],
            'signature_ai_generated': data.get('advisor_signature', ''),
            'client_signature': data['client_signature'],
            'departure_datetime': data['departure_datetime'],
            'return_datetime': data.get('return_datetime'),
            'departure_damage': json.dumps(departure_damage),
            'driver_license_photo': data.get('driver_license_photo'),
            'driver_license_number': data.get('driver_license_number'),
            'gdpr_consent': True,
            'inspection_acceptance': bool(data.get('inspection_acceptance')),
            'inspection_id': data.get('inspection_id'),
            'source': 'td_form',
            'status': 'FILLED',
        }

        contract = _fp_repo.create_from_td_form(contract_data)

        # Generate PDFs
        try:
            from ..services.pdf_service import generate_legal_pdf, generate_custom_pdf
            legal_path = generate_legal_pdf(contract)
            custom_path = generate_custom_pdf(contract)
            _fp_repo.execute(
                'UPDATE foi_de_parcurs SET pdf_legal_path = %s, pdf_custom_path = %s WHERE id = %s',
                (legal_path, custom_path, contract['id']),
            )
            contract['pdf_legal_path'] = legal_path
            contract['pdf_custom_path'] = custom_path
        except Exception:
            logger.exception('PDF generation failed for contract %s', contract.get('contract_id'))

        return jsonify({'success': True, 'contract': contract})

    except Exception as e:
        logger.exception('Failed to submit test drive form')
        return jsonify({'success': False, 'error': str(e)[:300]}), 500


@foi_parcurs_bp.route('/api/foi-parcurs/test-drive/<int:id>/return', methods=['PUT'])
@login_required
def api_return_test_drive(id):
    """Complete a test drive by recording return data (km/fuel/damage/signatures)."""
    data = request.get_json(silent=True) or {}

    try:
        contract = _fp_repo.get_contract_by_id(id)
        if not contract:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        if contract.get('route_type') != 'TD':
            return jsonify({'success': False, 'error': 'Contract is not a Test Drive'}), 400

        advisor_signature = data.get('advisor_signature')
        client_signature = data.get('client_signature')
        if not advisor_signature or not client_signature:
            return jsonify({
                'success': False,
                'error': 'Both advisor_signature and client_signature are required',
            }), 400

        km_end = data.get('km_end')
        if km_end is None:
            return jsonify({'success': False, 'error': 'km_end is required'}), 400
        try:
            km_end = int(km_end)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'km_end must be a number'}), 400

        km_start = contract.get('km_start')
        if km_start is not None and km_end < km_start:
            return jsonify({
                'success': False,
                'error': f'km_end ({km_end}) cannot be less than km_start ({km_start})',
            }), 400

        return_damage = data.get('return_damage') or []
        if not isinstance(return_damage, list):
            return jsonify({'success': False, 'error': 'return_damage must be a list'}), 400

        update_data = {
            'km_end': km_end,
            'fuel_gauge_end_level': data.get('fuel_gauge_end_level'),
            'return_datetime': data.get('return_datetime'),
            'return_damage': return_damage,
            'return_notes': data.get('return_notes'),
            'return_advisor_signature': advisor_signature,
            'return_client_signature': client_signature,
        }

        updated = _fp_repo.record_return(id, update_data)

        # Advance the vehicle's stored odometer to the latest reading (never backwards)
        try:
            vin = contract.get('vin')
            if vin:
                veh = _vehicle_repo.get_by_vin(vin)
                if veh and (veh.get('odometer_km') is None or km_end > veh['odometer_km']):
                    _vehicle_repo.update(veh['id'], {'odometer_km': km_end})
        except Exception:
            logger.warning('Could not advance vehicle odometer after return for contract %s', id, exc_info=True)

        return jsonify({'success': True, 'contract': updated})

    except Exception as e:
        logger.exception('Failed to record test drive return for contract %s', id)
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


@foi_parcurs_bp.route('/api/foi-parcurs/driver-license/ocr', methods=['POST'])
@login_required
def api_driver_license_ocr():
    """Extract structured fields from a driving-license photo via Claude vision.

    Body: {"image": "data:image/jpeg;base64,..."} (or bare base64).
    Returns {success, data: {last_name, first_name, full_name, cnp,
    license_number, birth_date, expiry_date, address, city, county}}.
    """
    data = request.get_json(silent=True) or {}
    image = data.get('image')
    if not image:
        return jsonify({'success': False, 'error': 'image is required'}), 400

    try:
        from ..services.license_ocr_service import extract_license_data
        fields = extract_license_data(image)
        return jsonify({'success': True, 'data': fields})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.exception('Driver-license OCR failed')
        return jsonify({'success': False, 'error': str(e)[:300]}), 500


@foi_parcurs_bp.route('/api/foi-parcurs/crm-clients', methods=['POST'])
@login_required
def api_create_crm_client():
    """Create a CRM client from the mobile Test Drive form (login-gated, so the
    consilier can create one without full CRM access). Returns the new client."""
    data = request.get_json(silent=True) or {}

    display_name = (data.get('display_name') or data.get('name') or '').strip()
    if not display_name:
        return jsonify({'success': False, 'error': 'display_name is required'}), 400

    phone = (data.get('phone') or '').strip()
    phone_clean = phone.replace(' ', '').replace('-', '')
    if not _PHONE_RE.match(phone_clean):
        return jsonify({
            'success': False,
            'error': 'Invalid phone. Must start with 07, +40, or 004',
        }), 400

    cnp = (data.get('cnp') or '').strip() or None
    address = (data.get('address') or '').strip() or None
    city = (data.get('city') or '').strip() or None
    county = (data.get('county') or '').strip() or None
    email = (data.get('email') or '').strip() or None
    is_company = bool(data.get('is_company'))
    company_name = (data.get('company_name') or '').strip() or None
    cui = (data.get('cui') or '').strip() or None

    try:
        row = _crm_client_repo.create(
            display_name=display_name,
            name_normalized=_normalize_name(display_name),
            client_type='company' if is_company else 'person',
            phone=phone_clean,
            phone_raw=phone,
            email=email,
            street=address,
            city=city,
            region=county,
            company_name=company_name,
            cui=cui,
            source_flags={'foi_parcurs': True},
        )
        new_id = row['id'] if row else None
        if new_id and cnp:
            _crm_client_repo.execute(
                'UPDATE crm_clients SET cnp = %s WHERE id = %s', (cnp, new_id)
            )
        client = _crm_client_repo.get_by_id(new_id) if new_id else None
        return jsonify({'success': True, 'client': client})
    except Exception as e:
        logger.exception('Failed to create CRM client from Test Drive form')
        return jsonify({'success': False, 'error': str(e)[:300]}), 500
