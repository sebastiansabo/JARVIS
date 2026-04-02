"""Pricing Service — Dynamic pricing engine for CarPark vehicles.

Handles pricing rule execution, floor price enforcement, dry-run simulation,
and batch pricing updates with full audit trail.
"""
import logging
import os
from datetime import datetime, date
from typing import Optional, Dict, Any, List

from carpark.repositories.pricing_repository import PricingRepository
from carpark.repositories.vehicle_repository import VehicleRepository
from carpark.repositories.cost_repository import CostRepository

logger = logging.getLogger('jarvis.carpark')

# Config from env
MIN_MARGIN_PERCENT = float(os.environ.get('CARPARK_MIN_MARGIN_PERCENT', '2'))
PRICING_APPROVAL_THRESHOLD = float(os.environ.get('CARPARK_PRICING_APPROVAL_THRESHOLD', '500'))
AGING_ALERT_DAYS = int(os.environ.get('CARPARK_AGING_ALERT_DAYS', '60'))

VALID_ACTION_TYPES = {'reduce_percent', 'reduce_amount', 'set_price', 'alert_only'}
VALID_FLOOR_TYPES = {'minimum_price', 'cost_plus_margin', 'purchase_recovery'}
VALID_TARGET_TYPES = {'all', 'category', 'brand', 'specific'}
VALID_PROMO_TYPES = {'discount', 'special_financing', 'gift', 'bundle'}
VALID_DISCOUNT_TYPES = {'percent', 'fixed'}


