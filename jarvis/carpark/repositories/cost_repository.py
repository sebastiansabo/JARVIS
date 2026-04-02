"""Cost Repository — Data access for carpark_vehicle_costs."""
from typing import Optional, Dict, Any, List
from core.base_repository import BaseRepository


COST_FIELDS = (
    'cost_type', 'description', 'amount', 'currency', 'vat_rate', 'vat_amount',
    'exchange_rate_eur', 'invoice_number', 'invoice_date', 'invoice_value',
    'invoice_id', 'supplier_name', 'radio_cost_type', 'document_file',
    'observation', 'date',
)

COST_UPDATABLE = set(COST_FIELDS)


class CostRepository(BaseRepository):
    """Data access for vehicle cost records."""

    def get_by_vehicle(self, vehicle_id: int,
                       cost_type: str = None,
                       limit: int = 200) -> List[Dict[str, Any]]:
        """List costs for a vehicle, optionally filtered by type."""
        sql = 'SELECT * FROM carpark_vehicle_costs WHERE vehicle_id = %s'
        params: list = [vehicle_id]
        if cost_type:
            sql += ' AND cost_type = %s'
            params.append(cost_type)
        sql += ' ORDER BY date DESC, id DESC LIMIT %s'
        params.append(limit)
        return self.query_all(sql, tuple(params))

    def get_by_id(self, cost_id: int) -> Optional[Dict[str, Any]]:
        """Get a single cost record by ID."""
        return self.query_one(
            'SELECT * FROM carpark_vehicle_costs WHERE id = %s', (cost_id,)
        )

    def create(self, vehicle_id: int, data: Dict[str, Any],
               created_by: int = None) -> Dict[str, Any]:
        """Create a cost record for a vehicle."""
        safe = {k: data[k] for k in COST_FIELDS if k in data and data[k] is not None}
        if 'cost_type' not in safe:
            raise ValueError('cost_type is required')
        if 'amount' not in safe:
            raise ValueError('amount is required')

        cols = ['vehicle_id'] + list(safe.keys())
        vals = [vehicle_id] + list(safe.values())
        if created_by:
            cols.append('created_by')
            vals.append(created_by)

        placeholders = ', '.join(['%s'] * len(vals))
        col_str = ', '.join(cols)
        return self.execute(
            f'INSERT INTO carpark_vehicle_costs ({col_str}) VALUES ({placeholders}) RETURNING *',
            tuple(vals), returning=True
        )

    def update(self, cost_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update cost fields."""
        sets = []
        params = []
        for key in COST_UPDATABLE:
            if key in data:
                sets.append(f'{key} = %s')
                params.append(data[key])
        if not sets:
            return None
        params.append(cost_id)
        return self.execute(
            f"UPDATE carpark_vehicle_costs SET {', '.join(sets)} WHERE id = %s RETURNING *",
            tuple(params), returning=True
        )

    def delete(self, cost_id: int) -> bool:
        """Delete a single cost record."""
        return self.execute(
            'DELETE FROM carpark_vehicle_costs WHERE id = %s', (cost_id,)
        ) > 0

    def get_totals_by_vehicle(self, vehicle_id: int) -> Dict[str, Any]:
        """Get cost totals grouped by cost_type for a vehicle."""
        rows = self.query_all('''
            SELECT cost_type,
                   COUNT(*) AS count,
                   SUM(amount) AS total_amount,
                   SUM(vat_amount) AS total_vat
            FROM carpark_vehicle_costs
            WHERE vehicle_id = %s
            GROUP BY cost_type
            ORDER BY cost_type
        ''', (vehicle_id,))
        grand_total = sum(r['total_amount'] or 0 for r in rows)
        grand_vat = sum(r['total_vat'] or 0 for r in rows)
        return {
            'by_type': rows,
            'total_amount': grand_total,
            'total_vat': grand_vat,
            'total_with_vat': grand_total + grand_vat,
        }
