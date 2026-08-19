"""Time Bank business logic."""

import logging
from decimal import Decimal

from .repository import TimeBankRepository

logger = logging.getLogger('jarvis.hr.time_bank.service')

# tx_types that are auto-approved (no manual approval needed)
AUTO_APPROVED_TYPES = ('T0', 'marketing_event', 'co_conversion', 'connecteam', 'leave_permit', 'leave_permit_reversal')


class TimeBankService:
    """Business logic for Time Bank operations."""

    def __init__(self):
        self.repo = TimeBankRepository()

    def credit(self, user_id, amount, tx_type, description=None,
               reference_type=None, reference_id=None, created_by=None):
        """Add hours to an employee's Time Bank.

        Manual credits start as 'pending'. System credits auto-approve.
        """
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValueError('Credit amount must be positive')

        if reference_type and reference_id:
            if self.repo.has_reference(reference_type, reference_id):
                logger.info('Skipping duplicate credit: %s/%s', reference_type, reference_id)
                return None

        status = 'approved' if tx_type in AUTO_APPROVED_TYPES else 'pending'
        row = self.repo.insert_transaction(
            user_id=user_id,
            amount=amount,
            tx_type=tx_type,
            description=description,
            reference_type=reference_type,
            reference_id=reference_id,
            created_by=created_by,
            status=status,
        )
        logger.info('Time Bank credit: user=%s amount=%s type=%s status=%s', user_id, amount, tx_type, status)
        return row

    def debit(self, user_id, amount, tx_type, description=None,
              reference_type=None, reference_id=None, created_by=None):
        """Deduct hours from an employee's Time Bank.

        Manual debits start as 'pending'. System debits auto-approve.
        """
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValueError('Debit amount must be positive')

        if reference_type and reference_id:
            if self.repo.has_reference(reference_type, reference_id):
                logger.info('Skipping duplicate debit: %s/%s', reference_type, reference_id)
                return None

        status = 'approved' if tx_type in AUTO_APPROVED_TYPES else 'pending'

        # Only check balance for auto-approved debits (pending ones don't affect balance yet)
        # Skip balance check for system imports (connecteam) — T0 may not be set yet
        if status == 'approved' and tx_type not in ('connecteam', 'leave_permit'):
            balance = self.repo.get_balance(user_id)
            if balance < amount:
                raise ValueError(
                    f'Insufficient balance: {balance}h available, {amount}h requested'
                )

        row = self.repo.insert_transaction(
            user_id=user_id,
            amount=-amount,
            tx_type=tx_type,
            description=description,
            reference_type=reference_type,
            reference_id=reference_id,
            created_by=created_by,
            status=status,
        )
        logger.info('Time Bank debit: user=%s amount=-%s type=%s status=%s', user_id, amount, tx_type, status)
        return row

    def approve(self, tx_id, approved_by):
        """Approve a pending transaction."""
        tx = self.repo.get_transaction_by_id(tx_id)
        if not tx:
            raise ValueError('Transaction not found')
        if tx['status'] != 'pending':
            raise ValueError(f"Cannot approve: transaction is already '{tx['status']}'")

        # For debits, check balance before approving
        if tx['amount'] < 0:
            balance = self.repo.get_balance(tx['jarvis_user_id'])
            needed = abs(tx['amount'])
            if balance < needed:
                raise ValueError(
                    f'Insufficient balance: {balance}h available, {needed}h requested'
                )

        row = self.repo.update_status(tx_id, 'approved', approved_by=approved_by)
        logger.info('Time Bank approved: tx=%s by=%s', tx_id, approved_by)
        return row

    def reject(self, tx_id, approved_by):
        """Reject a pending transaction."""
        tx = self.repo.get_transaction_by_id(tx_id)
        if not tx:
            raise ValueError('Transaction not found')
        if tx['status'] != 'pending':
            raise ValueError(f"Cannot reject: transaction is already '{tx['status']}'")

        row = self.repo.update_status(tx_id, 'rejected', approved_by=approved_by)
        logger.info('Time Bank rejected: tx=%s by=%s', tx_id, approved_by)
        return row

    def mark_processed(self, tx_id, approved_by):
        """Mark an approved transaction as processed."""
        tx = self.repo.get_transaction_by_id(tx_id)
        if not tx:
            raise ValueError('Transaction not found')
        if tx['status'] != 'approved':
            raise ValueError(f"Cannot process: transaction is '{tx['status']}', must be 'approved'")

        row = self.repo.update_status(tx_id, 'processed', approved_by=approved_by)
        logger.info('Time Bank processed: tx=%s by=%s', tx_id, approved_by)
        return row

    def get_balance(self, user_id):
        """Get current balance for a user."""
        return float(self.repo.get_balance(user_id))

    def get_all_balances(self, include_all_employees=False):
        """Get all employee balances."""
        rows = self.repo.get_all_balances(include_all_employees=include_all_employees)
        for r in rows:
            r['balance'] = float(r['balance'])
            r['pending_count'] = int(r.get('pending_count', 0))
        return rows

    def get_balances_for_users(self, user_ids):
        """Get balances for specific users."""
        balances = self.repo.get_balances_for_users(user_ids)
        return {uid: float(bal) for uid, bal in balances.items()}

    def get_transactions(self, user_id, limit=50, offset=0, tx_type=None):
        """Get transactions for a user."""
        rows = self.repo.get_transactions(user_id, limit=limit, offset=offset, tx_type=tx_type)
        for r in rows:
            r['amount'] = float(r['amount'])
        return rows

    def get_all_transactions(self, limit=100, offset=0, tx_type=None, user_id=None, status=None,
                             date_from=None, date_to=None):
        """Get all transactions (admin view)."""
        rows = self.repo.get_all_transactions(
            limit=limit, offset=offset, tx_type=tx_type, user_id=user_id, status=status,
            date_from=date_from, date_to=date_to,
        )
        for r in rows:
            r['amount'] = float(r['amount'])
        return rows

    def count_transactions(self, user_id=None, tx_type=None, status=None, date_from=None, date_to=None):
        """Count transactions."""
        return self.repo.count_transactions(user_id=user_id, tx_type=tx_type, status=status,
                                            date_from=date_from, date_to=date_to)

    def set_t0(self, user_id, amount, created_by=None):
        """Set T0 (starting balance) for an employee.

        T0 is auto-approved. Replaces existing T0 if one exists.
        """
        amount = Decimal(str(amount))
        if amount < 0:
            raise ValueError('T0 amount cannot be negative')

        # Remove existing T0 before inserting new one
        if self.repo.has_t0(user_id):
            self.repo.delete_t0(user_id)

        if amount == 0:
            return None

        row = self.repo.insert_transaction(
            user_id=user_id,
            amount=amount,
            tx_type='T0',
            description='Starting balance (T0)',
            created_by=created_by,
            status='approved',
        )
        logger.info('Time Bank T0 set: user=%s amount=%s', user_id, amount)
        return row
