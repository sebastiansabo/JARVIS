"""Time Bank data access layer."""

from decimal import Decimal

from core.base_repository import BaseRepository


class TimeBankRepository(BaseRepository):
    """CRUD for hr.time_bank_transactions."""

    # ── Balance ──

    def get_balance(self, user_id):
        """Get current balance for a single user."""
        row = self.query_one(
            """
            SELECT COALESCE(SUM(amount), 0) AS balance
            FROM hr.time_bank_transactions
            WHERE jarvis_user_id = %s
            """,
            (user_id,),
        )
        return Decimal(row['balance']) if row else Decimal(0)

    def get_balances_for_users(self, user_ids):
        """Get balances for a list of user IDs. Returns {user_id: Decimal}."""
        if not user_ids:
            return {}
        rows = self.query_all(
            """
            SELECT jarvis_user_id, COALESCE(SUM(amount), 0) AS balance
            FROM hr.time_bank_transactions
            WHERE jarvis_user_id IN %s
            GROUP BY jarvis_user_id
            """,
            (tuple(user_ids),),
        )
        return {r['jarvis_user_id']: Decimal(r['balance']) for r in rows}

    def get_all_balances(self):
        """All employee balances with user info. Returns list of dicts."""
        return self.query_all(
            """
            SELECT
                u.id AS user_id,
                u.name,
                u.email,
                u.company,
                u.department,
                COALESCE(tb.balance, 0) AS balance
            FROM public.users u
            INNER JOIN (
                SELECT jarvis_user_id, SUM(amount) AS balance
                FROM hr.time_bank_transactions
                GROUP BY jarvis_user_id
            ) tb ON tb.jarvis_user_id = u.id
            ORDER BY u.name
            """
        )

    # ── Transactions ──

    def insert_transaction(self, *, user_id, amount, tx_type, description=None,
                           reference_type=None, reference_id=None, created_by=None):
        """Insert a new transaction. Returns the new row."""
        return self.execute(
            """
            INSERT INTO hr.time_bank_transactions
                (jarvis_user_id, amount, tx_type, description,
                 reference_type, reference_id, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, jarvis_user_id, amount, tx_type, description,
                      reference_type, reference_id, created_by, created_at
            """,
            (user_id, amount, tx_type, description,
             reference_type, reference_id, created_by),
            returning=True,
        )

    def get_transactions(self, user_id, limit=50, offset=0, tx_type=None):
        """Get transactions for a single user, newest first."""
        conditions = ['jarvis_user_id = %s']
        params = [user_id]
        if tx_type:
            conditions.append('tx_type = %s')
            params.append(tx_type)
        where = ' AND '.join(conditions)
        params.extend([limit, offset])
        return self.query_all(
            f"""
            SELECT t.*, u.name AS created_by_name
            FROM hr.time_bank_transactions t
            LEFT JOIN public.users u ON u.id = t.created_by
            WHERE {where}
            ORDER BY t.created_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple(params),
        )

    def get_all_transactions(self, limit=100, offset=0, tx_type=None, user_id=None):
        """Get all transactions (admin view), newest first."""
        conditions = []
        params = []
        if tx_type:
            conditions.append('t.tx_type = %s')
            params.append(tx_type)
        if user_id:
            conditions.append('t.jarvis_user_id = %s')
            params.append(user_id)
        where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''
        params.extend([limit, offset])
        return self.query_all(
            f"""
            SELECT t.*, emp.name AS employee_name, emp.company AS employee_company,
                   cr.name AS created_by_name
            FROM hr.time_bank_transactions t
            JOIN public.users emp ON emp.id = t.jarvis_user_id
            LEFT JOIN public.users cr ON cr.id = t.created_by
            {where}
            ORDER BY t.created_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple(params),
        )

    def count_transactions(self, user_id=None, tx_type=None):
        """Count transactions (for pagination)."""
        conditions = []
        params = []
        if user_id:
            conditions.append('jarvis_user_id = %s')
            params.append(user_id)
        if tx_type:
            conditions.append('tx_type = %s')
            params.append(tx_type)
        where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''
        row = self.query_one(
            f"SELECT COUNT(*) AS n FROM hr.time_bank_transactions {where}",
            tuple(params) if params else None,
        )
        return int(row['n']) if row else 0

    # ── Idempotency ──

    def has_reference(self, reference_type, reference_id):
        """Check if a transaction with this reference already exists."""
        row = self.query_one(
            """
            SELECT 1 FROM hr.time_bank_transactions
            WHERE reference_type = %s AND reference_id = %s
            LIMIT 1
            """,
            (reference_type, reference_id),
        )
        return row is not None

    # ── T0 ──

    def has_t0(self, user_id):
        """Check if a T0 transaction already exists for this user."""
        row = self.query_one(
            """
            SELECT 1 FROM hr.time_bank_transactions
            WHERE jarvis_user_id = %s AND tx_type = 'T0'
            LIMIT 1
            """,
            (user_id,),
        )
        return row is not None

    def delete_t0(self, user_id):
        """Delete existing T0 for a user (to allow re-import)."""
        return self.execute(
            """
            DELETE FROM hr.time_bank_transactions
            WHERE jarvis_user_id = %s AND tx_type = 'T0'
            """,
            (user_id,),
        )
