"""Routes for foi de parcurs contract generation workflow."""

import re
import time
import uuid
from datetime import datetime
from ._shared import (
    foi_parcurs_bp, jsonify, request, login_required, current_user,
    logger, _fp_repo, _client_repo, _vehicle_repo, log_history, log_status_change,
)
from core.roles.decorators import v2_permission_required
from ..services.fuel_service import calculate_fuel_distribution
from ..services.route_service import calculate_route_assignments
from ..services.signature_service import generate_ai_signature


# ════════════════════════════════════════════════════════════════
# Preview — route assignments + fuel distribution
# ════════════════════════════════════════════════════════════════

@foi_parcurs_bp.route('/api/foi-parcurs/preview', methods=['POST'])
@login_required
def api_preview():
    """Takes batch config, returns route assignments + fuel distribution preview."""
    data = request.get_json(silent=True) or {}

    required = [
        'vin', 'odometer_start', 'odometer_end', 'num_td', 'num_comodat',
        'fuel_tank_capacity_liters',
        'fuel_gauge_start_level', 'fuel_gauge_end_level',
        'total_consumption_period_liters',
    ]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({'success': False, 'error': f'Missing fields: {", ".join(missing)}'}), 400

    try:
        num_td = int(data['num_td'])
        num_comodat = int(data['num_comodat'])
        odometer_start = int(data['odometer_start'])
        odometer_end = int(data['odometer_end'])
        fuel_tank = int(data['fuel_tank_capacity_liters'])
        total_consumption = float(data['total_consumption_period_liters'])
    except (ValueError, TypeError) as e:
        return jsonify({'success': False, 'error': f'Invalid numeric value: {e}'}), 400

    try:
        assignments = calculate_route_assignments(
            num_td=num_td,
            num_comodat=num_comodat,
            odometer_start=odometer_start,
            odometer_end=odometer_end,
        )
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    try:
        fuel_distribution = calculate_fuel_distribution(
            fuel_tank_capacity_liters=fuel_tank,
            fuel_gauge_start_level=data['fuel_gauge_start_level'],
            fuel_gauge_end_level=data['fuel_gauge_end_level'],
            total_consumption_period_liters=total_consumption,
            distances_per_client=assignments['distances'],
        )
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    return jsonify({
        'success': True,
        'assignments': assignments,
        'fuel_distribution': fuel_distribution,
    })


# ════════════════════════════════════════════════════════════════
# Create single contract (called iteratively per client)
# ════════════════════════════════════════════════════════════════

