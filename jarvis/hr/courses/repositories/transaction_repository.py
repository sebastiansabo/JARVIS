"""Repository for course transactions (manual spend + invoice-linked spend)."""
from typing import List, Dict, Any, Optional
from core.base_repository import BaseRepository


class CourseTransactionRepository(BaseRepository):
    """CRUD for hr.course_transactions — mirrors mkt_budget_transactions pattern."""

    def get_by_course(self, course_id: int) -> List[Dict[str, Any]]:
        """All transactions for a course, newest first."""
        return self.query_all('''
            SELECT ct.*,
                   i.invoice_number, i.supplier as invoice_supplier,
                   i.invoice_value as invoice_value, i.currency as invoice_currency
            FROM hr.course_transactions ct
            LEFT JOIN invoices i ON ct.invoice_id = i.id
            WHERE ct.course_id = %s
            ORDER BY ct.transaction_date DESC, ct.created_at DESC
        ''', (course_id,))

    def get_totals(self, course_id: int) -> Dict[str, Any]:
        """Aggregate debit/credit totals for a course."""
        return self.query_one('''
            SELECT COALESCE(SUM(CASE WHEN direction = 'debit' THEN amount ELSE 0 END), 0) as total_debit,
                   COALESCE(SUM(CASE WHEN direction = 'credit' THEN amount ELSE 0 END), 0) as total_credit,
                   COALESCE(SUM(CASE WHEN direction = 'debit' THEN amount ELSE -amount END), 0) as net_cost,
                   COUNT(*) as transaction_count
            FROM hr.course_transactions
            WHERE course_id = %s
        ''', (course_id,)) or {'total_debit': 0, 'total_credit': 0, 'net_cost': 0, 'transaction_count': 0}

    def create(self, course_id: int, amount: float, direction: str = 'debit',
               source: str = 'manual', invoice_id: int = None,
               transaction_date: str = None, description: str = None,
               recorded_by: int = None, recorded_by_name: str = None) -> Dict[str, Any]:
        """Create a new transaction."""
        return self.execute('''
            INSERT INTO hr.course_transactions
                (course_id, amount, direction, source, invoice_id,
                 transaction_date, description, recorded_by, recorded_by_name)
            VALUES (%s, %s, %s, %s, %s, COALESCE(%s, CURRENT_DATE), %s, %s, %s)
            RETURNING *
        ''', (course_id, amount, direction, source, invoice_id,
              transaction_date, description, recorded_by, recorded_by_name),
            returning=True)

    def update(self, tx_id: int, amount: float = None, transaction_date: str = None,
               description: str = None) -> Dict[str, Any]:
        """Update a manual transaction."""
        sets, params = [], []
        if amount is not None:
            sets.append('amount = %s')
            params.append(amount)
        if transaction_date is not None:
            sets.append('transaction_date = %s')
            params.append(transaction_date)
        if description is not None:
            sets.append('description = %s')
            params.append(description)
        if not sets:
            return None
        params.append(tx_id)
        return self.execute(
            f"UPDATE hr.course_transactions SET {', '.join(sets)} WHERE id = %s AND source = 'manual' RETURNING *",
            params, returning=True)

    def delete(self, tx_id: int) -> bool:
        """Delete a transaction."""
        self.execute('DELETE FROM hr.course_transactions WHERE id = %s', (tx_id,))
        return True

    def find_by_invoice(self, course_id: int, invoice_id: int) -> Optional[Dict[str, Any]]:
        """Check if an invoice is already linked as a transaction."""
        return self.query_one(
            "SELECT * FROM hr.course_transactions WHERE course_id = %s AND invoice_id = %s",
            (course_id, invoice_id))
