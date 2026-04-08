"""Cost & Revenue API routes — CRUD for vehicle financial tracking."""
import logging

from flask import request, jsonify
from flask_login import login_required, current_user

from carpark import carpark_bp
from carpark.services.vehicle_service import VehicleService
from carpark.routes.vehicles import (
    carpark_required, carpark_edit_required, _serialize, _verify_vehicle_ownership,
)

logger = logging.getLogger('jarvis.carpark')

_service = VehicleService()

VALID_COST_TYPES = {
    'repair', 'maintenance', 'insurance', 'registration', 'transport',
    'inspection', 'cleaning', 'fuel', 'parking', 'tax', 'other',
}

VALID_REVENUE_TYPES = {
    'sale', 'rental', 'lease', 'commission', 'refund', 'other',
}


# ═══════════════════════════════════════════════
# COSTS — LIST
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/costs', methods=['GET'])
@login_required
@carpark_required
def list_costs(vehicle_id):
    """List costs for a vehicle. Optional query: ?type=repair|maintenance|..."""
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err

    cost_type = request.args.get('type')
    if cost_type and cost_type not in VALID_COST_TYPES:
        return jsonify({'error': 'Invalid cost type'}), 400

    costs = _service.get_costs(vehicle_id, cost_type)
    return jsonify({'costs': _serialize(costs)})