@foi_parcurs_bp.route('/api/foi-parcurs/contracts', methods=['POST'])
@login_required
def api_create_contract():
    """Fill a single contract — called iteratively per client."""
    data = request.get_json(silent=True) or {}

    required = [
        'vin', 'company_id', 'client_id', 'route_type', 'km_start', 'km_end',
        'distance_km', 'fuel_tank_capacity_liters', 'fuel_gauge_start_level',
        'fuel_gauge_end_level', 'fuel_start_liters', 'fuel_end_liters',
        'fuel_consumed_liters', 'advisor_name', 'slot_number',
    ]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({'success': False, 'error': f'Missing fields: {", ".join(missing)}'}), 400

    # Validate route_type
    route_type = data['route_type']
    if route_type not in ('TD', 'Comodat'):
        return jsonify({'success': False, 'error': 'route_type must be TD or Comodat'}), 400

    # Generate contract_id: {VIN}_{unix_timestamp}_{slot_number}
    contract_id = f"{data['vin']}_{int(time.time())}_{data['slot_number']}"

    try:
        contract_data = {
            'contract_id': contract_id,
            'vin': data['vin'],
            'company_id': int(data['company_id']),
            'client_id': int(data['client_id']),
            'route_type': route_type,
            'km_start': int(data['km_start']),
            'km_end': int(data['km_end']),
            'distance_km': int(data['distance_km']),
            'fuel_tank_capacity_liters': int(data['fuel_tank_capacity_liters']),
            'fuel_gauge_start_level': data['fuel_gauge_start_level'],
            'fuel_gauge_end_level': data['fuel_gauge_end_level'],
            'fuel_start_liters': float(data['fuel_start_liters']),
            'fuel_end_liters': float(data['fuel_end_liters']),
            'fuel_consumed_liters': float(data['fuel_consumed_liters']),
            'itinerary': data.get('itinerary', ''),
            'advisor_name': data['advisor_name'],
            'signature_ai_generated': data.get('signature_svg', ''),
            'status': 'FILLED',
        }

        contract = _fp_repo.create_contract(contract_data)

        # Create audit entry (immutable log matching foi_de_parcurs_audit schema)
        assignment_rule = data.get('assignment_rule', '')
        total_consumption = float(data.get('total_consumption_period_liters', 0))
        audit_data = {
            'contract_id': contract_id,
            'vin': data['vin'],
            'client_id': int(data['client_id']),
            'company_id': int(data['company_id']),
            'assigned_route_type': route_type,
            'assignment_rule': assignment_rule,
            'fuel_allocation_method': 'PROPORTIONAL_DISTANCE',
            'fuel_start_liters': float(data['fuel_start_liters']),
            'fuel_end_liters': float(data['fuel_end_liters']),
            'fuel_consumed_liters': float(data['fuel_consumed_liters']),
            'total_consumption_period_liters': total_consumption,
            'reasoning': (
                f"Slot {data['slot_number']}: {route_type} assignment via {assignment_rule}, "
                f"km {data['km_start']}-{data['km_end']}, "
                f"fuel {data['fuel_start_liters']}L->{data['fuel_end_liters']}L"
            ),
            'status': 'FILLED',
        }
        try:
            _fp_repo.create_audit_entry(audit_data)
        except Exception:
            logger.exception('Failed to create audit entry for contract %s', contract_id)

        # Update client counters
        try:
            _client_repo.update_client_counters(int(data['client_id']), route_type)
        except Exception:
            logger.exception('Failed to update counters for client %s', data['client_id'])

        return jsonify({'success': True, 'contract': contract})

    except Exception as e:
        logger.exception('Failed to create contract')
        return jsonify({'success': False, 'error': str(e)[:300]}), 500


# ════════════════════════════════════════════════════════════════
# List contracts (paginated)
# ════════════════════════════════════════════════════════════════

@foi_parcurs_bp.route('/api/foi-parcurs/contracts', methods=['GET'])
@login_required
def api_list_contracts():
    """List contracts with pagination + server-side filters."""
    vin = request.args.get('vin')
    company_id = request.args.get('company_id', type=int)
    status = (request.args.get('status') or '').strip() or None
    route_type = (request.args.get('route_type') or '').strip() or None
    document_type = (request.args.get('document_type') or '').strip() or None
    date_from = (request.args.get('date_from') or '').strip() or None
    date_to = (request.args.get('date_to') or '').strip() or None
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    sort_by = request.args.get('sort_by', 'created_at')
    sort_dir = request.args.get('sort_dir', 'DESC')

    # Rows are lean (~1 kB each), so a generous cap is safe and lets the client
    # pull a whole company's history in one page; push filters server-side to
    # keep it bounded as data grows.
    per_page = min(max(per_page, 1), 2000)

    contracts, total = _fp_repo.get_contracts(
        vin=vin, company_id=company_id,
        status=status, route_type=route_type,
        document_type=document_type,
        date_from=date_from, date_to=date_to,
        page=page, per_page=per_page,
        sort_by=sort_by, sort_dir=sort_dir,
        lean=True,  # list never renders the base64 blobs — drop ~155 kB/row
    )

    return jsonify({
        'contracts': contracts,
        'total': total,
        'page': page,
        'per_page': per_page,
    })


# ════════════════════════════════════════════════════════════════
# Single contract detail
# ════════════════════════════════════════════════════════════════

@foi_parcurs_bp.route('/api/foi-parcurs/contracts/<int:id>', methods=['GET'])
@login_required
def api_contract_detail(id):
    """Single contract detail."""
    contract = _fp_repo.get_contract_by_id(id)
    if not contract:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return jsonify({'success': True, 'contract': contract})


def _is_admin():
    """Admin / superadmin — gates the destructive registration actions below."""
    return getattr(current_user, 'role_name', '').lower() in ('admin', 'superadmin')


