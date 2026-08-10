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


# ── Manual kurs override ─────────────────────────────────────────
# When BNR's rate service is unreachable (it now bot-blocks datacenter IPs and
# 302-redirects the XML to its homepage), the user must be able to type the
# official rate manually. _coerce_kurs normalises that input; issue_invoice must
# prefer it over the auto-fetch so issuing never depends on BNR being reachable.

def test_coerce_kurs_normalises_to_four_decimals(sm):
    assert sm._coerce_kurs("5.09123") == Decimal("5.0912")
    assert sm._coerce_kurs(5.1) == Decimal("5.1000")
    assert sm._coerce_kurs(Decimal("5.0991")) == Decimal("5.0991")


def test_coerce_kurs_treats_blank_zero_and_garbage_as_none(sm):
    assert sm._coerce_kurs(None) is None
    assert sm._coerce_kurs("") is None
    assert sm._coerce_kurs(0) is None
    assert sm._coerce_kurs("0") is None
    assert sm._coerce_kurs("abc") is None


class _FakeRepo:
    """Minimal repo so issue_invoice runs without a database."""
    def __init__(self):
        self.created = None

    def get_invoice_by_anexa_type_and_seq(self, anexa_id, inv_type, seq):
        # Proforma exists (kurs NULL, as proformas are always stored); no invoice yet.
        if str(getattr(inv_type, "value", inv_type)) == "PROFORMA":
            return {"id": 1, "total_amount_eur": Decimal("1000"), "kurs_applied": None,
                    "line_ids": None, "doc_mode": "per_car", "split_mode": "equal",
                    "invoice_number": 100}
        return None

    def query_all(self, *a, **k):
        return []

    def query_one(self, *a, **k):
        return {"name": "Tester"}

    def create_invoice(self, **kw):
        self.created = kw
        return {"id": 2, "anexa_id": kw["anexa_id"], "invoice_type": "INVOICE",
                "invoice_state": "DRAFT", "sequence_number": kw["sequence_number"],
                "total_amount_eur": kw["total_amount_eur"], "total_amount_ron": kw["total_amount_ron"],
                "currency": "EUR", "created_at": None, "updated_at": None,
                "invoice_number": kw.get("invoice_number"), "issued_date": kw.get("issued_date"),
                "kurs_applied": kw.get("kurs_applied"), "line_ids": kw.get("line_ids"),
                "doc_mode": kw.get("doc_mode", "per_car")}

    def create_link(self, **kw):
        pass

    # _persist_document_numbers dependencies
    def get_anexa_by_id(self, anexa_id):
        return {"contract_id": 1}

    def get_contract_by_id(self, contract_id):
        return {"supplier_id": 16}

    def get_lines_by_anexa(self, anexa_id):
        return [{"id": 10, "line_number": 1}]

    def replace_document_numbers(self, *a, **k):
        pass


def test_issue_invoice_uses_manual_kurs_without_fetching_bnr():
    """Manual override wins and the (blocked) BNR fetch is never consulted."""
    sm = InvoiceStateMachine(repo=_FakeRepo())

    def _boom(_date):
        raise AssertionError("BNR fetch must not be called when kurs is set manually")
    sm._fetch_kurs = _boom

    inv = sm.issue_invoice(anexa_id=1, sequence_number=1, invoice_number=100,
                           issued_date=date(2026, 8, 6), manual_kurs="5.0812")

    assert inv.kurs_applied == Decimal("5.0812")
    # 1000 EUR * 5.0812 = 5081.20 RON stored
    assert inv.total_amount_ron == Decimal("5081.2000")
    assert sm.repo.created["kurs_applied"] == Decimal("5.0812")
