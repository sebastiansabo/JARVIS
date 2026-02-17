"""Repository for mkt_budget_lines and mkt_budget_transactions tables."""

import logging
from database import get_db, get_cursor, release_db

logger = logging.getLogger('jarvis.marketing.budget_repo')


class BudgetRepository:

    # ---- Budget Lines ----

    def get_lines_by_project(self, project_id):
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                SELECT bl.*,
                       COALESCE(
                           (SELECT SUM(CASE WHEN t.direction = 'debit' THEN t.amount ELSE -t.amount END)
                            FROM mkt_budget_transactions t WHERE t.budget_line_id = bl.id), 0
                       ) as computed_spent
                FROM mkt_budget_lines bl
                WHERE bl.project_id = %s
                ORDER BY bl.created_at
            ''', (project_id,))
            return [dict(r) for r in cursor.fetchall()]
        finally:
            release_db(conn)

    def get_line_by_id(self, line_id):
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('SELECT * FROM mkt_budget_lines WHERE id = %s', (line_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            release_db(conn)

    def create_line(self, project_id, channel, **kwargs):
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                INSERT INTO mkt_budget_lines
                    (project_id, channel, description, department_structure_id, agency_name,
                     planned_amount, currency, period_type, period_start, period_end, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                project_id, channel, kwargs.get('description'),
                kwargs.get('department_structure_id'), kwargs.get('agency_name'),
                kwargs.get('planned_amount', 0), kwargs.get('currency', 'RON'),
                kwargs.get('period_type', 'campaign'),
                kwargs.get('period_start'), kwargs.get('period_end'),
                kwargs.get('notes'),
            ))
            line_id = cursor.fetchone()['id']
            # Update project total_budget
            self._recalc_project_budget(cursor, project_id)
            conn.commit()
            return line_id
        except Exception as e:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    def update_line(self, line_id, **kwargs):
        allowed = {
            'channel', 'description', 'department_structure_id', 'agency_name',
            'planned_amount', 'approved_amount', 'currency',
            'period_type', 'period_start', 'period_end', 'status', 'notes',
        }
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            updates = []
            params = []
            for key, val in kwargs.items():
                if key in allowed and val is not None:
                    updates.append(f'{key} = %s')
                    params.append(val)
            if not updates:
                return False
            updates.append('updated_at = NOW()')
            params.append(line_id)
            cursor.execute(f'UPDATE mkt_budget_lines SET {", ".join(updates)} WHERE id = %s', params)
            # Recalc project total
            cursor.execute('SELECT project_id FROM mkt_budget_lines WHERE id = %s', (line_id,))
            row = cursor.fetchone()
            if row:
                self._recalc_project_budget(cursor, row['project_id'])
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    def delete_line(self, line_id):
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('SELECT project_id FROM mkt_budget_lines WHERE id = %s', (line_id,))
            row = cursor.fetchone()
            project_id = row['project_id'] if row else None
            cursor.execute('DELETE FROM mkt_budget_lines WHERE id = %s', (line_id,))
            if project_id:
                self._recalc_project_budget(cursor, project_id)
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    # ---- Budget Transactions ----

    def get_transactions(self, budget_line_id):
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                SELECT t.*, u.name as recorded_by_name,
                       i.supplier as invoice_supplier,
                       i.invoice_number as invoice_number_ref
                FROM mkt_budget_transactions t
                JOIN users u ON u.id = t.recorded_by
                LEFT JOIN invoices i ON i.id = t.invoice_id
                WHERE t.budget_line_id = %s
                ORDER BY t.transaction_date DESC, t.created_at DESC
            ''', (budget_line_id,))
            return [dict(r) for r in cursor.fetchall()]
        finally:
            release_db(conn)

    def create_transaction(self, budget_line_id, amount, transaction_date, recorded_by, **kwargs):
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                INSERT INTO mkt_budget_transactions
                    (budget_line_id, amount, direction, source, reference_id, invoice_id,
                     transaction_date, description, recorded_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                budget_line_id, amount,
                kwargs.get('direction', 'debit'), kwargs.get('source', 'manual'),
                kwargs.get('reference_id'), kwargs.get('invoice_id'),
                transaction_date, kwargs.get('description'), recorded_by,
            ))
            tx_id = cursor.fetchone()['id']
            # Update spent_amount on budget line
            self._recalc_line_spent(cursor, budget_line_id)
            conn.commit()
            return tx_id
        except Exception as e:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    def update_transaction(self, tx_id, **kwargs):
        """Update editable fields of a transaction."""
        allowed = {'amount', 'transaction_date', 'description', 'direction'}
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            updates = []
            params = []
            for key, val in kwargs.items():
                if key in allowed:
                    updates.append(f'{key} = %s')
                    params.append(val)
            if not updates:
                return False
            params.append(tx_id)
            cursor.execute(f'UPDATE mkt_budget_transactions SET {", ".join(updates)} WHERE id = %s', params)
            # Recalc spent_amount on budget line
            cursor.execute('SELECT budget_line_id FROM mkt_budget_transactions WHERE id = %s', (tx_id,))
            row = cursor.fetchone()
            if row:
                self._recalc_line_spent(cursor, row['budget_line_id'])
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    def link_transaction_invoice(self, tx_id, invoice_id):
        """Set or clear invoice_id on a transaction."""
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                UPDATE mkt_budget_transactions SET invoice_id = %s WHERE id = %s
            ''', (invoice_id, tx_id))
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            release_db(conn)

    def delete_transaction(self, tx_id):
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('SELECT budget_line_id FROM mkt_budget_transactions WHERE id = %s', (tx_id,))
            row = cursor.fetchone()
            line_id = row['budget_line_id'] if row else None
            cursor.execute('DELETE FROM mkt_budget_transactions WHERE id = %s', (tx_id,))
            if line_id:
                self._recalc_line_spent(cursor, line_id)
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            conn.rollback()
            raise
        finally:
            release_db(conn)

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