@foi_parcurs_bp.route('/api/foi-parcurs/contracts/<int:id>', methods=['DELETE'])
@login_required
def api_delete_contract(id):
    """Permanently delete a registration (foi_de_parcurs row).

    Admins may delete any registration. Non-admins may delete only an INTERNAL
    driving-log session that belongs to their OWN company (self-service cleanup
    of an internal QuickSession) — never a client Test Drive, a batch
    registration, or another company's session. The company check matters
    because the session list is group-wide (unscoped reads), so without it any
    employee could delete a sibling company's internal log by id (IDOR).
    Session-event history is removed via the FK's ON DELETE CASCADE."""
    contract = _fp_repo.get_contract_by_id(id)
    if not contract:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    if not _is_admin():
        own_company = getattr(current_user, 'company_id', None)
        if (not contract.get('is_internal')
                or own_company is None
                or contract.get('company_id') != own_company):
            return jsonify({'success': False, 'error': 'Not allowed'}), 403
    _fp_repo.delete_contract(id)
    logger.info('foi-parcurs contract %s deleted by %s', id, getattr(current_user, 'email', '?'))
    return jsonify({'success': True})


def _parse_dt(v):
    """Best-effort ISO parse for date-order validation, returned as a NAIVE
    datetime (tzinfo stripped). DB timestamptz values come back tz-aware via
    dict_from_row.isoformat(), while frontend datetime-local values are naive —
    comparing the two directly raises TypeError, so normalize both to naive.
    None if absent/unparseable."""
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace('Z', '+00:00'))
    except ValueError:
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


@foi_parcurs_bp.route('/api/foi-parcurs/contracts/<int:id>/correct', methods=['PUT'])
@login_required
@v2_permission_required('test_drive', 'contracts', 'correct')
def api_correct_contract(id):
    """Correct a session's drive date(s) and/or odometer readings to fix data-entry
    anomalies (date↔odometer inversions, overlapping km). Gated by the role-matrix
    permission test_drive.contracts.correct (admins bypass; granted to Admin + Viewer
    by default). Works on any status; does NOT change the status. Validates
    km_end >= km_start and return >= departure against the resulting values."""
    contract = _fp_repo.get_contract_by_id(id)
    if not contract:
        return jsonify({'success': False, 'error': 'Not found'}), 404

    data = request.get_json(silent=True) or {}
    fields = {}
    for k in ('km_start', 'km_end'):
        if k in data and data[k] not in (None, ''):
            try:
                fields[k] = int(data[k])
            except (TypeError, ValueError):
                return jsonify({'success': False, 'error': f'{k} must be a number'}), 400
    for k in ('departure_datetime', 'return_datetime'):
        if k in data:
            fields[k] = data[k] or None

    # Consilier change (light-correction). Non-empty only — a blank advisor must
    # never wipe the existing one.
    if 'advisor_name' in data:
        advisor = (data.get('advisor_name') or '').strip()
        if advisor:
            fields['advisor_name'] = advisor

    if not fields:
        return jsonify({'success': False, 'error': 'No fields to correct'}), 400

    # Reject malformed dates with a clean 400 rather than letting the raw string
    # reach the timestamptz column and blow up as a 500.
    for k in ('departure_datetime', 'return_datetime'):
        if fields.get(k) and _parse_dt(fields[k]) is None:
            return jsonify({'success': False, 'error': f'{k} is not a valid datetime'}), 400

    # Odometer sanity on the resulting state (new value, else the stored one).
    eff_start = fields.get('km_start', contract.get('km_start'))
    eff_end = fields.get('km_end', contract.get('km_end'))
    if eff_start is not None and eff_end is not None and eff_end < eff_start:
        return jsonify({'success': False,
                        'error': f'km_end ({eff_end}) cannot be less than km_start ({eff_start})'}), 400

    # Date sanity on the resulting state (return not before departure).
    eff_dep = _parse_dt(fields['departure_datetime'] if 'departure_datetime' in fields
                        else contract.get('departure_datetime'))
    eff_ret = _parse_dt(fields['return_datetime'] if 'return_datetime' in fields
                        else contract.get('return_datetime'))
    if eff_dep and eff_ret and eff_ret < eff_dep:
        return jsonify({'success': False,
                        'error': 'return_datetime cannot be before departure_datetime'}), 400

    updated = _fp_repo.correct_session(id, fields, getattr(current_user, 'email', None))
    log_history(id, 'correct')
    # If the correction moved the window so the car is currently out (departure
    # passed, return in the future), revive a MISSED / late-PLANNED session to
    # FILLED — it now reads "În desfășurare" (the Modificat marker stays). Log
    # the status transition for the Istoric audit trail.
    revived = _fp_repo.revive_to_active_if_window_open(id)
    if revived:
        log_status_change(id, contract.get('status'), 'FILLED')
        updated = revived
    logger.info('foi-parcurs contract %s corrected by admin %s: %s',
                id, getattr(current_user, 'email', '?'), fields)

    # Keep the vehicle's odometer floor honest if km_end was raised (mirrors return).
    try:
        if 'km_end' in fields and contract.get('vin'):
            veh = _vehicle_repo.get_by_vin(contract['vin'])
            if veh and (veh.get('odometer_km') is None or fields['km_end'] > veh['odometer_km']):
                _vehicle_repo.update(veh['id'], {'odometer_km': fields['km_end']})
    except Exception:
        logger.warning('Could not advance vehicle odometer after correcting contract %s', id, exc_info=True)

    return jsonify({'success': True, 'contract': updated})


