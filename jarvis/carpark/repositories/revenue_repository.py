"""Revenue Repository — Data access for carpark_vehicle_revenues."""
from typing import Optional, Dict, Any, List
from core.base_repository import BaseRepository
from carpark.money import REVENUE_EUR_SQL, REVENUE_VAT_EUR_SQL


REVENUE_FIELDS = (
    'revenue_type', 'description', 'amount', 'currency', 'vat_amount',
    'exchange_rate_eur', 'invoice_number', 'invoice_id', 'client_name', 'date',
)

# source_document_id is intentionally NOT in REVENUE_FIELDS/REVENUE_UPDATABLE:
# it's server-controlled (set only by the invoice->income transfer via the
# create() kwarg below), so a user can't mass-assign it on the generic revenue
# create/update routes to fake/steal a document->revenue link.
REVENUE_UPDATABLE = set(REVENUE_FIELDS)


class RevenueRepository(BaseRepository):
    """Data access for vehicle revenue records."""

    def get_by_vehicle(self, vehicle_id: int,
                       revenue_type: str = None,
                       limit: int = 200) -> List[Dict[str, Any]]:
        """List revenues for a vehicle, optionally filtered by type."""
        sql = 'SELECT * FROM carpark_vehicle_revenues WHERE vehicle_id = %s'
        params: list = [vehicle_id]
        if revenue_type:
            sql += ' AND revenue_type = %s'
            params.append(revenue_type)
        sql += ' ORDER BY date DESC, id DESC LIMIT %s'
        params.append(limit)
        return self.query_all(sql, tuple(params))

    def get_by_id(self, revenue_id: int) -> Optional[Dict[str, Any]]:
        """Get a single revenue record by ID."""
        return self.query_one(
            'SELECT * FROM carpark_vehicle_revenues WHERE id = %s', (revenue_id,)
        )

    def find_by_source_document(self, doc_id: int) -> Optional[Dict[str, Any]]:
        """Existing revenue row (if any) already linked to this source
        document — the dedup pre-check for the invoice->income transfer."""
        return self.query_one(
            'SELECT * FROM carpark_vehicle_revenues WHERE source_document_id = %s LIMIT 1',
            (doc_id,)
        )

    def create(self, vehicle_id: int, data: Dict[str, Any],
               created_by: int = None, source_document_id: int = None) -> Dict[str, Any]:
        """Create a revenue record for a vehicle.

        `source_document_id` is passed explicitly (by the invoice->income
        transfer), never read from `data`, so it can't be mass-assigned.
        """
        safe = {k: data[k] for k in REVENUE_FIELDS if k in data and data[k] is not None}
        if 'revenue_type' not in safe:
            raise ValueError('revenue_type is required')
        if 'amount' not in safe:
            raise ValueError('amount is required')
        if source_document_id is not None:
            safe['source_document_id'] = source_document_id

        cols = ['vehicle_id'] + list(safe.keys())
        vals = [vehicle_id] + list(safe.values())
        if created_by:
            cols.append('created_by')
            vals.append(created_by)

        placeholders = ', '.join(['%s'] * len(vals))
        col_str = ', '.join(cols)
        return self.execute(
            f'INSERT INTO carpark_vehicle_revenues ({col_str}) VALUES ({placeholders}) RETURNING *',
            tuple(vals), returning=True
        )

    def update(self, revenue_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update revenue fields."""
        sets = []
        params = []
        for key in REVENUE_UPDATABLE:
            if key in data:
                sets.append(f'{key} = %s')
                params.append(data[key])
        if not sets:
            return None
        params.append(revenue_id)
        return self.execute(
            f"UPDATE carpark_vehicle_revenues SET {', '.join(sets)} WHERE id = %s RETURNING *",
            tuple(params), returning=True
        )

    def delete(self, revenue_id: int) -> bool:
        """Delete a single revenue record."""
        return self.execute(
            'DELETE FROM carpark_vehicle_revenues WHERE id = %s', (revenue_id,)
        ) > 0

    def get_totals_by_vehicle(self, vehicle_id: int) -> Dict[str, Any]:
        """Get revenue totals grouped by revenue_type for a vehicle."""
        rows = self.query_all(f'''
            SELECT revenue_type,
                   COUNT(*) AS count,
                   SUM({REVENUE_EUR_SQL}) AS total_amount,
                   SUM({REVENUE_VAT_EUR_SQL}) AS total_vat
            FROM carpark_vehicle_revenues
            WHERE vehicle_id = %s
            GROUP BY revenue_type
            ORDER BY revenue_type
        ''', (vehicle_id,))
        grand_total = sum(r['total_amount'] or 0 for r in rows)
        grand_vat = sum(r['total_vat'] or 0 for r in rows)
        return {
            'by_type': rows,
            'total_amount': grand_total,
            'total_vat': grand_vat,
            'total_with_vat': grand_total + grand_vat,
        }
