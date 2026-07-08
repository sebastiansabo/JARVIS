"""Integration tests for the Invoice State Machine.

Runs against the staging PostgreSQL database. Each test uses a unique
cod_comanda prefix and cleans up after itself via the cleanup fixture.

Requires DATABASE_URL env var pointing to staging DB.
"""
import os
import sys
import uuid

import pytest

# Ensure jarvis package root is on sys.path
JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if JARVIS_ROOT not in sys.path:
    sys.path.insert(0, JARVIS_ROOT)

# DATABASE_URL must be provided via the environment — never hardcode credentials.
if not os.environ.get("DATABASE_URL"):
    raise RuntimeError(
        "DATABASE_URL is not set. Export it before running this test, e.g.\n"
        "  export DATABASE_URL='postgresql://doadmin:<password>@<host>:25060/defaultdb?sslmode=require'"
    )

from decimal import Decimal
from datetime import date

from accounting.facturare.services.invoice_state_machine import (
    InvoiceStateMachine, InvoiceStateMachineError,
)
from accounting.facturare.repositories.invoice_storage_repository import (
    InvoiceStorageRepository,
)
from accounting.facturare.schemas import (
    ProformaCreateRequest, AdvanceCreateRequest,
    StornoCreateRequest, FinalCreateRequest, InvoiceLineCreate,
)
from accounting.facturare.models import InvoiceTypeEnum

# Use a real customer_id and supplier_id from staging DB
# company 16 = AUTOWORLD S.R.L., crm_clients id 1 = first client
SUPPLIER_ID = 16
CUSTOMER_ID = 18
USER_ID = 1


def _unique_cod() -> str:
    """Generate a unique cod_comanda for test isolation."""
    return f"TEST-{uuid.uuid4().hex[:8].upper()}"


@pytest.fixture(autouse=True)
def cleanup_test_invoices():
    """Delete all TEST-* invoices after each test."""
    yield
    from database import get_db, get_cursor, release_db
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        # Links are CASCADE-deleted when invoices are deleted
        cursor.execute(
            "DELETE FROM facturare_invoices WHERE cod_comanda LIKE 'TEST-%%'"
        )
    finally:
        release_db(conn)


@pytest.fixture
def sm():
    return InvoiceStateMachine()


def _make_proforma(sm: InvoiceStateMachine, cod: str, amount: Decimal = Decimal("45000")):
    """Helper: issue a standard Proforma."""
    req = ProformaCreateRequest(
        cod_comanda=cod,
        customer_id=CUSTOMER_ID,
        supplier_id=SUPPLIER_ID,
        issued_date=date(2026, 6, 11),
        lines=[
            InvoiceLineCreate(
                vin="WVWZZZ3CZWE000001",
                model="Audi A4",
                culoare="Black",
                list_price_eur=Decimal("50000"),
                selling_price_eur=amount,
                rest_amount_eur=amount,
            )
        ],
    )
    return sm.issue_proforma(req, created_by_user_id=USER_ID)


# ── Test 1: Full lifecycle ───────────────────────────────────────

def test_full_invoice_lifecycle(sm):
    """Proforma → Advance(2x) → Storno → Final."""
    cod = _unique_cod()

    # 1. Proforma
    proforma = _make_proforma(sm, cod)
    assert proforma.invoice_type == InvoiceTypeEnum.PROFORMA
    assert proforma.total_amount_eur == Decimal("45000")

    # 2. Advance #1
    adv1 = sm.issue_advance(
        AdvanceCreateRequest(
            cod_comanda=cod, advance_number=1,
            amount_eur=Decimal("15000"), issued_date=date(2026, 6, 12),
        ),
        created_by_user_id=USER_ID,
    )
    assert adv1.invoice_type == InvoiceTypeEnum.ADVANCE
    assert adv1.total_amount_eur == Decimal("15000")

    # 3. Advance #2
    adv2 = sm.issue_advance(
        AdvanceCreateRequest(
            cod_comanda=cod, advance_number=2,
            amount_eur=Decimal("15000"), issued_date=date(2026, 6, 13),
        ),
        created_by_user_id=USER_ID,
    )
    assert adv2.total_amount_eur == Decimal("15000")

    # 4. Storno — reverses Proforma(45k) + Adv1(15k) + Adv2(15k) = -75k
    storno = sm.issue_storno(
        StornoCreateRequest(cod_comanda=cod, issued_date=date(2026, 6, 14)),
        created_by_user_id=USER_ID,
    )
    assert storno.invoice_type == InvoiceTypeEnum.STORNO
    assert storno.total_amount_eur == Decimal("-75000")

    # 5. Final — abs(Storno) = 75k
    final = sm.issue_final(
        FinalCreateRequest(cod_comanda=cod, issued_date=date(2026, 6, 15)),
        created_by_user_id=USER_ID,
    )
    assert final.invoice_type == InvoiceTypeEnum.FINAL
    assert final.total_amount_eur == Decimal("75000")

    # Verify full chain
    all_invoices = sm.get_invoices_by_cod_comanda(cod)
    assert len(all_invoices) == 5  # Proforma + 2 Advances + Storno + Final