@foi_parcurs_bp.route('/api/foi-parcurs/contracts/<int:id>/drive-type', methods=['PUT'])
@login_required
@v2_permission_required('test_drive', 'contracts', 'drive_type')
def api_set_drive_type(id):
    """Reclassify a session between internal (company driving) and external
    (client) — a cleaning tool for sessions a colleague mis-marked. Gated by the
    role-matrix permission test_drive.contracts.drive_type (admins bypass; Admin
    granted by default). Flag-only: client identity is left intact, so the change
    is reversible with one more flip. Logs `mark_internal` / `mark_external`."""
    contract = _fp_repo.get_contract_by_id(id)
    if not contract:
        return jsonify({'success': False, 'error': 'Not found'}), 404

    data = request.get_json(silent=True) or {}
    # Strict boolean — reject 1/"true"/None so a bad payload can't corrupt the flag.
    if not isinstance(data.get('is_internal'), bool):
        return jsonify({'success': False, 'error': 'is_internal (boolean) is required'}), 400
    is_internal = data['is_internal']

    updated = _fp_repo.set_internal_flag(id, is_internal, getattr(current_user, 'email', None))
    log_history(id, 'mark_internal' if is_internal else 'mark_external')
    logger.info('foi-parcurs contract %s marked %s by %s', id,
                'internal' if is_internal else 'external', getattr(current_user, 'email', '?'))
    return jsonify({'success': True, 'contract': updated})


@foi_parcurs_bp.route('/api/foi-parcurs/contracts/<int:id>/reset', methods=['POST'])
@login_required
def api_reset_contract(id):
    """Admin-only: reset a completed Test Drive back to 'driving' (clears the
    return data) so the return flow can be re-tested."""
    if not _is_admin():
        return jsonify({'success': False, 'error': 'Admin access required'}), 403
    contract = _fp_repo.get_contract_by_id(id)
    if not contract:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    if contract.get('route_type') != 'TD':
        return jsonify({'success': False, 'error': 'Only Test Drive registrations can be reset'}), 400
    updated = _fp_repo.reset_return(id)
    log_history(id, 'reset')
    log_status_change(id, contract.get('status'), 'FILLED')
    logger.info('foi-parcurs contract %s reset to driving by admin %s', id, getattr(current_user, 'email', '?'))
    return jsonify({'success': True, 'contract': updated})


# ════════════════════════════════════════════════════════════════
# Save Batch — persist preview as PENDING contracts
# ════════════════════════════════════════════════════════════════

