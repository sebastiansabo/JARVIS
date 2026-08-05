"""Unit tests for the invoice-issuance Kurs guard.

Regression guard for the missing-Kurs bug: the state machine must refuse to
issue an EUR document when no BNR exchange rate can be resolved, instead of
silently persisting kurs_applied = NULL (which produced storno/final documents
with a blank exchange rate). These tests exercise the pure guard helper and do
not touch the database.
"""
import os
import sys

# Dummy DATABASE_URL so importing DB-backed modules succeeds (no connection is
# opened at import time; the guard helper never queries).
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jarvis'))

from decimal import Decimal
from datetime import date

import pytest

from accounting.facturare.services.invoice_state_machine import (
    InvoiceStateMachine, InvoiceStateMachineError,
)


@pytest.fixture
def sm():
    # object() is a truthy stand-in repo, so __init__ does not build the real
    # DB-backed repository. _require_kurs never touches the repo.
    return InvoiceStateMachine(repo=object())


def test_require_kurs_raises_when_missing(sm):
    with pytest.raises(InvoiceStateMachineError, match="BNR exchange rate"):
        sm._require_kurs(None, date(2026, 7, 31), "Invoice #2")


def test_require_kurs_message_flags_missing_date(sm):
    with pytest.raises(InvoiceStateMachineError, match="without a date"):
        sm._require_kurs(None, None, "Invoice #1")


def test_require_kurs_rejects_zero(sm):
    with pytest.raises(InvoiceStateMachineError):
        sm._require_kurs(Decimal("0"), date(2026, 7, 31), "Final invoice")


def test_require_kurs_passes_when_present(sm):
    # Should not raise.
    sm._require_kurs(Decimal("5.0991"), date(2026, 7, 31), "Invoice #2")
