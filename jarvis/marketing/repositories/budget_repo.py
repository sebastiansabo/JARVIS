"""Repository for mkt_budget_lines and mkt_budget_transactions tables."""

import logging
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.marketing.budget_repo')


class BudgetRepository(BaseRepository):

    # ---- Budget Lines ----

    def get_lines_by_project(self, project_id):
        return self.query_all('''
            SELECT bl.*,
                   COALESCE(
                       (SELECT SUM(CASE WHEN t.direction = 'debit' THEN t.amount ELSE -t.amount END)
                        FROM mkt_budget_transactions t WHERE t.budget_line_id = bl.id), 0
                   ) as computed_spent,
                   COALESCE(
                       (SELECT SUM(t.amount)
                        FROM mkt_budget_transactions t WHERE t.budget_line_id = bl.id AND t.direction = 'credit'), 0
                   ) as credit_amount
            FROM mkt_budget_lines bl
            WHERE bl.project_id = %s
            ORDER BY bl.created_at
        ''', (project_id,))

    def get_line_by_id(self, line_id):
        return self.query_one(
            'SELECT * FROM mkt_budget_lines WHERE id = %s', (line_id,)
        )

    def create_line(self, project_id, channel, **kwargs):
        def _work(cursor):
            import json
            metadata = kwargs.get('metadata')
            metadata_json = json.dumps(metadata) if metadata else '{}'
            cursor.execute('''
                INSERT INTO mkt_budget_lines
                    (project_id, channel, description, department_structure_id, agency_name,
                     planned_amount, currency, period_type, period_start, period_end, notes, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id
            ''', (
                project_id, channel, kwargs.get('description'),
                kwargs.get('department_structure_id'), kwargs.get('agency_name'),
                kwargs.get('planned_amount', 0), kwargs.get('currency', 'RON'),
                kwargs.get('period_type', 'campaign'),
                kwargs.get('period_start'), kwargs.get('period_end'),
                kwargs.get('notes'), metadata_json,
            ))
            line_id = cursor.fetchone()['id']
            self._recalc_project_budget(cursor, project_id)
            return line_id
        return self.execute_many(_work)

    # ---- Event-linked auto lines ----

    def create_for_event(self, project_id, event_id, event_name, event_cost, currency='RON'):
        """Auto-create a budget line for a linked HR event. Idempotent."""
        def _work(cursor):
            import json
            # Skip if an auto-line for this event already exists
            cursor.execute('''
                SELECT id FROM mkt_budget_lines
                WHERE project_id = %s
                  AND metadata->>'source' = 'event'
                  AND metadata->>'event_id' = %s
                LIMIT 1
            ''', (project_id, str(event_id)))
            existing = cursor.fetchone()
            if existing:
                cursor.execute('''
                    UPDATE mkt_budget_lines
                    SET planned_amount = %s, currency = %s, updated_at = NOW()
                    WHERE id = %s
                ''', (event_cost or 0, currency, existing['id']))
                self._recalc_project_budget(cursor, project_id)
                return existing['id']
            metadata = json.dumps({
                'source': 'event',
                'event_id': int(event_id),
                'event_name': event_name,
            })
            cursor.execute('''
                INSERT INTO mkt_budget_lines
                    (project_id, channel, description, planned_amount, currency,
                     period_type, status, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id
            ''', (
                project_id, 'events', f'Event: {event_name}',
                event_cost or 0, currency, 'campaign', 'active', metadata,
            ))
            line_id = cursor.fetchone()['id']
            self._recalc_project_budget(cursor, project_id)
            return line_id
        return self.execute_many(_work)

    def delete_for_event(self, project_id, event_id):
        """Delete the auto-generated budget line for an unlinked event. Returns True if deleted."""
        def _work(cursor):
            cursor.execute('''
                DELETE FROM mkt_budget_lines
                WHERE project_id = %s
                  AND metadata->>'source' = 'event'
                  AND metadata->>'event_id' = %s
                RETURNING id
            ''', (project_id, str(event_id)))
            deleted = cursor.fetchone() is not None
            if deleted:
                self._recalc_project_budget(cursor, project_id)
            return deleted
        return self.execute_many(_work)

    def update_line(self, line_id, **kwargs):
        allowed = {
            'channel', 'description', 'department_structure_id', 'agency_name',
            'planned_amount', 'approved_amount', 'currency',
            'period_type', 'period_start', 'period_end', 'status', 'notes',
        }
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
                f'UPDATE mkt_budget_lines SET {", ".join(updates)} WHERE id = %s', params
            )
            cursor.execute(
                'SELECT project_id FROM mkt_budget_lines WHERE id = %s', (line_id,)
            )
            row = cursor.fetchone()
            if row:
                self._recalc_project_budget(cursor, row['project_id'])
            return cursor.rowcount > 0
        return self.execute_many(_work)

    def delete_line(self, line_id):
        def _work(cursor):
            cursor.execute(
                'SELECT project_id FROM mkt_budget_lines WHERE id = %s', (line_id,)
            )
            row = cursor.fetchone()
            project_id = row['project_id'] if row else None
            cursor.execute('DELETE FROM mkt_budget_lines WHERE id = %s', (line_id,))
            deleted = cursor.rowcount > 0
            if project_id:
                self._recalc_project_budget(cursor, project_id)
            return deleted
        return self.execute_many(_work)

    def get_invoice_info(self, invoice_id):
        """Get invoice currency and value for currency conversion."""
        return self.query_one('''
            SELECT id, currency, COALESCE(net_value, invoice_value) as net_value,
                   invoice_date
            FROM invoices WHERE id = %s
        ''', (invoice_id,))

    # ---- Budget Transactions ----

    def get_transactions(self, budget_line_id):
        return self.query_all('''
            SELECT t.*, u.name as recorded_by_name,
                   i.supplier as invoice_supplier,
                   i.invoice_number as invoice_number_ref,
                   f.file_name as file_name_ref,
                   f.storage_uri as file_storage_uri
            FROM mkt_budget_transactions t
            JOIN users u ON u.id = t.recorded_by
            LEFT JOIN invoices i ON i.id = t.invoice_id
            LEFT JOIN mkt_project_files f ON f.id = t.file_id
            WHERE t.budget_line_id = %s
            ORDER BY t.transaction_date DESC, t.created_at DESC
        ''', (budget_line_id,))

    def create_transaction(self, budget_line_id, amount, transaction_date, recorded_by, **kwargs):
        def _work(cursor):
            invoice_id = kwargs.get('invoice_id')
            if invoice_id:
                cursor.execute('''
                    SELECT 1 FROM mkt_budget_transactions
                    WHERE budget_line_id = %s AND invoice_id = %s
                    LIMIT 1
                ''', (budget_line_id, invoice_id))
                if cursor.fetchone():
                    raise ValueError('This invoice is already linked to this budget line')
            # Prevent duplicate event links
            source = kwargs.get('source')
            reference_id = kwargs.get('reference_id')
            if source == 'event' and reference_id:
                cursor.execute('''
                    SELECT 1 FROM mkt_budget_transactions
                    WHERE budget_line_id = %s AND source = 'event' AND reference_id = %s
                    LIMIT 1
                ''', (budget_line_id, reference_id))
                if cursor.fetchone():
                    raise ValueError('This event is already linked to this budget line')
            cursor.execute('''
                INSERT INTO mkt_budget_transactions
                    (budget_line_id, amount, direction, source, reference_id, invoice_id,
                     file_id, transaction_date, description, recorded_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                budget_line_id, amount,
                kwargs.get('direction', 'debit'), kwargs.get('source', 'manual'),
                kwargs.get('reference_id'), kwargs.get('invoice_id'),
                kwargs.get('file_id'),
                transaction_date, kwargs.get('description'), recorded_by,
            ))
            tx_id = cursor.fetchone()['id']
            self._recalc_line_spent(cursor, budget_line_id)
            return tx_id
        return self.execute_many(_work)

    def update_transaction(self, tx_id, **kwargs):
        """Update editable fields of a transaction."""
        allowed = {'amount', 'transaction_date', 'description', 'direction'}
        updates = []
        params = []
        for key, val in kwargs.items():
            if key in allowed:
                updates.append(f'{key} = %s')
                params.append(val)
        if not updates:
            return False

        def _work(cursor):
            params.append(tx_id)
            cursor.execute(
                f'UPDATE mkt_budget_transactions SET {", ".join(updates)} WHERE id = %s', params
            )
            cursor.execute(
                'SELECT budget_line_id FROM mkt_budget_transactions WHERE id = %s', (tx_id,)
            )
            row = cursor.fetchone()
            if row:
                self._recalc_line_spent(cursor, row['budget_line_id'])
            return cursor.rowcount > 0
        return self.execute_many(_work)

    def link_transaction_invoice(self, tx_id, invoice_id):
        """Set or clear invoice_id on a transaction."""
        return self.execute('''
            UPDATE mkt_budget_transactions SET invoice_id = %s WHERE id = %s
        ''', (invoice_id, tx_id)) > 0

    def link_transaction_file(self, tx_id, file_id):
        """Set or clear file_id on a transaction."""
        return self.execute('''
            UPDATE mkt_budget_transactions SET file_id = %s WHERE id = %s
        ''', (file_id, tx_id)) > 0

    def delete_transaction(self, tx_id):
        def _work(cursor):
            cursor.execute(
                'SELECT budget_line_id FROM mkt_budget_transactions WHERE id = %s', (tx_id,)
            )
            row = cursor.fetchone()
            line_id = row['budget_line_id'] if row else None
            cursor.execute(
                'DELETE FROM mkt_budget_transactions WHERE id = %s', (tx_id,)
            )
            deleted = cursor.rowcount > 0
            if line_id:
                self._recalc_line_spent(cursor, line_id)
            return deleted
        return self.execute_many(_work)

    # ---- Helpers ----

    def _recalc_line_spent(self, cursor, budget_line_id):
        cursor.execute('''
            UPDATE mkt_budget_lines SET
                spent_amount = COALESCE(
                    (SELECT SUM(CASE WHEN direction = 'debit' THEN amount ELSE -amount END)
                     FROM mkt_budget_transactions WHERE budget_line_id = %s), 0
                ),
                updated_at = NOW()
            WHERE id = %s
        ''', (budget_line_id, budget_line_id))

    def _recalc_project_budget(self, cursor, project_id):
        cursor.execute('''
            UPDATE mkt_projects SET
                total_budget = COALESCE(
                    (SELECT SUM(planned_amount) FROM mkt_budget_lines WHERE project_id = %s), 0
                ),
                updated_at = NOW()
            WHERE id = %s
        ''', (project_id, project_id))
