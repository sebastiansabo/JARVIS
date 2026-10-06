"""Time Bank event-pool cap: an auto-approved event-leave debit must never drive
the (hard-capped) event pool below zero, even when the pool dropped between
form-submission validation and this debit.

Regression guard for the gap where `leave_permit_event` skipped the balance check
entirely and could push `event_balance` negative.
"""
from decimal import Decimal

import pytest

import hr.time_bank.service as tb_service
from hr.time_bank.service import TimeBankService


class FakeRepo:
    """Stand-in for TimeBankRepository — no DB. Captures inserts, serves fixed balances."""

    def __init__(self, event_balance=0, balance=0, tx=None):
        self._event_balance = Decimal(str(event_balance))
        self._balance = Decimal(str(balance))
        self._tx = tx
        self.inserted = []
        self.status_updates = []

    def has_reference(self, reference_type, reference_id):
        return False

    def get_event_balance(self, user_id):
        return self._event_balance

    def get_balance(self, user_id):
        return self._balance

    def insert_transaction(self, **kwargs):
        self.inserted.append(kwargs)
        return {'id': len(self.inserted), **kwargs}

    def get_transaction_by_id(self, tx_id):
        return self._tx

    def update_status(self, tx_id, status, approved_by=None):
        self.status_updates.append({'tx_id': tx_id, 'status': status, 'approved_by': approved_by})
        return {'id': tx_id, 'status': status, 'approved_by': approved_by}


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


# ── approve(): personal pool may go negative, event pool must not ──

def _pending(amount, tx_type):
    return {'id': 1, 'jarvis_user_id': 9, 'amount': Decimal(str(amount)),
            'tx_type': tx_type, 'status': 'pending'}


def test_approve_personal_debit_allows_negative_balance(monkeypatch):
    """A pending personal manual_debit approves even when the balance can't cover it —
    the personal pool overdraws by design (regression: approve() used to block this)."""
    repo = FakeRepo(balance=-11, tx=_pending(-4, 'manual_debit'))
    svc = _service_with(repo, monkeypatch)

    row = svc.approve(1, approved_by=49)

    assert row['status'] == 'approved'
    assert repo.status_updates == [{'tx_id': 1, 'status': 'approved', 'approved_by': 49}]


def test_approve_event_debit_blocks_when_over_event_pool(monkeypatch):
    """A pending event-pool debit still hard-blocks if it would drive the event pool
    below zero (the event perk must never go negative)."""
    repo = FakeRepo(event_balance=1, tx=_pending(-4, 'manual_event_debit'))
    svc = _service_with(repo, monkeypatch)

    with pytest.raises(ValueError, match='Insufficient balance'):
        svc.approve(1, approved_by=49)

    assert repo.status_updates == []


def test_approve_event_debit_ok_within_event_pool(monkeypatch):
    """An event-pool debit that fits the event pool approves normally."""
    repo = FakeRepo(event_balance=5, tx=_pending(-4, 'manual_event_debit'))
    svc = _service_with(repo, monkeypatch)

    row = svc.approve(1, approved_by=49)

    assert row['status'] == 'approved'