# ── Test 2: Storno without advance (allowed) ────────────────────

def test_storno_without_advance_succeeds(sm):
    """Storno only needs a Proforma — advances are optional."""
    cod = _unique_cod()
    _make_proforma(sm, cod, Decimal("55000"))

    storno = sm.issue_storno(
        StornoCreateRequest(cod_comanda=cod),
        created_by_user_id=USER_ID,
    )
    assert storno.total_amount_eur == Decimal("-55000")


# ── Test 3: Duplicate proforma fails ────────────────────────────

def test_duplicate_proforma_fails(sm):
    """Cannot issue two Proformas for same cod_comanda."""
    cod = _unique_cod()
    _make_proforma(sm, cod)

    with pytest.raises(InvoiceStateMachineError, match="Proforma already exists"):
        _make_proforma(sm, cod)


# ── Test 4: Advance exceeds proforma fails ──────────────────────

def test_advance_exceeds_proforma_fails(sm):
    """Advance total cannot exceed Proforma total."""
    cod = _unique_cod()
    _make_proforma(sm, cod, Decimal("70000"))

    with pytest.raises(InvoiceStateMachineError, match="exceed Proforma total"):
        sm.issue_advance(
            AdvanceCreateRequest(
                cod_comanda=cod, advance_number=1,
                amount_eur=Decimal("75000"),
            ),
            created_by_user_id=USER_ID,
        )


# ── Test 5: can_transition validation ───────────────────────────

def test_can_transition_validation(sm):
    """can_transition() returns correct allowed/denied states."""
    cod = _unique_cod()

    # No invoices yet → can create Proforma
    can, reason = sm.can_transition(cod, InvoiceTypeEnum.PROFORMA)
    assert can is True

    # After Proforma → can't create another
    _make_proforma(sm, cod)
    can, reason = sm.can_transition(cod, InvoiceTypeEnum.PROFORMA)
    assert can is False
    assert "already exists" in reason

    # Can create Advance
    can, reason = sm.can_transition(cod, InvoiceTypeEnum.ADVANCE)
    assert can is True

    # Can't create Final (no Storno yet)
    can, reason = sm.can_transition(cod, InvoiceTypeEnum.FINAL)
    assert can is False
    assert "Storno required" in reason


# ── Test 6: Max 3 advances ──────────────────────────────────────

def test_max_three_advances(sm):
    """Cannot issue more than 3 advances.

    Two layers of defense:
    - Pydantic rejects advance_number > 3 at schema level
    - State machine rejects 4th advance at business logic level
    """
    cod = _unique_cod()
    _make_proforma(sm, cod, Decimal("90000"))

    for i in range(1, 4):
        sm.issue_advance(
            AdvanceCreateRequest(
                cod_comanda=cod, advance_number=i,
                amount_eur=Decimal("10000"),
            ),
            created_by_user_id=USER_ID,
        )

    # Pydantic rejects advance_number=4 before it reaches the state machine
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="less than or equal to 3"):
        AdvanceCreateRequest(
            cod_comanda=cod, advance_number=4,
            amount_eur=Decimal("10000"),
        )

    # State machine also rejects a 4th advance even with advance_number=3 (reuse)
    with pytest.raises(InvoiceStateMachineError, match="Maximum 3"):
        sm.issue_advance(
            AdvanceCreateRequest(
                cod_comanda=cod, advance_number=3,
                amount_eur=Decimal("10000"),
            ),
            created_by_user_id=USER_ID,
        )


# ── Test 7: Final without storno fails ──────────────────────────

def test_final_without_storno_fails(sm):
    """Cannot issue Final without Storno."""
    cod = _unique_cod()
    _make_proforma(sm, cod)

    with pytest.raises(InvoiceStateMachineError, match="Storno required"):
        sm.issue_final(
            FinalCreateRequest(cod_comanda=cod),
            created_by_user_id=USER_ID,
        )


# ── Test 8: Advance without proforma fails ──────────────────────

def test_advance_without_proforma_fails(sm):
    """Cannot issue Advance without a Proforma."""
    cod = _unique_cod()

    with pytest.raises(InvoiceStateMachineError, match="Proforma required"):
        sm.issue_advance(
            AdvanceCreateRequest(
                cod_comanda=cod, advance_number=1,
                amount_eur=Decimal("10000"),
            ),
            created_by_user_id=USER_ID,
        )
