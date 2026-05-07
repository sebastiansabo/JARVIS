"""Time Bank business logic."""

import logging
from decimal import Decimal

from .repository import TimeBankRepository

logger = logging.getLogger('jarvis.hr.time_bank.service')


class TimeBankService:
    """Business logic for Time Bank operations."""

    def __init__(self):
        self.repo = TimeBankRepository()

    def credit(self, user_id, amount, tx_type, description=None,
               reference_type=None, reference_id=None, created_by=None):
        """Add hours to an employee's Time Bank.

        Validates amount > 0 and checks idempotency via reference.
        """
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValueError('Credit amount must be positive')

        if reference_type and reference_id:
            if self.repo.has_reference(reference_type, reference_id):
                logger.info('Skipping duplicate credit: %s/%s', reference_type, reference_id)
                return None

        row = self.repo.insert_transaction(
            user_id=user_id,
            amount=amount,
            tx_type=tx_type,
            description=description,
            reference_type=reference_type,
            reference_id=reference_id,
            created_by=created_by,
        )
        logger.info('Time Bank credit: user=%s amount=%s type=%s', user_id, amount, tx_type)
        return row

    def debit(self, user_id, amount, tx_type, description=None,
              reference_type=None, reference_id=None, created_by=None):
        """Deduct hours from an employee's Time Bank.

        Validates amount > 0, checks balance >= amount, and checks idempotency.
        """
        amount = Decimal(str(amount))
        if amount <= 0:
            raise ValueError('Debit amount must be positive')

        if reference_type and reference_id:
            if self.repo.has_reference(reference_type, reference_id):
                logger.info('Skipping duplicate debit: %s/%s', reference_type, reference_id)
                return None

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
        )
        logger.info('Time Bank debit: user=%s amount=-%s type=%s', user_id, amount, tx_type)
        return row

    def get_balance(self, user_id):
        """Get current balance for a user."""
        return float(self.repo.get_balance(user_id))

    def get_all_balances(self, include_all_employees=False):
        """Get all employee balances."""
        rows = self.repo.get_all_balances(include_all_employees=include_all_employees)
        for r in rows:
            r['balance'] = float(r['balance'])
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

    def get_all_transactions(self, limit=100, offset=0, tx_type=None, user_id=None):
        """Get all transactions (admin view)."""
        rows = self.repo.get_all_transactions(
            limit=limit, offset=offset, tx_type=tx_type, user_id=user_id,
        )
        for r in rows:
            r['amount'] = float(r['amount'])
        return rows

    def count_transactions(self, user_id=None, tx_type=None):
        """Count transactions."""
        return self.repo.count_transactions(user_id=user_id, tx_type=tx_type)

    def set_t0(self, user_id, amount, created_by=None):
        """Set T0 (starting balance) for an employee.

        Replaces existing T0 if one exists.
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
        )
        logger.info('Time Bank T0 set: user=%s amount=%s', user_id, amount)
        return row
