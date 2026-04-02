"""Pricing API routes — Rules, promotions, history, simulation, aging alerts."""
import logging

from flask import request, jsonify
from flask_login import login_required, current_user

from carpark import carpark_bp
from carpark.services.pricing_service import PricingService
from carpark.routes.vehicles import (
    carpark_required, carpark_edit_required, _serialize,
    _verify_vehicle_ownership, _user_company_id,
)

logger = logging.getLogger('jarvis.carpark')

_pricing_service = PricingService()


# ═══════════════════════════════════════════════
# PRICING RULES — LIST / CREATE
# ═══════════════════════════════════════════════

@carpark_bp.route('/pricing/rules', methods=['GET'])
@login_required
@carpark_required
def list_pricing_rules():
    """List pricing rules. Query: ?active_only=true"""
    active_only = request.args.get('active_only', '').lower() == 'true'
    company_id = _user_company_id()
    rules = _pricing_service.list_rules(company_id, active_only)
    return jsonify({'rules': _serialize(rules)})


@carpark_bp.route('/pricing/rules', methods=['POST'])
@login_required
@carpark_edit_required
def create_pricing_rule():
    """Create a pricing rule.

    Body: { name, action_type, action_value?, description?, is_active?,
            priority?, condition_category?, condition_brand?,
            condition_min_days?, condition_max_days?,
            condition_min_price?, condition_max_price?,
            action_floor_type?, action_floor_value?, frequency? }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    data['company_id'] = _user_company_id()

    try:
        rule = _pricing_service.create_rule(data, created_by=current_user.id)
        return jsonify({'rule': _serialize(rule)}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f'Pricing rule creation failed: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500


# ═══════════════════════════════════════════════
# PRICING RULES — GET / UPDATE / DELETE
# ═══════════════════════════════════════════════

@carpark_bp.route('/pricing/rules/<int:rule_id>', methods=['GET'])
@login_required
@carpark_required
def get_pricing_rule(rule_id):
    rule = _pricing_service.get_rule(rule_id)
    if not rule:
        return jsonify({'error': 'Rule not found'}), 404
    return jsonify({'rule': _serialize(rule)})


@carpark_bp.route('/pricing/rules/<int:rule_id>', methods=['PUT'])
@login_required
@carpark_edit_required
def update_pricing_rule(rule_id):
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    existing = _pricing_service.get_rule(rule_id)
    if not existing:
        return jsonify({'error': 'Rule not found'}), 404

    try:
        rule = _pricing_service.update_rule(rule_id, data)
        if not rule:
            return jsonify({'error': 'No fields to update'}), 400
        return jsonify({'rule': _serialize(rule)})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@carpark_bp.route('/pricing/rules/<int:rule_id>', methods=['DELETE'])
@login_required
@carpark_edit_required
def delete_pricing_rule(rule_id):
    if _pricing_service.delete_rule(rule_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Rule not found'}), 404


# ═══════════════════════════════════════════════
# PRICING RULES — EXECUTE
# ═══════════════════════════════════════════════

@carpark_bp.route('/pricing/rules/<int:rule_id>/execute', methods=['POST'])
@login_required
@carpark_edit_required
def execute_pricing_rule(rule_id):
    """Execute a pricing rule. Body: { dry_run?: boolean }"""
    data = request.get_json(silent=True) or {}
    dry_run = data.get('dry_run', False)
    company_id = _user_company_id()

    try:
        result = _pricing_service.execute_rule(
            rule_id, company_id=company_id,
            executed_by=current_user.id, dry_run=dry_run
        )
        return jsonify(_serialize(result))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f'Rule execution failed: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500


# ═══════════════════════════════════════════════
# SIMULATE
# ═══════════════════════════════════════════════

@carpark_bp.route('/pricing/simulate', methods=['POST'])
@login_required
@carpark_required
def simulate_pricing():
    """Dry-run pricing rules.

    Body: { vehicle_id?: number, rule_id?: number }
    At least one of vehicle_id or rule_id must be provided.
    """
    data = request.get_json(silent=True) or {}
    vehicle_id = data.get('vehicle_id')
    rule_id = data.get('rule_id')

    if not vehicle_id and not rule_id:
        return jsonify({'error': 'vehicle_id or rule_id is required'}), 400

    # Verify vehicle ownership if vehicle_id provided
    if vehicle_id:
        _, err = _verify_vehicle_ownership(vehicle_id)
        if err:
            return err

    company_id = _user_company_id()
    results = _pricing_service.simulate_rules(
        vehicle_id=vehicle_id, rule_id=rule_id, company_id=company_id
    )
    return jsonify({'simulations': _serialize(results)})


# ═══════════════════════════════════════════════
# FLOOR PRICE
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/floor-price', methods=['GET'])
@login_required
@carpark_required
def vehicle_floor_price(vehicle_id):
    """Get the calculated floor price for a vehicle."""
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err
    floor = _pricing_service.calculate_floor_price(vehicle_id)
    return jsonify(_serialize(floor))


# ═══════════════════════════════════════════════
# PRICING HISTORY
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/pricing-history', methods=['GET'])
@login_required
@carpark_required
def vehicle_pricing_history(vehicle_id):
    """Get pricing history for a vehicle."""
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err
    history = _pricing_service.get_pricing_history(vehicle_id)
    return jsonify({'history': _serialize(history)})


# ═══════════════════════════════════════════════
# VEHICLE PROMOTIONS
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/promotions', methods=['GET'])
@login_required
@carpark_required
def vehicle_promotions(vehicle_id):
    """Get active promotions for a specific vehicle."""
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err
    promos = _pricing_service.get_vehicle_promotions(vehicle_id)
    return jsonify({'promotions': _serialize(promos)})


# ═══════════════════════════════════════════════
# PROMOTIONS — LIST / CREATE
# ═══════════════════════════════════════════════

@carpark_bp.route('/promotions', methods=['GET'])
@login_required
@carpark_required
def list_promotions():
    """List promotions. Query: ?active_only=true"""
    active_only = request.args.get('active_only', '').lower() == 'true'
    company_id = _user_company_id()
    promos = _pricing_service.list_promotions(company_id, active_only)
    return jsonify({'promotions': _serialize(promos)})


@carpark_bp.route('/promotions', methods=['POST'])
@login_required
@carpark_edit_required
def create_promotion():
    """Create a promotion.

    Body: { name, target_type, promo_type, start_date, end_date,
            description?, discount_type?, discount_value?,
            target_categories?, target_brands?, target_vehicle_ids?,
            budget?, push_to_platforms?, platform_badge? }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    data['company_id'] = _user_company_id()

    try:
        promo = _pricing_service.create_promotion(data, created_by=current_user.id)
        return jsonify({'promotion': _serialize(promo)}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f'Promotion creation failed: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500


# ═══════════════════════════════════════════════
# PROMOTIONS — GET / UPDATE / DELETE
# ═══════════════════════════════════════════════

@carpark_bp.route('/promotions/<int:promo_id>', methods=['GET'])
@login_required
@carpark_required
def get_promotion(promo_id):
    promo = _pricing_service.get_promotion(promo_id)
    if not promo:
        return jsonify({'error': 'Promotion not found'}), 404
    return jsonify({'promotion': _serialize(promo)})


@carpark_bp.route('/promotions/<int:promo_id>', methods=['PUT'])
@login_required
@carpark_edit_required
def update_promotion(promo_id):
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    existing = _pricing_service.get_promotion(promo_id)
    if not existing:
        return jsonify({'error': 'Promotion not found'}), 404

    promo = _pricing_service.update_promotion(promo_id, data)
    if not promo:
        return jsonify({'error': 'No fields to update'}), 400
    return jsonify({'promotion': _serialize(promo)})


@carpark_bp.route('/promotions/<int:promo_id>', methods=['DELETE'])
@login_required
@carpark_edit_required
def delete_promotion(promo_id):
    if _pricing_service.delete_promotion(promo_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Promotion not found'}), 404


# ═══════════════════════════════════════════════
# AGING ALERTS
# ═══════════════════════════════════════════════

@carpark_bp.route('/pricing/aging', methods=['GET'])
@login_required
@carpark_required
def aging_vehicles():
    """Get vehicles that exceed the aging threshold.

    Query: ?min_days=60 (default from CARPARK_AGING_ALERT_DAYS env var)
    """
    min_days_str = request.args.get('min_days')
    min_days = int(min_days_str) if min_days_str else None
    company_id = _user_company_id()
    vehicles = _pricing_service.get_aging_vehicles(company_id, min_days)
    return jsonify({'vehicles': _serialize(vehicles), 'count': len(vehicles)})