@foi_parcurs_bp.route('/api/foi-parcurs/batches', methods=['POST'])
@login_required
def api_save_batch():
    """Save a previewed batch as PENDING contracts (no clients yet)."""
    data = request.get_json(silent=True) or {}
    config = data.get('config', {})
    preview = data.get('preview', {})

    if not config or not preview:
        return jsonify({'success': False, 'error': 'config and preview are required'}), 400

    vin = config.get('vin', '')
    company_id = int(config.get('company_id', 0))
    year = config.get('year')
    month = config.get('month')
    fuel_tank = int(config.get('fuel_tank_capacity_liters', 0))
    fuel_start_level = config.get('fuel_gauge_start_level', '1')
    fuel_end_level = config.get('fuel_gauge_end_level', '1/2')
    total_consumption = float(config.get('total_consumption_period_liters', 0))

    assignments = preview.get('assignments', {})
    fuel_dist = preview.get('fuel_distribution', {})
    clients = assignments.get('clients', [])
    per_client_fuel = fuel_dist.get('per_client', [])

    if not clients:
        return jsonify({'success': False, 'error': 'No contracts in preview'}), 400

    batch_id = f"B-{vin}-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    created = 0

    try:
        for i, slot in enumerate(clients):
            fuel = per_client_fuel[i] if i < len(per_client_fuel) else {}
            contract_id = f"{vin}_{int(time.time())}_{slot.get('slot', i)}"
            contract_data = {
                'contract_id': contract_id,
                'batch_id': batch_id,
                'vin': vin,
                'company_id': company_id,
                'year': year,
                'month': month,
                'route_type': slot.get('route_type', 'TD'),
                'slot_number': slot.get('slot', i),
                'km_start': int(slot.get('km_start', 0)),
                'km_end': int(slot.get('km_end', 0)),
                'distance_km': int(slot.get('distance_km', 0)),
                'fuel_tank_capacity_liters': fuel_tank,
                'fuel_gauge_start_level': fuel_start_level,
                'fuel_gauge_end_level': fuel_end_level,
                'fuel_start_liters': float(fuel.get('fuel_start_liters', 0)),
                'fuel_end_liters': float(fuel.get('fuel_end_liters', 0)),
                'fuel_consumed_liters': float(fuel.get('fuel_consumed_liters', 0)),
                'status': 'PENDING',
            }
            _fp_repo.create_contract(contract_data)
            created += 1

        return jsonify({'success': True, 'batch_id': batch_id, 'count': created})

    except Exception as e:
        logger.exception('Failed to save batch %s', batch_id)
        return jsonify({'success': False, 'error': str(e)[:300]}), 500


# ════════════════════════════════════════════════════════════════
# Allocate client to a PENDING contract
# ════════════════════════════════════════════════════════════════

@foi_parcurs_bp.route('/api/foi-parcurs/contracts/<int:id>/allocate', methods=['PUT'])
@login_required
def api_allocate_client(id):
    """Allocate a client + itinerary + advisor to a PENDING contract."""
    data = request.get_json(silent=True) or {}
    client_id = data.get('client_id')
    itinerary = data.get('itinerary', '')
    advisor_name = data.get('advisor_name', '')
    signature_svg = data.get('signature_svg', '')

    if not client_id:
        return jsonify({'success': False, 'error': 'client_id is required'}), 400

    contract = _fp_repo.get_contract_by_id(id)
    if not contract:
        return jsonify({'success': False, 'error': 'Contract not found'}), 404

    try:
        update_data: dict = {
            'client_id': int(client_id),
            'status': 'FILLED',
        }
        # Only overwrite if provided (don't blank out existing values)
        if itinerary:
            update_data['itinerary'] = itinerary
        if advisor_name:
            update_data['advisor_name'] = advisor_name
        if signature_svg:
            update_data['signature_ai_generated'] = signature_svg

        updated = _fp_repo.allocate_client(id, update_data)
        log_history(id, 'allocate')
        return jsonify({'success': True, 'contract': updated})
    except Exception as e:
        logger.exception('Failed to allocate client to contract %s', id)
        return jsonify({'success': False, 'error': str(e)[:300]}), 500


# ════════════════════════════════════════════════════════════════
# AI Signature generation
# ════════════════════════════════════════════════════════════════

@foi_parcurs_bp.route('/api/foi-parcurs/signature', methods=['POST'])
@login_required
def api_generate_signature():
    """Generate AI signature SVG."""
    data = request.get_json(silent=True) or {}
    advisor_name = (data.get('advisor_name') or '').strip()
    if not advisor_name:
        return jsonify({'success': False, 'error': 'advisor_name is required'}), 400

    variant = data.get('variant', 1)
    try:
        variant = int(variant)
    except (ValueError, TypeError):
        variant = 1

    svg = generate_ai_signature(advisor_name, variant)
    return jsonify({'success': True, 'svg': svg})
