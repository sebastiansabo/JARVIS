"""Cost Line Repository — two-level cost hierarchy for CarPark vehicles.

Parent: carpark_vehicle_cost_lines  (cost lines / budget items)
Child:  carpark_vehicle_costs       (actual cost entries under each line)
"""
import logging
from typing import Optional, Dict, Any, List
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.carpark.cost_lines')

COST_ENTRY_FIELDS = (
    'cost_type', 'description', 'amount', 'currency', 'vat_rate', 'vat_amount',
    'exchange_rate_eur', 'invoice_number', 'invoice_date', 'invoice_value',
    'invoice_id', 'supplier_name', 'document_file', 'observation', 'date',
)


class CostLineRepository(BaseRepository):
    """Data access for vehicle cost lines and their child cost entries."""

    # ── Cost Lines ────────────────────────────────────────

    def get_lines_by_vehicle(self, vehicle_id: int) -> List[Dict[str, Any]]:
        """All cost lines for a vehicle with computed spent totals."""
        return self.query_all('''
            SELECT cl.*,
                   COALESCE(
                       (SELECT SUM(c.amount) FROM carpark_vehicle_costs c
                        WHERE c.cost_line_id = cl.id), 0
                   ) AS computed_spent,
                   COALESCE(
                       (SELECT COUNT(*) FROM carpark_vehicle_costs c
                        WHERE c.cost_line_id = cl.id), 0
                   ) AS cost_count
            FROM carpark_vehicle_cost_lines cl
            WHERE cl.vehicle_id = %s
            ORDER BY cl.created_at
        ''', (vehicle_id,))

    def get_line_by_id(self, line_id: int) -> Optional[Dict[str, Any]]:
        return self.query_one(
            'SELECT * FROM carpark_vehicle_cost_lines WHERE id = %s', (line_id,)
        )

    def create_line(self, vehicle_id: int, cost_type: str, **kwargs) -> int:
        def _work(cursor):
            cursor.execute('''
                INSERT INTO carpark_vehicle_cost_lines
                    (vehicle_id, cost_type, description, planned_amount, currency, notes, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                vehicle_id, cost_type,
                kwargs.get('description'),
                kwargs.get('planned_amount', 0),
                kwargs.get('currency', 'EUR'),
                kwargs.get('notes'),
                kwargs.get('created_by'),
            ))
            return cursor.fetchone()['id']
        return self.execute_many(_work)

    def update_line(self, line_id: int, **kwargs) -> bool:
        allowed = {'cost_type', 'description', 'planned_amount', 'currency', 'notes'}
        updates = []
        params = []
        for key, val in kwargs.items():
            if key in allowed and val is not None:
                updates.append(f'{key} = %s')
                params.append(val)
        if not updates:
            return False

        def _work(cursor):
            updates.append('updated_at = NOW()')
            params.append(line_id)
            cursor.execute(
                f'UPDATE carpark_vehicle_cost_lines SET {", ".join(updates)} WHERE id = %s',
                params
            )
            return cursor.rowcount > 0
        return self.execute_many(_work)

    def delete_line(self, line_id: int) -> bool:
        """Delete a cost line — cascades to child costs."""
        return self.execute(
            'DELETE FROM carpark_vehicle_cost_lines WHERE id = %s', (line_id,)
        ) > 0

    # ── Cost Entries (children) ───────────────────────────

    def get_costs_by_line(self, cost_line_id: int) -> List[Dict[str, Any]]:
        """All costs under a cost line, with invoice info."""
        return self.query_all('''
            SELECT c.*,
                   i.invoice_number AS invoice_number_ref,
                   i.supplier AS invoice_supplier_ref
            FROM carpark_vehicle_costs c
            LEFT JOIN invoices i ON i.id = c.invoice_id
            WHERE c.cost_line_id = %s
            ORDER BY c.date DESC, c.id DESC
        ''', (cost_line_id,))

    def create_cost(self, cost_line_id: int, data: Dict[str, Any],
                    created_by: int = None) -> int:
        """Create a cost entry under a cost line, recalc parent spent."""
        def _work(cursor):
            # Get parent line info to inherit vehicle_id and cost_type
            cursor.execute(
                'SELECT vehicle_id, cost_type FROM carpark_vehicle_cost_lines WHERE id = %s',
                (cost_line_id,)
            )
            line = cursor.fetchone()
            if not line:
                raise ValueError('Cost line not found')

            safe = {k: data[k] for k in COST_ENTRY_FIELDS if k in data and data[k] is not None}
            if 'amount' not in safe:
                raise ValueError('amount is required')
            # Default cost_type from parent if not provided
            if 'cost_type' not in safe:
                safe['cost_type'] = line['cost_type']

            cols = ['vehicle_id', 'cost_line_id'] + list(safe.keys())
            vals = [line['vehicle_id'], cost_line_id] + list(safe.values())
            if created_by:
                cols.append('created_by')
                vals.append(created_by)

            placeholders = ', '.join(['%s'] * len(vals))
            col_str = ', '.join(cols)
            cursor.execute(
                f'INSERT INTO carpark_vehicle_costs ({col_str}) VALUES ({placeholders}) RETURNING id',
                tuple(vals)
            )
            cost_id = cursor.fetchone()['id']
            self._recalc_line_spent(cursor, cost_line_id)
            return cost_id
        return self.execute_many(_work)

    def update_cost(self, cost_id: int, data: Dict[str, Any]) -> bool:
        """Update a cost entry and recalc parent line."""
        updates = []
        params = []
        for key in COST_ENTRY_FIELDS:
            if key in data:
                updates.append(f'{key} = %s')
                params.append(data[key])
        if not updates:
            return False

        def _work(cursor):
            params.append(cost_id)
            cursor.execute(
                f"UPDATE carpark_vehicle_costs SET {', '.join(updates)} WHERE id = %s",
                params
            )
            cursor.execute(
                'SELECT cost_line_id FROM carpark_vehicle_costs WHERE id = %s', (cost_id,)
            )
            row = cursor.fetchone()
            if row and row['cost_line_id']:
                self._recalc_line_spent(cursor, row['cost_line_id'])
            return cursor.rowcount > 0
        return self.execute_many(_work)

    def delete_cost(self, cost_id: int) -> bool:
        """Delete a cost entry and recalc parent line."""
        def _work(cursor):
            cursor.execute(
                'SELECT cost_line_id FROM carpark_vehicle_costs WHERE id = %s', (cost_id,)
            )
            row = cursor.fetchone()
            line_id = row['cost_line_id'] if row else None
            cursor.execute('DELETE FROM carpark_vehicle_costs WHERE id = %s', (cost_id,))
            deleted = cursor.rowcount > 0
            if line_id:
                self._recalc_line_spent(cursor, line_id)
            return deleted
        return self.execute_many(_work)

    def link_cost_invoice(self, cost_id: int, invoice_id: int = None) -> bool:
        """Link or unlink an invoice to a cost entry."""
        return self.execute(
            'UPDATE carpark_vehicle_costs SET invoice_id = %s WHERE id = %s',
            (invoice_id, cost_id)
        ) > 0

    # ── Helpers ───────────────────────────────────────────

    def _recalc_line_spent(self, cursor, cost_line_id: int):
        """Recalculate spent_amount on the parent cost line."""
        cursor.execute('''
            UPDATE carpark_vehicle_cost_lines SET
                spent_amount = COALESCE(
                    (SELECT SUM(amount) FROM carpark_vehicle_costs
                     WHERE cost_line_id = %s), 0
                ),
                updated_at = NOW()
            WHERE id = %s
        ''', (cost_line_id, cost_line_id))