class PricingService:
    """Dynamic pricing engine with rule evaluation, floor enforcement, and simulation."""

    def __init__(self):
        self._pricing_repo = PricingRepository()
        self._vehicle_repo = VehicleRepository()
        self._cost_repo = CostRepository()

    # ═══════════════════════════════════════════════
    # PRICING RULES CRUD
    # ═══════════════════════════════════════════════

    def list_rules(self, company_id: int = None,
                   active_only: bool = False) -> List[Dict[str, Any]]:
        return self._pricing_repo.list_rules(company_id, active_only)

    def get_rule(self, rule_id: int) -> Optional[Dict[str, Any]]:
        return self._pricing_repo.get_rule(rule_id)

    def create_rule(self, data: Dict[str, Any],
                    created_by: int = None) -> Dict[str, Any]:
        if data.get('action_type') and data['action_type'] not in VALID_ACTION_TYPES:
            raise ValueError(f'Invalid action_type. Allowed: {", ".join(sorted(VALID_ACTION_TYPES))}')
        if data.get('action_floor_type') and data['action_floor_type'] not in VALID_FLOOR_TYPES:
            raise ValueError(f'Invalid action_floor_type. Allowed: {", ".join(sorted(VALID_FLOOR_TYPES))}')
        return self._pricing_repo.create_rule(data, created_by=created_by)

    def update_rule(self, rule_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if data.get('action_type') and data['action_type'] not in VALID_ACTION_TYPES:
            raise ValueError(f'Invalid action_type. Allowed: {", ".join(sorted(VALID_ACTION_TYPES))}')
        return self._pricing_repo.update_rule(rule_id, data)

    def delete_rule(self, rule_id: int) -> bool:
        return self._pricing_repo.delete_rule(rule_id)

    # ═══════════════════════════════════════════════
    # PROMOTIONS CRUD
    # ═══════════════════════════════════════════════

    def list_promotions(self, company_id: int = None,
                        active_only: bool = False) -> List[Dict[str, Any]]:
        return self._pricing_repo.list_promotions(company_id, active_only)

    def get_promotion(self, promo_id: int) -> Optional[Dict[str, Any]]:
        return self._pricing_repo.get_promotion(promo_id)

    def create_promotion(self, data: Dict[str, Any],
                         created_by: int = None) -> Dict[str, Any]:
        if data.get('target_type') and data['target_type'] not in VALID_TARGET_TYPES:
            raise ValueError(f'Invalid target_type. Allowed: {", ".join(sorted(VALID_TARGET_TYPES))}')
        if data.get('promo_type') and data['promo_type'] not in VALID_PROMO_TYPES:
            raise ValueError(f'Invalid promo_type. Allowed: {", ".join(sorted(VALID_PROMO_TYPES))}')
        if data.get('discount_type') and data['discount_type'] not in VALID_DISCOUNT_TYPES:
            raise ValueError(f'Invalid discount_type. Allowed: {", ".join(sorted(VALID_DISCOUNT_TYPES))}')
        return self._pricing_repo.create_promotion(data, created_by=created_by)

    def update_promotion(self, promo_id: int,
                         data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._pricing_repo.update_promotion(promo_id, data)

    def delete_promotion(self, promo_id: int) -> bool:
        return self._pricing_repo.delete_promotion(promo_id)

    def get_vehicle_promotions(self, vehicle_id: int) -> List[Dict[str, Any]]:
        return self._pricing_repo.get_vehicle_promotions(vehicle_id)

    # ═══════════════════════════════════════════════
    # PRICING HISTORY
    # ═══════════════════════════════════════════════

    def get_pricing_history(self, vehicle_id: int,
                            limit: int = 100) -> List[Dict[str, Any]]:
        return self._pricing_repo.get_history(vehicle_id, limit)

    # ═══════════════════════════════════════════════
    # FLOOR PRICE CALCULATION
    # ═══════════════════════════════════════════════

    def calculate_floor_price(self, vehicle_id: int) -> Dict[str, Any]:
        """Calculate the absolute minimum price for a vehicle.

        floor_price = MAX(
            vehicle.minimum_price,
            vehicle.total_cost * (1 + min_margin_percent / 100),
            vehicle.purchase_price_net * min_recovery_percent / 100
        )
        """
        vehicle = self._vehicle_repo.get_by_id(vehicle_id)
        if not vehicle:
            return {'floor_price': 0, 'components': {}}

        minimum_price = float(vehicle.get('minimum_price') or 0)

        # Cost + margin floor
        cost_totals = self._cost_repo.get_totals_by_vehicle(vehicle_id)
        acquisition_price = float(vehicle.get('acquisition_price') or 0)
        total_cost = acquisition_price + float(cost_totals['total_with_vat'])
        cost_plus_margin = total_cost * (1 + MIN_MARGIN_PERCENT / 100)

        # Purchase recovery floor (100% of net purchase price)
        purchase_net = float(vehicle.get('purchase_price_net') or 0)
        purchase_recovery = purchase_net

        floor = max(minimum_price, cost_plus_margin, purchase_recovery)

        return {
            'floor_price': round(floor, 2),
            'components': {
                'minimum_price': round(minimum_price, 2),
                'cost_plus_margin': round(cost_plus_margin, 2),
                'purchase_recovery': round(purchase_recovery, 2),
                'total_cost': round(total_cost, 2),
                'acquisition_price': round(acquisition_price, 2),
                'min_margin_percent': MIN_MARGIN_PERCENT,
            },
            'binding_constraint': (
                'minimum_price' if floor == minimum_price else
                'cost_plus_margin' if floor == cost_plus_margin else
                'purchase_recovery'
            ),
        }

    # ═══════════════════════════════════════════════
    # RULE EVALUATION (single vehicle)
    # ═══════════════════════════════════════════════

    def _vehicle_matches_rule(self, vehicle: Dict[str, Any],
                              rule: Dict[str, Any]) -> bool:
        """Check if a vehicle matches a rule's conditions."""
        # Category condition
        cats = rule.get('condition_category')
        if cats and vehicle.get('category') not in cats:
            return False

        # Brand condition
        brands = rule.get('condition_brand')
        if brands and vehicle.get('brand') not in brands:
            return False

        # Days listed condition
        days = vehicle.get('days_listed') or vehicle.get('stationary_days') or 0
        min_days = rule.get('condition_min_days')
        if min_days is not None and days < min_days:
            return False
        max_days = rule.get('condition_max_days')
        if max_days is not None and days > max_days:
            return False

        # Price range condition
        current_price = float(vehicle.get('current_price') or vehicle.get('list_price') or 0)
        min_price = rule.get('condition_min_price')
        if min_price is not None and current_price < float(min_price):
            return False
        max_price = rule.get('condition_max_price')
        if max_price is not None and current_price > float(max_price):
            return False

        return True

    def _apply_rule_action(self, current_price: float, rule: Dict[str, Any],
                           floor_price: float) -> Dict[str, Any]:
        """Calculate new price after applying a rule's action, enforcing floor."""
        action_type = rule['action_type']
        action_value = float(rule.get('action_value') or 0)

        if action_type == 'reduce_percent':
            new_price = current_price * (1 - action_value / 100)
        elif action_type == 'reduce_amount':
            new_price = current_price - action_value
        elif action_type == 'set_price':
            new_price = action_value
        elif action_type == 'alert_only':
            return {
                'action': 'alert_only',
                'current_price': current_price,
                'suggested_price': current_price,
                'reduction': 0,
                'floor_price': floor_price,
                'floor_hit': False,
            }
        else:
            return {
                'action': 'unknown',
                'current_price': current_price,
                'suggested_price': current_price,
                'reduction': 0,
                'floor_price': floor_price,
                'floor_hit': False,
            }

        floor_hit = new_price < floor_price
        final_price = max(new_price, floor_price)

        return {
            'action': action_type,
            'current_price': round(current_price, 2),
            'suggested_price': round(final_price, 2),
            'reduction': round(current_price - final_price, 2),
            'reduction_percent': round((current_price - final_price) / current_price * 100, 2) if current_price > 0 else 0,
            'floor_price': round(floor_price, 2),
            'floor_hit': floor_hit,
        }

    # ═══════════════════════════════════════════════
    # SIMULATE (dry-run)
    # ═══════════════════════════════════════════════

    def simulate_rules(self, vehicle_id: int = None,
                       rule_id: int = None,
                       company_id: int = None) -> List[Dict[str, Any]]:
        """Dry-run: simulate pricing rules without applying.

        If vehicle_id is given, simulate all active rules against that vehicle.
        If rule_id is given, simulate that rule against all eligible vehicles.
        """
        results = []

        if vehicle_id:
            vehicle = self._vehicle_repo.get_by_id(vehicle_id)
            if not vehicle:
                return []
            rules = self._pricing_repo.list_rules(company_id, active_only=True)
            floor_data = self.calculate_floor_price(vehicle_id)
            current_price = float(vehicle.get('current_price') or vehicle.get('list_price') or 0)

            for rule in rules:
                if self._vehicle_matches_rule(vehicle, rule):
                    result = self._apply_rule_action(current_price, rule, floor_data['floor_price'])
                    result['rule_id'] = rule['id']
                    result['rule_name'] = rule['name']
                    result['vehicle_id'] = vehicle_id
                    result['vin'] = vehicle.get('vin')
                    results.append(result)

        elif rule_id:
            rule = self._pricing_repo.get_rule(rule_id)
            if not rule:
                return []
            # Get vehicles that match the rule's conditions
            vehicles = self._get_eligible_vehicles(rule, company_id)
            for v in vehicles:
                vid = v['id']
                floor_data = self.calculate_floor_price(vid)
                current_price = float(v.get('current_price') or v.get('list_price') or 0)
                if current_price <= 0:
                    continue
                result = self._apply_rule_action(current_price, rule, floor_data['floor_price'])
                result['rule_id'] = rule['id']
                result['rule_name'] = rule['name']
                result['vehicle_id'] = vid
                result['vin'] = v.get('vin')
                result['brand'] = v.get('brand')
                result['model'] = v.get('model')
                results.append(result)

        return results

    def _get_eligible_vehicles(self, rule: Dict[str, Any],
                               company_id: int = None,
                               limit: int = 200) -> List[Dict[str, Any]]:
        """Get vehicles matching a rule's conditions for batch simulation."""
        filters: Dict[str, Any] = {}
        if company_id:
            filters['company_id'] = str(company_id)

        cats = rule.get('condition_category')
        if cats and len(cats) == 1:
            filters['category'] = cats[0]

        brands = rule.get('condition_brand')
        if brands and len(brands) == 1:
            filters['brand'] = brands[0]

        # Fetch a broad set from catalog
        result = self._vehicle_repo.get_catalog(filters, page=1, per_page=limit)
        vehicles = result.get('items', [])

        # Further filter in Python for multi-condition matching
        return [v for v in vehicles if self._vehicle_matches_rule(v, rule)]

    # ═══════════════════════════════════════════════
    # EXECUTE RULE (apply price changes)
    # ═══════════════════════════════════════════════

    def execute_rule(self, rule_id: int, company_id: int = None,
                     executed_by: int = None,
                     dry_run: bool = False) -> Dict[str, Any]:
        """Execute a pricing rule against all matching vehicles.

        Returns summary with applied/skipped counts and details.
        Set dry_run=True for simulation without writes.
        """
        rule = self._pricing_repo.get_rule(rule_id)
        if not rule:
            raise ValueError('Rule not found')
        if not rule.get('is_active'):
            raise ValueError('Rule is not active')

        vehicles = self._get_eligible_vehicles(rule, company_id)
        applied = []
        skipped = []
        alerts = []

        for v in vehicles:
            vid = v['id']
            current_price = float(v.get('current_price') or v.get('list_price') or 0)
            if current_price <= 0:
                skipped.append({'vehicle_id': vid, 'reason': 'no_price'})
                continue

            floor_data = self.calculate_floor_price(vid)
            result = self._apply_rule_action(current_price, rule, floor_data['floor_price'])

            if result['action'] == 'alert_only':
                alerts.append({
                    'vehicle_id': vid,
                    'vin': v.get('vin'),
                    'brand': v.get('brand'),
                    'model': v.get('model'),
                    'days_listed': v.get('days_listed') or v.get('stationary_days'),
                    'current_price': current_price,
                })
                continue

            if result['reduction'] == 0:
                skipped.append({'vehicle_id': vid, 'reason': 'no_change'})
                continue

            # Check approval threshold
            needs_approval = result['reduction'] > PRICING_APPROVAL_THRESHOLD

            if not dry_run and not needs_approval:
                # Apply the price change
                self._vehicle_repo.update(vid, {
                    'current_price': result['suggested_price']
                }, updated_by=executed_by)

                # Log to history
                self._pricing_repo.log_price_change(
                    vid, current_price, result['suggested_price'],
                    f'rule:{rule["name"]}',
                    rule_id=rule_id,
                    changed_by=executed_by
                )

            applied.append({
                'vehicle_id': vid,
                'vin': v.get('vin'),
                'brand': v.get('brand'),
                'model': v.get('model'),
                'old_price': current_price,
                'new_price': result['suggested_price'],
                'reduction': result['reduction'],
                'floor_hit': result['floor_hit'],
                'needs_approval': needs_approval,
                'applied': not dry_run and not needs_approval,
            })

        # Update last_executed timestamp
        if not dry_run:
            self._pricing_repo.update_rule(rule_id, {'last_executed': datetime.utcnow()})

        return {
            'rule_id': rule_id,
            'rule_name': rule['name'],
            'dry_run': dry_run,
            'total_matched': len(vehicles),
            'applied_count': sum(1 for a in applied if a.get('applied')),
            'pending_approval_count': sum(1 for a in applied if a.get('needs_approval')),
            'skipped_count': len(skipped),
            'alert_count': len(alerts),
            'applied': applied,
            'skipped': skipped,
            'alerts': alerts,
        }

    # ═══════════════════════════════════════════════
    # AGING ALERTS
    # ═══════════════════════════════════════════════

    def get_aging_vehicles(self, company_id: int = None,
                           min_days: int = None) -> List[Dict[str, Any]]:
        """Get vehicles that have been listed/in stock beyond the aging threshold."""
        threshold = min_days if min_days is not None else AGING_ALERT_DAYS
        filters: Dict[str, Any] = {}
        if company_id:
            filters['company_id'] = str(company_id)

        result = self._vehicle_repo.get_catalog(filters, page=1, per_page=200)
        vehicles = result.get('items', [])

        aging = []
        for v in vehicles:
            days = v.get('days_listed') or v.get('stationary_days') or 0
            if days >= threshold:
                aging.append({
                    'vehicle_id': v['id'],
                    'vin': v.get('vin'),
                    'brand': v.get('brand'),
                    'model': v.get('model'),
                    'status': v.get('status'),
                    'days_listed': days,
                    'current_price': float(v.get('current_price') or 0),
                    'list_price': float(v.get('list_price') or 0),
                    'category': v.get('category'),
                    'severity': (
                        'critical' if days >= 90 else
                        'warning' if days >= 60 else
                        'info'
                    ),
                })

        aging.sort(key=lambda x: x['days_listed'], reverse=True)
        return aging
