"""Pricing Repository — Data access for pricing rules, history, and promotions."""
from typing import Optional, Dict, Any, List
from core.base_repository import BaseRepository


# ── Pricing Rules ──

RULE_FIELDS = (
    'name', 'description', 'is_active', 'priority',
    'condition_category', 'condition_brand',
    'condition_min_days', 'condition_max_days',
    'condition_min_price', 'condition_max_price',
    'action_type', 'action_value', 'action_floor_type', 'action_floor_value',
    'frequency', 'company_id',
)

RULE_UPDATABLE = set(RULE_FIELDS) | {'last_executed'}

# ── Promotions ──

PROMO_FIELDS = (
    'name', 'description',
    'target_type', 'target_categories', 'target_brands', 'target_vehicle_ids',
    'promo_type', 'discount_type', 'discount_value',
    'special_financing_rate', 'gift_description',
    'start_date', 'end_date', 'is_active',
    'budget', 'spent', 'vehicles_sold',
    'push_to_platforms', 'platform_badge',
    'company_id',
)

PROMO_UPDATABLE = set(PROMO_FIELDS)


class PricingRepository(BaseRepository):
    """Data access for pricing rules, pricing history, and promotions."""

    # ═══════════════════════════════════════════════
    # PRICING RULES
    # ═══════════════════════════════════════════════

    def list_rules(self, company_id: int = None,
                   active_only: bool = False,
                   limit: int = 100) -> List[Dict[str, Any]]:
        """List pricing rules, optionally filtered by company and active status."""
        sql = 'SELECT * FROM carpark_pricing_rules WHERE 1=1'
        params: list = []
        if company_id:
            sql += ' AND (company_id = %s OR company_id IS NULL)'
            params.append(company_id)
        if active_only:
            sql += ' AND is_active = TRUE'
        sql += ' ORDER BY priority DESC, name ASC LIMIT %s'
        params.append(limit)
        return self.query_all(sql, tuple(params))

    def get_rule(self, rule_id: int) -> Optional[Dict[str, Any]]:
        return self.query_one(
            'SELECT * FROM carpark_pricing_rules WHERE id = %s', (rule_id,)
        )

    def create_rule(self, data: Dict[str, Any],
                    created_by: int = None) -> Dict[str, Any]:
        safe = {k: data[k] for k in RULE_FIELDS if k in data and data[k] is not None}
        if 'name' not in safe:
            raise ValueError('Rule name is required')
        if 'action_type' not in safe:
            raise ValueError('action_type is required')

        cols = list(safe.keys())
        vals = list(safe.values())
        if created_by:
            cols.append('created_by')
            vals.append(created_by)

        placeholders = ', '.join(['%s'] * len(vals))
        col_str = ', '.join(cols)
        return self.execute(
            f'INSERT INTO carpark_pricing_rules ({col_str}) VALUES ({placeholders}) RETURNING *',
            tuple(vals), returning=True
        )

    def update_rule(self, rule_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        sets = []
        params = []
        for key in RULE_UPDATABLE:
            if key in data:
                sets.append(f'{key} = %s')
                params.append(data[key])
        if not sets:
            return None
        sets.append('updated_at = NOW()')
        params.append(rule_id)
        return self.execute(
            f"UPDATE carpark_pricing_rules SET {', '.join(sets)} WHERE id = %s RETURNING *",
            tuple(params), returning=True
        )

    def delete_rule(self, rule_id: int) -> bool:
        return self.execute(
            'DELETE FROM carpark_pricing_rules WHERE id = %s', (rule_id,)
        ) > 0

    # ═══════════════════════════════════════════════
    # PRICING HISTORY
    # ═══════════════════════════════════════════════

    def get_history(self, vehicle_id: int,
                    limit: int = 100) -> List[Dict[str, Any]]:
        """Get pricing history for a vehicle, newest first."""
        return self.query_all('''
            SELECT ph.*,
                   pr.name AS rule_name
            FROM carpark_pricing_history ph
            LEFT JOIN carpark_pricing_rules pr ON pr.id = ph.rule_id
            WHERE ph.vehicle_id = %s
            ORDER BY ph.created_at DESC
            LIMIT %s
        ''', (vehicle_id, limit))

    def log_price_change(self, vehicle_id: int, old_price: float,
                         new_price: float, reason: str,
                         rule_id: int = None,
                         changed_by: int = None) -> Dict[str, Any]:
        """Record a pricing change in history."""
        return self.execute('''
            INSERT INTO carpark_pricing_history
                (vehicle_id, old_price, new_price, change_reason, rule_id, changed_by)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING *
        ''', (vehicle_id, old_price, new_price, reason, rule_id, changed_by),
            returning=True)

    # ═══════════════════════════════════════════════
    # PROMOTIONS
    # ═══════════════════════════════════════════════

    def list_promotions(self, company_id: int = None,
                        active_only: bool = False,
                        limit: int = 100) -> List[Dict[str, Any]]:
        sql = 'SELECT * FROM carpark_promotions WHERE 1=1'
        params: list = []
        if company_id:
            sql += ' AND (company_id = %s OR company_id IS NULL)'
            params.append(company_id)
        if active_only:
            sql += ' AND is_active = TRUE AND end_date >= CURRENT_DATE'
        sql += ' ORDER BY start_date DESC, name ASC LIMIT %s'
        params.append(limit)
        return self.query_all(sql, tuple(params))

    def get_promotion(self, promo_id: int) -> Optional[Dict[str, Any]]:
        return self.query_one(
            'SELECT * FROM carpark_promotions WHERE id = %s', (promo_id,)
        )

    def create_promotion(self, data: Dict[str, Any],
                         created_by: int = None) -> Dict[str, Any]:
        safe = {k: data[k] for k in PROMO_FIELDS if k in data and data[k] is not None}
        if 'name' not in safe:
            raise ValueError('Promotion name is required')
        if 'target_type' not in safe:
            raise ValueError('target_type is required')
        if 'promo_type' not in safe:
            raise ValueError('promo_type is required')
        if 'start_date' not in safe or 'end_date' not in safe:
            raise ValueError('start_date and end_date are required')

        cols = list(safe.keys())
        vals = list(safe.values())
        if created_by:
            cols.append('created_by')
            vals.append(created_by)

        placeholders = ', '.join(['%s'] * len(vals))
        col_str = ', '.join(cols)
        return self.execute(
            f'INSERT INTO carpark_promotions ({col_str}) VALUES ({placeholders}) RETURNING *',
            tuple(vals), returning=True
        )

    def update_promotion(self, promo_id: int,
                         data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        sets = []
        params = []
        for key in PROMO_UPDATABLE:
            if key in data:
                sets.append(f'{key} = %s')
                params.append(data[key])
        if not sets:
            return None
        sets.append('updated_at = NOW()')
        params.append(promo_id)
        return self.execute(
            f"UPDATE carpark_promotions SET {', '.join(sets)} WHERE id = %s RETURNING *",
            tuple(params), returning=True
        )

    def delete_promotion(self, promo_id: int) -> bool:
        return self.execute(
            'DELETE FROM carpark_promotions WHERE id = %s', (promo_id,)
        ) > 0

    def get_vehicle_promotions(self, vehicle_id: int) -> List[Dict[str, Any]]:
        """Get active promotions that apply to a specific vehicle.

        Checks: target_type='all', junction table, legacy array, category/brand match.
        """
        return self.query_all('''
            SELECT DISTINCT p.* FROM carpark_promotions p
            LEFT JOIN carpark_promotion_vehicles cpv
                ON cpv.promotion_id = p.id AND cpv.vehicle_id = %s
            LEFT JOIN carpark_vehicles v ON v.id = %s
            WHERE p.is_active = TRUE
              AND p.end_date >= CURRENT_DATE
              AND (
                  p.target_type = 'all'
                  OR cpv.id IS NOT NULL
                  OR (p.target_type = 'specific' AND %s = ANY(p.target_vehicle_ids))
                  OR (p.target_type = 'category' AND v.category = ANY(p.target_categories))
                  OR (p.target_type = 'brand' AND v.brand = ANY(p.target_brands))
              )
            ORDER BY p.start_date DESC
        ''', (vehicle_id, vehicle_id, vehicle_id))

    # ═══════════════════════════════════════════════
    # PROMOTION VEHICLES (junction table)
    # ═══════════════════════════════════════════════

    def get_promotion_vehicles(self, promo_id: int) -> List[Dict[str, Any]]:
        """Get vehicles assigned to a promotion via junction table."""
        return self.query_all('''
            SELECT cpv.id, cpv.promotion_id, cpv.vehicle_id, cpv.added_by,
                   cpv.created_at,
                   u.name AS added_by_name,
                   v.vin, v.brand, v.model, v.current_price, v.status
            FROM carpark_promotion_vehicles cpv
            JOIN carpark_vehicles v ON v.id = cpv.vehicle_id
            LEFT JOIN users u ON u.id = cpv.added_by
            WHERE cpv.promotion_id = %s
              AND v.deleted_at IS NULL
            ORDER BY v.brand, v.model
        ''', (promo_id,))

    def add_vehicle_to_promotion(self, promo_id: int, vehicle_id: int,
                                  added_by: int) -> Optional[Dict[str, Any]]:
        """Add a vehicle to a promotion. Returns None if already exists."""
        return self.execute('''
            INSERT INTO carpark_promotion_vehicles (promotion_id, vehicle_id, added_by)
            VALUES (%s, %s, %s)
            ON CONFLICT (promotion_id, vehicle_id) DO NOTHING
            RETURNING *
        ''', (promo_id, vehicle_id, added_by), returning=True)

    def remove_vehicle_from_promotion(self, promo_id: int,
                                       vehicle_id: int) -> bool:
        """Remove a vehicle from a promotion."""
        return self.execute(
            'DELETE FROM carpark_promotion_vehicles WHERE promotion_id = %s AND vehicle_id = %s',
            (promo_id, vehicle_id)
        ) > 0

    def set_promotion_vehicles(self, promo_id: int, vehicle_ids: List[int],
                                added_by: int) -> int:
        """Bulk set vehicles for a promotion. Returns count of new links."""
        if not vehicle_ids:
            self.execute(
                'DELETE FROM carpark_promotion_vehicles WHERE promotion_id = %s',
                (promo_id,)
            )
            return 0

        def _work(cursor):
            # Remove vehicles not in new list
            cursor.execute(
                'DELETE FROM carpark_promotion_vehicles WHERE promotion_id = %s AND vehicle_id != ALL(%s)',
                (promo_id, vehicle_ids)
            )
            # Insert new ones
            added = 0
            for vid in vehicle_ids:
                cursor.execute('''
                    INSERT INTO carpark_promotion_vehicles (promotion_id, vehicle_id, added_by)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (promotion_id, vehicle_id) DO NOTHING
                ''', (promo_id, vid, added_by))
                added += cursor.rowcount
            return added

        return self.execute_many(_work)
