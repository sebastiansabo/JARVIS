"""Integration tests: issuing invoices persists per-document (per-car) numbers.

Runs against the real localhost Postgres DB (facturare_document_numbers table
must exist — see Task 3). Builds a hermetic contract -> anexa -> anexa_lines
fixture and cleans it up by deleting the contract (CASCADE removes anexa,
anexa_lines, invoices, links, and document_numbers).
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

from database import get_db, get_cursor, release_db
from accounting.facturare.services.invoice_state_machine import InvoiceStateMachine
from accounting.facturare.repositories.invoice_storage_repository import InvoiceStorageRepository

# supplier_id=16 (AUTOWORLD S.R.L.) and customer_id=18 are pre-existing rows
# (same convention as test_document_numbers_repo.py).
SUPPLIER_ID = 16
CUSTOMER_ID = 18
USER_ID = 1


@pytest.fixture
def anexa3():
    """Contract -> Anexa -> 3 vehicle lines (10000 EUR each), cleaned up after."""
    conn = get_db(); cur = get_cursor(conn)
    ref = f"TEST-SM-NUM-{uuid.uuid4().hex[:8].upper()}"
    cur.execute(
        """INSERT INTO facturare_contracts (contract_ref, supplier_id, customer_id)
           VALUES (%s, %s, %s) RETURNING id""",
        (ref, SUPPLIER_ID, CUSTOMER_ID))
    contract_id = cur.fetchone()["id"]

    anexa_number = random.randint(900000, 999999)
    cur.execute(
        """INSERT INTO facturare_anexas (contract_id, anexa_number)
           VALUES (%s, %s) RETURNING id""",
        (contract_id, anexa_number))
    anexa_id = cur.fetchone()["id"]

    line_ids = []
    for i in range(3):
        cur.execute(
            """INSERT INTO facturare_anexa_lines
               (anexa_id, line_number, model, selling_price_eur, list_price_eur)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (anexa_id, i + 1, f"TestModel{i}", Decimal("10000"), Decimal("10000")))
        line_ids.append(cur.fetchone()["id"])
    conn.commit()

    yield anexa_id, line_ids

    # CASCADE from contract deletion removes anexa -> lines -> invoices
    # -> invoice_links -> document_numbers.
    cur.execute("DELETE FROM facturare_contracts WHERE id=%s", (contract_id,))
    conn.commit()
    release_db(conn)


@pytest.fixture
def sm():
    return InvoiceStateMachine()


@pytest.fixture
def repo():
    return InvoiceStorageRepository()


def _rand_base(lo=1_000_000, hi=8_999_990):
    return random.randint(lo, hi)


# ── Case 1: per_car mode over 3 lines ────────────────────────────

def test_issue_proforma_persists_per_car_numbers(sm, repo, anexa3):
    anexa_id, line_ids = anexa3
    base = _rand_base()

    inv = sm.issue_proforma(
        anexa_id, Decimal("30000"),
        invoice_number=base, doc_mode="per_car",
        created_by_user_id=USER_ID,
    )

    m = repo.get_document_number_map(inv.id)
    assert m == {
        line_ids[0]: base,
        line_ids[1]: base + 1,
        line_ids[2]: base + 2,
    }


# ── Case 2: single_doc mode over 3 lines ─────────────────────────
#
# All 3 cars of a single_doc invoice share ONE document_number. This works
# because Task 2's uniqueness rule is now an EXCLUDE constraint
# (excl_facturare_docnum_cross_invoice) that only forbids reuse ACROSS
# different invoices, permitting the same number within one invoice's rows.
def test_issue_proforma_persists_single_doc_numbers(sm, repo, anexa3):
    anexa_id, line_ids = anexa3
    base = _rand_base()

    inv = sm.issue_proforma(
        anexa_id, Decimal("30000"),
        invoice_number=base, doc_mode="single_doc",
        created_by_user_id=USER_ID,
    )

    m = repo.get_document_number_map(inv.id)
    assert m == {
        line_ids[0]: base,
        line_ids[1]: base,
        line_ids[2]: base,
    }


# ── Case 3 (strongly encouraged): proforma -> invoice -> storno lifecycle ──
# for a single car; storno's stored number must equal the storno's own
# invoice_number (single target line => position 0).

def test_storno_persists_own_number_for_single_car(sm, repo, anexa3):
    anexa_id, line_ids = anexa3
    target_line = line_ids[0]

    proforma_base = _rand_base(1_000_000, 1_999_999)
    proforma = sm.issue_proforma(
        anexa_id, Decimal("10000"),
        invoice_number=proforma_base, line_ids=[target_line],
        created_by_user_id=USER_ID,
    )
    assert repo.get_document_number_map(proforma.id) == {target_line: proforma_base}

    invoice_base = _rand_base(2_000_000, 2_999_999)
    invoice = sm.issue_invoice(
        anexa_id, sequence_number=proforma.sequence_number,
        invoice_number=invoice_base,
        created_by_user_id=USER_ID,
    )
    assert repo.get_document_number_map(invoice.id) == {target_line: invoice_base}

    storno_base = _rand_base(3_000_000, 3_999_999)
    storno = sm.issue_storno(
        anexa_id, invoice_number=storno_base, line_ids=[target_line],
        created_by_user_id=USER_ID,
    )

    m = repo.get_document_number_map(storno.id)
    assert m == {target_line: storno_base}
    assert m[target_line] == storno_base  # position 0 == the storno's own invoice_number
