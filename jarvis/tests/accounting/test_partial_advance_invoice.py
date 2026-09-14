"""Integration tests: partial advance invoice (factura de avans parțială).

A single proforma covering N cars can be confirmed by MULTIPLE advance invoices,
each over a disjoint subset of the proforma's lines. This lets accounting invoice
only the cars that were actually paid (e.g. 5 of 7) and issue the rest later.

Runs against the real localhost Postgres DB. Builds a hermetic
contract -> anexa -> anexa_lines fixture and cleans it up by deleting the
contract (CASCADE removes anexa, anexa_lines, invoices, links, document_numbers).

Run with a real DB (psycopg2 must be pre-imported so jarvis/conftest.py does NOT
install its MagicMock):

    DATABASE_URL='postgresql://localhost/defaultdb' \
    python -c "import psycopg2, psycopg2.pool, psycopg2.extras, psycopg2.errors, pytest, sys; \
               sys.exit(pytest.main(['jarvis/tests/accounting/test_partial_advance_invoice.py','-q']))"
"""
import os
import sys
import uuid
import random

JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if JARVIS_ROOT not in sys.path:
    sys.path.insert(0, JARVIS_ROOT)
os.environ.setdefault("DATABASE_URL", "postgresql://localhost/defaultdb")

import pytest
from decimal import Decimal
from datetime import date

from database import get_db, get_cursor, release_db
from accounting.facturare.services.invoice_state_machine import (
    InvoiceStateMachine, InvoiceStateMachineError,
)
from accounting.facturare.repositories.invoice_storage_repository import InvoiceStorageRepository

SUPPLIER_ID = 16   # AUTOWORLD S.R.L.
CUSTOMER_ID = 18
USER_ID = 1
KURS = Decimal("5.0")          # manual kurs so tests never depend on the BNR service
ISSUED = date(2026, 8, 25)


