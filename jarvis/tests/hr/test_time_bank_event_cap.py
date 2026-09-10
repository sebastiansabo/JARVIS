"""Time Bank event-pool cap: an auto-approved event-leave debit must never drive
the (hard-capped) event pool below zero, even when the pool dropped between
form-submission validation and this debit.

Regression guard for the gap where `leave_permit_event` skipped the balance check
entirely and could push `event_balance` negative.
"""
from decimal import Decimal

import hr.time_bank.service as tb_service
from hr.time_bank.service import TimeBankService


class FakeRepo:
    """Stand-in for TimeBankRepository — no DB. Captures inserts, serves fixed balances."""

    def __init__(self, event_balance=0, balance=0):
        self._event_balance = Decimal(str(event_balance))
        self._balance = Decimal(str(balance))
        self.inserted = []

    def has_reference(self, reference_type, reference_id):
        return False

    def get_event_balance(self, user_id):
        return self._event_balance

    def get_balance(self, user_id):
        return self._balance

    def insert_transaction(self, **kwargs):
        self.inserted.append(kwargs)
        return {'id': len(self.inserted), **kwargs}


def _service_with(repo, monkeypatch):
    """A TimeBankService whose repo is the fake (no DB touched on construction)."""
    monkeypatch.setattr(tb_service, 'TimeBankRepository', lambda: repo)
    return TimeBankService()


def test_event_leave_debit_caps_at_event_pool(monkeypatch):
    """8h event leave against a 3h pool debits only 3h — pool lands at 0, not -5."""
    repo = FakeRepo(event_balance=3)
    svc = _service_with(repo, monkeypatch)

    svc.debit(user_id=9, amount=8, tx_type='leave_permit_event')

    assert len(repo.inserted) == 1
    assert repo.inserted[0]['amount'] == Decimal('-3')


def test_event_leave_debit_empty_pool_records_nothing(monkeypatch):
    """With an empty event pool, an event-leave debit records no row (never negative)."""
    repo = FakeRepo(event_balance=0)
    svc = _service_with(repo, monkeypatch)

    row = svc.debit(user_id=9, amount=8, tx_type='leave_permit_event')

    assert row is None
    assert repo.inserted == []


def test_event_leave_debit_within_pool_charges_full(monkeypatch):
    """When the pool covers it, the full amount is debited (no spurious capping)."""
    repo = FakeRepo(event_balance=10)
    svc = _service_with(repo, monkeypatch)

    svc.debit(user_id=9, amount=8, tx_type='leave_permit_event')

    assert repo.inserted[0]['amount'] == Decimal('-8')


def test_personal_leave_debit_still_allowed_to_go_negative(monkeypatch):
    """Personal leave is unchanged: it may overdraw the personal pool by design."""
    repo = FakeRepo(event_balance=0, balance=0)
    svc = _service_with(repo, monkeypatch)

    svc.debit(user_id=9, amount=8, tx_type='leave_permit')

    assert repo.inserted[0]['amount'] == Decimal('-8')
