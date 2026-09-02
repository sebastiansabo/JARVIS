"""Time Bank data access layer."""

from decimal import Decimal

from core.base_repository import BaseRepository

# Only these statuses count toward the effective balance
ACTIVE_STATUSES = ('approved', 'processed')

# tx_types whose net sum forms the separately-capped "event" pool (Ore Libere din
# Eveniment). Everything else (T0, manual, personal leave, connecteam, co_conversion…)
# is the "personal" pool = total − event, which may go negative.
EVENT_TX_TYPES = ('marketing_event', 'leave_permit_event', 'leave_permit_event_reversal')


class TimeBankRepository(BaseRepository):
    """CRUD for hr.time_bank_transactions."""

    # ── Balance ──

    def get_balance(self, user_id):
        """Get current balance for a single user (only approved/processed)."""
        row = self.query_one(
            """
            SELECT COALESCE(SUM(amount), 0) AS balance
            FROM hr.time_bank_transactions
            WHERE jarvis_user_id = %s AND status IN %s
            """,
            (user_id, ACTIVE_STATUSES),
        )
        return Decimal(row['balance']) if row else Decimal(0)

    def get_event_balance(self, user_id):
        """Net event-pool balance: marketing_event credits minus event-reason leave
        debits (+ reversals). Event leaves are capped at this so it never goes < 0."""
        row = self.query_one(
            """
            SELECT COALESCE(SUM(amount), 0) AS balance
            FROM hr.time_bank_transactions
            WHERE jarvis_user_id = %s AND status IN %s AND tx_type IN %s
            """,
            (user_id, ACTIVE_STATUSES, EVENT_TX_TYPES),
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
            WHERE jarvis_user_id IN %s AND status IN %s
            GROUP BY jarvis_user_id
            """,
            (tuple(user_ids), ACTIVE_STATUSES),
        )
        return {r['jarvis_user_id']: Decimal(r['balance']) for r in rows}

    def get_all_balances(self, include_all_employees=False):
        """All employee balances with user info. Returns list of dicts.

        If include_all_employees=True, returns every active user (balance 0 if no transactions).
        Also returns pending_count per user.
        """
        join = 'LEFT' if include_all_employees else 'INNER'
        where = "WHERE u.is_active = true" if include_all_employees else ""
        return self.query_all(
            f"""
            SELECT
                u.id AS user_id,
                u.name,
                u.email,
                u.company,
                u.department,
                COALESCE(tb.balance, 0) AS balance,
                COALESCE(pend.pending_count, 0) AS pending_count
            FROM public.users u
            {join} JOIN (
                SELECT jarvis_user_id, SUM(amount) AS balance
                FROM hr.time_bank_transactions
                WHERE status IN ('approved', 'processed')
                GROUP BY jarvis_user_id
            ) tb ON tb.jarvis_user_id = u.id
            LEFT JOIN (
                SELECT jarvis_user_id, COUNT(*) AS pending_count
                FROM hr.time_bank_transactions
                WHERE status = 'pending'
                GROUP BY jarvis_user_id
            ) pend ON pend.jarvis_user_id = u.id
            {where}
            ORDER BY u.name
            """
        )

    # ── Transactions ──

    def insert_transaction(self, *, user_id, amount, tx_type, description=None,
                           reference_type=None, reference_id=None, created_by=None,
                           status='pending'):
        """Insert a new transaction. Returns the new row."""
        approved_by = created_by if status in ACTIVE_STATUSES else None
        approved_at = 'NOW()' if status in ACTIVE_STATUSES else 'NULL'
        return self.execute(
            f"""
            INSERT INTO hr.time_bank_transactions
                (jarvis_user_id, amount, tx_type, description,
                 reference_type, reference_id, created_by, status,
                 approved_by, approved_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, {approved_at})
            RETURNING id, jarvis_user_id, amount, tx_type, description,
                      reference_type, reference_id, created_by, created_at,
                      status, approved_by, approved_at
            """,
            (user_id, amount, tx_type, description,
             reference_type, reference_id, created_by, status, approved_by),
            returning=True,
        )

    def update_status(self, tx_id, status, approved_by=None):
        """Update transaction status. Returns updated row."""
        return self.execute(
            """
            UPDATE hr.time_bank_transactions
            SET status = %s, approved_by = %s, approved_at = NOW()
            WHERE id = %s
            RETURNING id, jarvis_user_id, amount, tx_type, description,
                      status, approved_by, approved_at
            """,
            (status, approved_by, tx_id),
            returning=True,
        )

    def get_transaction_by_id(self, tx_id):
        """Get a single transaction by ID."""
        return self.query_one(
            """
            SELECT t.*, emp.name AS employee_name, cr.name AS created_by_name,
                   apr.name AS approved_by_name
            FROM hr.time_bank_transactions t
            JOIN public.users emp ON emp.id = t.jarvis_user_id
            LEFT JOIN public.users cr ON cr.id = t.created_by
            LEFT JOIN public.users apr ON apr.id = t.approved_by
            WHERE t.id = %s
            """,
            (tx_id,),
        )

    def get_transactions(self, user_id, limit=50, offset=0, tx_type=None, status=None):
        """Get transactions for a single user, newest first."""
        conditions = ['jarvis_user_id = %s']
        params = [user_id]
        if tx_type:
            conditions.append('tx_type = %s')
            params.append(tx_type)
        if status:
            conditions.append('status = %s')
            params.append(status)
        where = ' AND '.join(conditions)
        params.extend([limit, offset])
        return self.query_all(
            f"""
            SELECT t.*, u.name AS created_by_name, apr.name AS approved_by_name
            FROM hr.time_bank_transactions t
            LEFT JOIN public.users u ON u.id = t.created_by
            LEFT JOIN public.users apr ON apr.id = t.approved_by
            WHERE {where}
            ORDER BY t.created_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple(params),
        )

    def get_all_transactions(self, limit=100, offset=0, tx_type=None, user_id=None, status=None,
                             date_from=None, date_to=None):
        """Get all transactions (admin view), newest first."""
        conditions = []
        params = []
        if tx_type:
            conditions.append('t.tx_type = %s')
            params.append(tx_type)
        if user_id:
            conditions.append('t.jarvis_user_id = %s')
            params.append(user_id)
        if status:
            conditions.append('t.status = %s')
            params.append(status)
        if date_from:
            conditions.append('t.created_at >= %s::date')
            params.append(date_from)
        if date_to:
            conditions.append('t.created_at < (%s::date + 1)')
            params.append(date_to)
        where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''
        params.extend([limit, offset])
        return self.query_all(
            f"""
            SELECT t.*, emp.name AS employee_name, emp.company AS employee_company,
                   cr.name AS created_by_name, apr.name AS approved_by_name
            FROM hr.time_bank_transactions t
            JOIN public.users emp ON emp.id = t.jarvis_user_id
            LEFT JOIN public.users cr ON cr.id = t.created_by
            LEFT JOIN public.users apr ON apr.id = t.approved_by
            {where}
            ORDER BY t.created_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple(params),
        )

    def count_transactions(self, user_id=None, tx_type=None, status=None, date_from=None, date_to=None):
        """Count transactions (for pagination)."""
        conditions = []
        params = []
        if user_id:
            conditions.append('jarvis_user_id = %s')
            params.append(user_id)
        if tx_type:
            conditions.append('tx_type = %s')
            params.append(tx_type)
        if status:
            conditions.append('status = %s')
            params.append(status)
        if date_from:
            conditions.append('created_at >= %s::date')
            params.append(date_from)
        if date_to:
            conditions.append("created_at < (%s::date + 1)")
            params.append(date_to)
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