@pytest.fixture
def make_anexa():
    """Factory: build a contract -> anexa with the given per-line selling prices.

    Returns (anexa_id, [line_id, ...]) in line_number order. All created
    contracts are deleted (CASCADE) at teardown.
    """
    created = []
    conn = get_db(); cur = get_cursor(conn)

    def _make(prices):
        ref = f"TEST-PAI-{uuid.uuid4().hex[:8].upper()}"
        cur.execute(
            """INSERT INTO facturare_contracts (contract_ref, supplier_id, customer_id)
               VALUES (%s, %s, %s) RETURNING id""",
            (ref, SUPPLIER_ID, CUSTOMER_ID))
        contract_id = cur.fetchone()["id"]
        created.append(contract_id)
        cur.execute(
            """INSERT INTO facturare_anexas (contract_id, anexa_number)
               VALUES (%s, %s) RETURNING id""",
            (contract_id, random.randint(900000, 999999)))
        anexa_id = cur.fetchone()["id"]
        line_ids = []
        for i, price in enumerate(prices):
            cur.execute(
                """INSERT INTO facturare_anexa_lines
                   (anexa_id, line_number, model, selling_price_eur, list_price_eur)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (anexa_id, i + 1, f"Model{i}", Decimal(str(price)), Decimal(str(price))))
            line_ids.append(cur.fetchone()["id"])
        conn.commit()
        return anexa_id, line_ids

    yield _make

    for cid in created:
        cur.execute("DELETE FROM facturare_contracts WHERE id=%s", (cid,))
    conn.commit()
    release_db(conn)


@pytest.fixture
def sm():
    return InvoiceStateMachine()


@pytest.fixture
def repo():
    return InvoiceStorageRepository()


def _base():
    return random.randint(1_000_000, 8_999_990)


def _line_ids_of(repo, inv, all_line_ids):
    """Resolve a stored invoice's covered lines (None stored == whole anexa)."""
    import json
    raw = repo.get_invoice_by_id(inv.id).get("line_ids")
    if isinstance(raw, str):
        raw = json.loads(raw)
    return set(raw) if raw else set(all_line_ids)


# ── 1. Partial invoice covers only the selected lines, proforma stays open ──

def test_partial_invoice_covers_subset_only(sm, repo, make_anexa):
    anexa_id, lids = make_anexa([10000, 20000, 30000])
    prof = sm.issue_proforma(anexa_id, Decimal("60000"), split_mode="proportional",
                             invoice_number=_base(), issued_date=ISSUED,
                             created_by_user_id=USER_ID)

    inv = sm.issue_invoice(anexa_id, sequence_number=prof.sequence_number,
                           invoice_number=_base(), issued_date=ISSUED,
                           line_ids=[lids[0], lids[1]], manual_kurs=KURS,
                           created_by_user_id=USER_ID)

    assert _line_ids_of(repo, inv, lids) == {lids[0], lids[1]}
    assert Decimal(str(inv.total_amount_eur)) == Decimal("30000")     # 10000 + 20000
    assert inv.sequence_number == prof.sequence_number               # invoice keyed to its proforma

    # Proforma still has line 3 uninvoiced -> still offered for INVOICE.
    unpaired = sm.get_unpaired_proformas(anexa_id)
    assert len(unpaired) == 1
    assert set(unpaired[0]["remaining_line_ids"]) == {lids[2]}
    assert "INVOICE" in sm.get_next_actions(anexa_id)


# ── 2. Second partial completes the proforma; totals reconcile exactly ──

def test_second_partial_completes_and_reconciles(sm, repo, make_anexa):
    anexa_id, lids = make_anexa([10000, 20000, 30000])
    prof = sm.issue_proforma(anexa_id, Decimal("60000"), split_mode="proportional",
                             invoice_number=_base(), issued_date=ISSUED,
                             created_by_user_id=USER_ID)

    inv1 = sm.issue_invoice(anexa_id, sequence_number=prof.sequence_number,
                            invoice_number=_base(), issued_date=ISSUED,
                            line_ids=[lids[0], lids[1]], manual_kurs=KURS,
                            created_by_user_id=USER_ID)
    inv2 = sm.issue_invoice(anexa_id, sequence_number=prof.sequence_number,
                            invoice_number=_base(), issued_date=ISSUED,
                            line_ids=[lids[2]], manual_kurs=KURS,
                            created_by_user_id=USER_ID)

    assert Decimal(str(inv2.total_amount_eur)) == Decimal("30000")
    total = Decimal(str(inv1.total_amount_eur)) + Decimal(str(inv2.total_amount_eur))
    assert total == Decimal("60000")                                  # sums to proforma total

    assert sm.get_unpaired_proformas(anexa_id) == []                  # nothing left to invoice
    assert "INVOICE" not in sm.get_next_actions(anexa_id)


# ── 3. line_ids=None confirms only the REMAINING lines (closing remainder) ──

def test_none_confirms_remaining_lines(sm, repo, make_anexa):
    anexa_id, lids = make_anexa([10000, 20000, 30000])
    prof = sm.issue_proforma(anexa_id, Decimal("60000"), split_mode="proportional",
                             invoice_number=_base(), issued_date=ISSUED,
                             created_by_user_id=USER_ID)

    sm.issue_invoice(anexa_id, sequence_number=prof.sequence_number,
                     invoice_number=_base(), issued_date=ISSUED,
                     line_ids=[lids[0]], manual_kurs=KURS, created_by_user_id=USER_ID)
    inv2 = sm.issue_invoice(anexa_id, sequence_number=prof.sequence_number,
                            invoice_number=_base(), issued_date=ISSUED,
                            line_ids=None, manual_kurs=KURS, created_by_user_id=USER_ID)

    assert _line_ids_of(repo, inv2, lids) == {lids[1], lids[2]}
    assert Decimal(str(inv2.total_amount_eur)) == Decimal("50000")    # remainder 60000 - 10000
    assert sm.get_unpaired_proformas(anexa_id) == []


# ── 4. Backward compat: whole proforma in one shot (line_ids=None, untouched) ──

def test_full_confirm_backward_compatible(sm, repo, make_anexa):
    anexa_id, lids = make_anexa([10000, 20000, 30000])
    prof = sm.issue_proforma(anexa_id, Decimal("60000"), split_mode="proportional",
                             invoice_number=_base(), issued_date=ISSUED,
                             created_by_user_id=USER_ID)

    inv = sm.issue_invoice(anexa_id, sequence_number=prof.sequence_number,
                           invoice_number=_base(), issued_date=ISSUED,
                           line_ids=None, manual_kurs=KURS, created_by_user_id=USER_ID)

    assert Decimal(str(inv.total_amount_eur)) == Decimal("60000")
    assert _line_ids_of(repo, inv, lids) == set(lids)                  # whole anexa
    assert sm.get_unpaired_proformas(anexa_id) == []


# ── 5. Equal split reconciles via the closing slice (333 + 333 + 334) ──

def test_equal_split_partials_reconcile(sm, repo, make_anexa):
    anexa_id, lids = make_anexa([10000, 10000, 10000])
    prof = sm.issue_proforma(anexa_id, Decimal("1000"), split_mode="equal",
                             invoice_number=_base(), issued_date=ISSUED,
                             created_by_user_id=USER_ID)

    a = sm.issue_invoice(anexa_id, sequence_number=prof.sequence_number, invoice_number=_base(),
                         issued_date=ISSUED, line_ids=[lids[0]], manual_kurs=KURS, created_by_user_id=USER_ID)
    b = sm.issue_invoice(anexa_id, sequence_number=prof.sequence_number, invoice_number=_base(),
                         issued_date=ISSUED, line_ids=[lids[1]], manual_kurs=KURS, created_by_user_id=USER_ID)
    c = sm.issue_invoice(anexa_id, sequence_number=prof.sequence_number, invoice_number=_base(),
                         issued_date=ISSUED, line_ids=[lids[2]], manual_kurs=KURS, created_by_user_id=USER_ID)

    totals = sorted(Decimal(str(x.total_amount_eur)) for x in (a, b, c))
    assert totals == [Decimal("333"), Decimal("333"), Decimal("334")]
    assert sum(totals) == Decimal("1000")


# ── 6. Reject re-invoicing a line already covered under this proforma ──

def test_reject_double_invoicing_line(sm, repo, make_anexa):
    anexa_id, lids = make_anexa([10000, 20000, 30000])
    prof = sm.issue_proforma(anexa_id, Decimal("60000"), split_mode="proportional",
                             invoice_number=_base(), issued_date=ISSUED,
                             created_by_user_id=USER_ID)
    sm.issue_invoice(anexa_id, sequence_number=prof.sequence_number, invoice_number=_base(),
                     issued_date=ISSUED, line_ids=[lids[0]], manual_kurs=KURS, created_by_user_id=USER_ID)

    with pytest.raises(InvoiceStateMachineError, match="already"):
        sm.issue_invoice(anexa_id, sequence_number=prof.sequence_number, invoice_number=_base(),
                         issued_date=ISSUED, line_ids=[lids[0], lids[1]], manual_kurs=KURS,
                         created_by_user_id=USER_ID)


# ── 7. Reject a line that is not part of the selected proforma ──

def test_reject_line_outside_proforma(sm, repo, make_anexa):
    anexa_id, lids = make_anexa([10000, 20000, 30000])
    prof = sm.issue_proforma(anexa_id, Decimal("30000"), split_mode="proportional",
                             invoice_number=_base(), issued_date=ISSUED,
                             line_ids=[lids[0], lids[1]], created_by_user_id=USER_ID)

    with pytest.raises(InvoiceStateMachineError, match="not (in|part)"):
        sm.issue_invoice(anexa_id, sequence_number=prof.sequence_number, invoice_number=_base(),
                         issued_date=ISSUED, line_ids=[lids[2]], manual_kurs=KURS,
                         created_by_user_id=USER_ID)


# ── 8. Per-car document numbers still allocate over the subset ──

def test_partial_invoice_allocates_per_car_numbers(sm, repo, make_anexa):
    anexa_id, lids = make_anexa([10000, 20000, 30000])
    prof = sm.issue_proforma(anexa_id, Decimal("60000"), split_mode="proportional",
                             invoice_number=_base(), issued_date=ISSUED,
                             created_by_user_id=USER_ID)
    base = _base()
    inv = sm.issue_invoice(anexa_id, sequence_number=prof.sequence_number, invoice_number=base,
                           issued_date=ISSUED, line_ids=[lids[0], lids[1]], manual_kurs=KURS,
                           doc_mode="per_car", created_by_user_id=USER_ID)

    m = repo.get_document_number_map(inv.id)
    assert m == {lids[0]: base, lids[1]: base + 1}