# ═══════════════════════════════════════════════
# COSTS — CREATE
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/costs', methods=['POST'])
@login_required
@carpark_edit_required
def create_cost(vehicle_id):
    """Create a cost record.

    Body: { cost_type, amount, currency?, description?, vat_rate?, vat_amount?,
            invoice_number?, invoice_id?, supplier_name?, date?, ... }
    """
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    if data.get('cost_type') and data['cost_type'] not in VALID_COST_TYPES:
        return jsonify({'error': f'Invalid cost_type. Allowed: {", ".join(sorted(VALID_COST_TYPES))}'}), 400

    try:
        cost = _service.create_cost(vehicle_id, data, created_by=current_user.id)
        return jsonify({'cost': _serialize(cost)}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f'Cost creation failed: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500


# ═══════════════════════════════════════════════
# COSTS — UPDATE
# ═══════════════════════════════════════════════

@carpark_bp.route('/costs/<int:cost_id>', methods=['PUT'])
@login_required
@carpark_edit_required
def update_cost(cost_id):
    """Update a cost record."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    if data.get('cost_type') and data['cost_type'] not in VALID_COST_TYPES:
        return jsonify({'error': f'Invalid cost_type. Allowed: {", ".join(sorted(VALID_COST_TYPES))}'}), 400

    # Verify cost exists and vehicle belongs to user's company
    existing = _service.get_cost(cost_id)
    if not existing:
        return jsonify({'error': 'Cost not found'}), 404
    _, err = _verify_vehicle_ownership(existing['vehicle_id'])
    if err:
        return err

    cost = _service.update_cost(cost_id, data)
    if not cost:
        return jsonify({'error': 'No fields to update'}), 400
    return jsonify({'cost': _serialize(cost)})


# ═══════════════════════════════════════════════
# COSTS — DELETE
# ═══════════════════════════════════════════════

@carpark_bp.route('/costs/<int:cost_id>', methods=['DELETE'])
@login_required
@carpark_edit_required
def delete_cost(cost_id):
    """Delete a cost record."""
    existing = _service.get_cost(cost_id)
    if not existing:
        return jsonify({'error': 'Cost not found'}), 404
    _, err = _verify_vehicle_ownership(existing['vehicle_id'])
    if err:
        return err

    if _service.delete_cost(cost_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Cost not found'}), 404


# ═══════════════════════════════════════════════
# COSTS — TOTALS
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/costs/totals', methods=['GET'])
@login_required
@carpark_required
def cost_totals(vehicle_id):
    """Get cost totals grouped by type for a vehicle."""
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err
    totals = _service.get_cost_totals(vehicle_id)
    return jsonify(_serialize(totals))


# ═══════════════════════════════════════════════
# COST LINES — LIST
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/cost-lines', methods=['GET'])
@login_required
@carpark_required
def list_cost_lines(vehicle_id):
    """List all cost lines for a vehicle."""
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err
    lines = _service.get_cost_lines(vehicle_id)
    return jsonify({'cost_lines': _serialize(lines)})


# ═══════════════════════════════════════════════
# COST LINES — CREATE
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/cost-lines', methods=['POST'])
@login_required
@carpark_edit_required
def create_cost_line(vehicle_id):
    """Create a cost line. Body: {cost_type, description?, planned_amount?, currency?, notes?}"""
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body required'}), 400
    cost_type = data.get('cost_type')
    if not cost_type or cost_type not in VALID_COST_TYPES:
        return jsonify({'error': f'Invalid cost_type. Allowed: {", ".join(sorted(VALID_COST_TYPES))}'}), 400
    try:
        line_id = _service.create_cost_line(
            vehicle_id, cost_type,
            created_by=current_user.id,
            description=data.get('description'),
            planned_amount=data.get('planned_amount', 0),
            currency=data.get('currency', 'EUR'),
            notes=data.get('notes'),
        )
        return jsonify({'success': True, 'id': line_id}), 201
    except Exception as e:
        logger.error(f'Cost line creation failed: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500


# ═══════════════════════════════════════════════
# COST LINES — UPDATE
# ═══════════════════════════════════════════════

@carpark_bp.route('/cost-lines/<int:line_id>', methods=['PUT'])
@login_required
@carpark_edit_required
def update_cost_line(line_id):
    """Update a cost line."""
    line = _service.get_cost_line(line_id)
    if not line:
        return jsonify({'error': 'Cost line not found'}), 404
    _, err = _verify_vehicle_ownership(line['vehicle_id'])
    if err:
        return err
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body required'}), 400
    if data.get('cost_type') and data['cost_type'] not in VALID_COST_TYPES:
        return jsonify({'error': 'Invalid cost_type'}), 400
    _service.update_cost_line(line_id, **{
        k: v for k, v in data.items()
        if k in ('cost_type', 'description', 'planned_amount', 'currency', 'notes')
    })
    return jsonify({'success': True})


# ═══════════════════════════════════════════════
# COST LINES — DELETE
# ═══════════════════════════════════════════════

@carpark_bp.route('/cost-lines/<int:line_id>', methods=['DELETE'])
@login_required
@carpark_edit_required
def delete_cost_line(line_id):
    """Delete a cost line and all its child costs."""
    line = _service.get_cost_line(line_id)
    if not line:
        return jsonify({'error': 'Cost line not found'}), 404
    _, err = _verify_vehicle_ownership(line['vehicle_id'])
    if err:
        return err
    if _service.delete_cost_line(line_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Cost line not found'}), 404


# ═══════════════════════════════════════════════
# COST LINE → COSTS (children)
# ═══════════════════════════════════════════════

@carpark_bp.route('/cost-lines/<int:line_id>/costs', methods=['GET'])
@login_required
@carpark_required
def list_line_costs(line_id):
    """List cost entries under a cost line."""
    line = _service.get_cost_line(line_id)
    if not line:
        return jsonify({'error': 'Cost line not found'}), 404
    _, err = _verify_vehicle_ownership(line['vehicle_id'])
    if err:
        return err
    costs = _service.get_line_costs(line_id)
    return jsonify({'costs': _serialize(costs)})


@carpark_bp.route('/cost-lines/<int:line_id>/costs', methods=['POST'])
@login_required
@carpark_edit_required
def create_line_cost(line_id):
    """Create a cost entry under a cost line.

    Body: {amount, date?, description?, supplier_name?, vat_rate?, vat_amount?,
           invoice_number?, invoice_id?, ...}
    """
    line = _service.get_cost_line(line_id)
    if not line:
        return jsonify({'error': 'Cost line not found'}), 404
    _, err = _verify_vehicle_ownership(line['vehicle_id'])
    if err:
        return err
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body required'}), 400
    try:
        cost_id = _service.create_line_cost(line_id, data, created_by=current_user.id)
        return jsonify({'success': True, 'id': cost_id}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f'Line cost creation failed: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500


# ═══════════════════════════════════════════════
# INDIVIDUAL COST OPERATIONS (under a line)
# ═══════════════════════════════════════════════

@carpark_bp.route('/line-costs/<int:cost_id>', methods=['PUT'])
@login_required
@carpark_edit_required
def update_line_cost(cost_id):
    """Update a cost entry under a cost line."""
    existing = _service.get_cost(cost_id)
    if not existing:
        return jsonify({'error': 'Cost not found'}), 404
    _, err = _verify_vehicle_ownership(existing['vehicle_id'])
    if err:
        return err
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body required'}), 400
    _service.update_line_cost(cost_id, data)
    return jsonify({'success': True})


@carpark_bp.route('/line-costs/<int:cost_id>', methods=['DELETE'])
@login_required
@carpark_edit_required
def delete_line_cost(cost_id):
    """Delete a cost entry under a cost line."""
    existing = _service.get_cost(cost_id)
    if not existing:
        return jsonify({'error': 'Cost not found'}), 404
    _, err = _verify_vehicle_ownership(existing['vehicle_id'])
    if err:
        return err
    if _service.delete_line_cost(cost_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Cost not found'}), 404


@carpark_bp.route('/line-costs/<int:cost_id>/link-invoice', methods=['PUT'])
@login_required
@carpark_edit_required
def link_cost_invoice(cost_id):
    """Link or unlink an invoice to a cost entry. Body: {invoice_id: N|null}"""
    existing = _service.get_cost(cost_id)
    if not existing:
        return jsonify({'error': 'Cost not found'}), 404
    _, err = _verify_vehicle_ownership(existing['vehicle_id'])
    if err:
        return err
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({'error': 'Request body required'}), 400
    invoice_id = data.get('invoice_id')
    _service.link_cost_invoice(cost_id, invoice_id)
    return jsonify({'success': True})


# ═══════════════════════════════════════════════
# REVENUES — LIST
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/revenues', methods=['GET'])
@login_required
@carpark_required
def list_revenues(vehicle_id):
    """List revenues for a vehicle. Optional query: ?type=sale|rental|..."""
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err

    revenue_type = request.args.get('type')
    if revenue_type and revenue_type not in VALID_REVENUE_TYPES:
        return jsonify({'error': 'Invalid revenue type'}), 400

    revenues = _service.get_revenues(vehicle_id, revenue_type)
    return jsonify({'revenues': _serialize(revenues)})


# ═══════════════════════════════════════════════
# REVENUES — CREATE
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/revenues', methods=['POST'])
@login_required
@carpark_edit_required
def create_revenue(vehicle_id):
    """Create a revenue record.

    Body: { revenue_type, amount, currency?, description?, vat_amount?,
            invoice_number?, invoice_id?, client_name?, date? }
    """
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    if data.get('revenue_type') and data['revenue_type'] not in VALID_REVENUE_TYPES:
        return jsonify({'error': f'Invalid revenue_type. Allowed: {", ".join(sorted(VALID_REVENUE_TYPES))}'}), 400

    try:
        revenue = _service.create_revenue(vehicle_id, data, created_by=current_user.id)
        return jsonify({'revenue': _serialize(revenue)}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f'Revenue creation failed: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500


# ═══════════════════════════════════════════════
# REVENUES — UPDATE
# ═══════════════════════════════════════════════

@carpark_bp.route('/revenues/<int:revenue_id>', methods=['PUT'])
@login_required
@carpark_edit_required
def update_revenue(revenue_id):
    """Update a revenue record."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    if data.get('revenue_type') and data['revenue_type'] not in VALID_REVENUE_TYPES:
        return jsonify({'error': f'Invalid revenue_type. Allowed: {", ".join(sorted(VALID_REVENUE_TYPES))}'}), 400

    existing = _service.get_revenue(revenue_id)
    if not existing:
        return jsonify({'error': 'Revenue not found'}), 404
    _, err = _verify_vehicle_ownership(existing['vehicle_id'])
    if err:
        return err

    revenue = _service.update_revenue(revenue_id, data)
    if not revenue:
        return jsonify({'error': 'No fields to update'}), 400
    return jsonify({'revenue': _serialize(revenue)})


# ═══════════════════════════════════════════════
# REVENUES — DELETE
# ═══════════════════════════════════════════════

@carpark_bp.route('/revenues/<int:revenue_id>', methods=['DELETE'])
@login_required
@carpark_edit_required
def delete_revenue(revenue_id):
    """Delete a revenue record."""
    existing = _service.get_revenue(revenue_id)
    if not existing:
        return jsonify({'error': 'Revenue not found'}), 404
    _, err = _verify_vehicle_ownership(existing['vehicle_id'])
    if err:
        return err

    if _service.delete_revenue(revenue_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Revenue not found'}), 404


# ═══════════════════════════════════════════════
# REVENUES — TOTALS
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/revenues/totals', methods=['GET'])
@login_required
@carpark_required
def revenue_totals(vehicle_id):
    """Get revenue totals grouped by type for a vehicle."""
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err
    totals = _service.get_revenue_totals(vehicle_id)
    return jsonify(_serialize(totals))


# ═══════════════════════════════════════════════
# PROFITABILITY
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/profitability', methods=['GET'])
@login_required
@carpark_required
def vehicle_profitability(vehicle_id):
    """Get profitability summary for a vehicle."""
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err
    profit = _service.get_profitability(vehicle_id)
    return jsonify(_serialize(profit))
