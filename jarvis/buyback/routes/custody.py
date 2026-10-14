"""POST /api/buyback/records/<id>/custody — take a failed (LOST) buyback onto
custody (consignment): create a CarPark vehicle (is_consignment, source
CUSTODIE, no purchase price) and record the custody agreement. Mirrors
finalize.py's guard ordering; the accepted-decision machinery does not apply
(the record is already terminal LOST)."""
import decimal
from datetime import date

from flask import jsonify, request
from flask_login import login_required, current_user

from buyback import buyback_bp
from buyback.routes import _shared
from buyback import lifecycle
from buyback.services.carpark_handoff import handoff_to_carpark_custody
from core.roles.decorators import v2_permission_required


def validate_custody_agreement(data: dict) -> dict:
    """Validate + coerce the custody-agreement payload. Returns a new dict with
    the stored fields; raises ValueError(message) on the first invalid value
    (route catches → 400). Only commission_type + commission_value are
    required; money/date fields are optional."""
    data = data or {}
    ctype = data.get('commission_type')
    if ctype not in ('percent', 'fixed'):
        raise ValueError("commission_type must be 'percent' or 'fixed'")

    if data.get('commission_value') is None:
        raise ValueError('commission_value is required')
    try:
        cval = decimal.Decimal(str(data['commission_value']))
    except (decimal.InvalidOperation, TypeError, ValueError):
        raise ValueError('commission_value must be numeric')
    if cval < 0:
        raise ValueError('commission_value must be >= 0')
    if ctype == 'percent' and cval > 100:
        raise ValueError('commission_value (percent) must be between 0 and 100')

    out = {
        'commission_type': ctype,
        'commission_value': cval,
        'currency': (data.get('currency') or 'EUR'),
        'owner_price': None,
        'min_sale_price': None,
        'contract_number': data.get('contract_number'),
        'agreement_date': None,
        'expiry_date': None,
    }
    if isinstance(out['contract_number'], (dict, list)):
        raise ValueError('contract_number must be a plain string')

    for fld in ('owner_price', 'min_sale_price'):
        if data.get(fld) is not None:
            try:
                v = decimal.Decimal(str(data[fld]))
            except (decimal.InvalidOperation, TypeError, ValueError):
                raise ValueError(f'{fld} must be numeric')
            if v < 0:
                raise ValueError(f'{fld} must be >= 0')
            out[fld] = v

    for fld in ('agreement_date', 'expiry_date'):
        if data.get(fld):
            try:
                out[fld] = date.fromisoformat(str(data[fld]))
            except (TypeError, ValueError):
                raise ValueError(f'{fld} must be an ISO date (YYYY-MM-DD)')

    if out['agreement_date'] and out['expiry_date'] and out['expiry_date'] < out['agreement_date']:
        raise ValueError('expiry_date must be on or after agreement_date')

    return out


@buyback_bp.route('/records/<int:record_id>/custody', methods=['POST'])
@login_required
@v2_permission_required('buyback', 'record', 'custody')
def transfer_to_custody(record_id):
    record = _shared.records_repo.get_by_id(record_id)
    if not record:
        return jsonify({'success': False, 'error': 'Record not found'}), 404

    err = _shared._guard_company(record)
    if err:
        return err

    if record['status'] != lifecycle.LOST:
        return jsonify({
            'success': False,
            'error': f"Only LOST records can be taken on custody "
                     f"(record is {record['status']!r})",
        }), 409

    if record.get('carpark_vehicle_id') is not None:
        return jsonify({'success': False, 'error': 'Record already transferred to custody'}), 409

    try:
        agreement = validate_custody_agreement(request.get_json(silent=True) or {})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    try:
        vehicle = handoff_to_carpark_custody(record, agreement, current_user.id)
    except ValueError as e:
        # dup/invalid VIN — the car's VIN already lives in CarPark (same orphan
        # window the BOUGHT hand-off accepts). Record left unlinked, retryable.
        return jsonify({'success': False, 'error': str(e)}), 409

    updated = _shared.records_repo.update(record_id, {'carpark_vehicle_id': vehicle['id']})
    return jsonify({
        'success': True,
        'record': _shared._serialize(updated),
        'vehicle': _shared._serialize(vehicle),
    }), 200
