"""Integration tests for the Task 5 document-number backfill.

Runs against the real localhost Postgres DB (facturare_document_numbers table
must exist — see Task 1-3). Builds a hermetic contract -> anexas -> invoices
fixture and cleans it up by deleting the contract (CASCADE removes anexas,
anexa_lines, invoices, links, and document_numbers).

NOTE: `backfill()` scans the ENTIRE facturare_invoices table (that's its job),
so it also processes whatever pre-existing invoices already live in this dev
DB. That's intentional and exercised here too — the assertions below only
pin down OUR seeded rows, but a non-empty base_mismatches for the whole table
would still (correctly) make the run refuse to write, which would fail these
tests. That's a feature, not a test-isolation bug: it's a real safety net.
"""
import os
import sys
import uuid
import random

JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if JARVIS_ROOT not in sys.path:
    sys.path.insert(0, JARVIS_ROOT)
os.environ.setdefault("DATABASE_URL", "postgresql://localhost/defaultdb")

import psycopg2
import psycopg2.errors
import pytest
from decimal import Decimal

from database import get_db, get_cursor, release_db
from accounting.facturare.repositories.invoice_storage_repository import InvoiceStorageRepository
from accounting.facturare.services.invoice_state_machine import InvoiceStateMachine
from accounting.facturare.scripts.backfill_document_numbers import backfill

# supplier_id=16 (AUTOWORLD S.R.L.) and customer_id=18 are pre-existing rows
# (same convention as test_document_numbers_repo.py / test_state_machine_numbering.py).
SUPPLIER_ID = 16
CUSTOMER_ID = 18
USER_ID = 1


def _rand_base(lo=1_000_000, hi=8_999_990):
    return random.randint(lo, hi)


@pytest.fixture
def repo():
    return InvoiceStorageRepository()


@pytest.fixture
def sm():
    return InvoiceStateMachine()


@pytest.fixture
def seeded():
    """One contract with 4 anexas, cleaned up via CASCADE on contract delete:

      - anexa_pc: 3 lines, will carry a per_car multi-car PROFORMA
      - anexa_sd: 3 lines, will carry a single_doc multi-car PROFORMA
      - anexa_x / anexa_y: 1 line each, seeded directly (bypassing the state
        machine, which only enforces invoice-number uniqueness WITHIN one
        anexa) with the SAME invoice_number on the SAME supplier — this
        reproduces the historical data anomaly the backfill must surface as
        a collision instead of crashing on.

    Yields a dict with anexa ids, line ids, and the pre-picked base numbers.
    """
    conn = get_db(); cur = get_cursor(conn)
    ref = f"TEST-BACKFILL-{uuid.uuid4().hex[:8].upper()}"
    cur.execute(
        """INSERT INTO facturare_contracts (contract_ref, supplier_id, customer_id)
           VALUES (%s, %s, %s) RETURNING id""",
        (ref, SUPPLIER_ID, CUSTOMER_ID))
    contract_id = cur.fetchone()["id"]

    def _make_anexa(n_lines):
        anexa_number = random.randint(900000, 999999)
        cur.execute(
            """INSERT INTO facturare_anexas (contract_id, anexa_number)
               VALUES (%s, %s) RETURNING id""",
            (contract_id, anexa_number))
        anexa_id = cur.fetchone()["id"]
        line_ids = []
        for i in range(n_lines):
            cur.execute(
                """INSERT INTO facturare_anexa_lines
                   (anexa_id, line_number, model, selling_price_eur, list_price_eur)
                   VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                (anexa_id, i + 1, f"TestModel{i}", Decimal("10000"), Decimal("10000")))
            line_ids.append(cur.fetchone()["id"])
        return anexa_id, line_ids

    anexa_pc, lines_pc = _make_anexa(3)
    anexa_sd, lines_sd = _make_anexa(3)
    anexa_x, lines_x = _make_anexa(1)
    anexa_y, lines_y = _make_anexa(1)
    conn.commit()

    dup_number = _rand_base(5_000_000, 5_999_990)
    cur.execute(
        """INSERT INTO facturare_invoices
           (anexa_id, invoice_type, invoice_state, sequence_number, invoice_number,
            total_amount_eur, total_amount_ron, currency, line_ids, doc_mode)
           VALUES (%s,'INVOICE','DRAFT',1,%s,10000,0,'EUR', %s, 'per_car') RETURNING id""",
        (anexa_x, dup_number, f'[{lines_x[0]}]'))
    inv_x_id = cur.fetchone()["id"]
    cur.execute(
        """INSERT INTO facturare_invoices
           (anexa_id, invoice_type, invoice_state, sequence_number, invoice_number,
            total_amount_eur, total_amount_ron, currency, line_ids, doc_mode)
           VALUES (%s,'INVOICE','DRAFT',1,%s,10000,0,'EUR', %s, 'per_car') RETURNING id""",
        (anexa_y, dup_number, f'[{lines_y[0]}]'))
    inv_y_id = cur.fetchone()["id"]
    conn.commit()

    yield {
        "contract_id": contract_id,
        "anexa_pc": anexa_pc, "lines_pc": lines_pc,
        "anexa_sd": anexa_sd, "lines_sd": lines_sd,
        "lines_x": lines_x, "lines_y": lines_y,
        "inv_x_id": inv_x_id, "inv_y_id": inv_y_id,
        "dup_number": dup_number,
    }

    cur.execute("DELETE FROM facturare_contracts WHERE id=%s", (contract_id,))
    conn.commit()
    release_db(conn)


def test_backfill_populates_per_car_and_single_doc_maps_and_reports_collision(sm, repo, seeded):
    pc_base = _rand_base(1_000_000, 1_999_999)
    sd_base = _rand_base(2_000_000, 2_999_999)

    proforma_pc = sm.issue_proforma(
        seeded["anexa_pc"], Decimal("30000"),
        invoice_number=pc_base, doc_mode="per_car",
        created_by_user_id=USER_ID,
    )
    proforma_sd = sm.issue_proforma(
        seeded["anexa_sd"], Decimal("30000"),
        invoice_number=sd_base, doc_mode="single_doc",
        created_by_user_id=USER_ID,
    )

    result = backfill(repo, apply=True)

    assert result["base_mismatches"] == [], result["base_mismatches"]
    assert result["invoices"] >= 4
    assert result["rows_written"] >= 3 + 3 + 1  # pc(3) + sd(3) + one side of the dup pair

    lines_pc = seeded["lines_pc"]
    lines_sd = seeded["lines_sd"]

    assert repo.get_document_number_map(proforma_pc.id) == {
        lines_pc[0]: pc_base,
        lines_pc[1]: pc_base + 1,
        lines_pc[2]: pc_base + 2,
    }
    assert repo.get_document_number_map(proforma_sd.id) == {
        lines_sd[0]: sd_base,
        lines_sd[1]: sd_base,
        lines_sd[2]: sd_base,
    }

    # Exactly one side of the deliberately-duplicated pair collided; the
    # other kept its number. Neither crashed the run.
    inv_x_id, inv_y_id = seeded["inv_x_id"], seeded["inv_y_id"]
    x_map = repo.get_document_number_map(inv_x_id)
    y_map = repo.get_document_number_map(inv_y_id)
    dup_number = seeded["dup_number"]

    collision_ids = {c["invoice_id"] for c in result["collisions"]}
    assert (inv_x_id in collision_ids) ^ (inv_y_id in collision_ids), (
        "expected exactly one of the duplicated-number invoices to collide")

    if inv_x_id in collision_ids:
        winner_id, loser_id, winner_map, loser_map = inv_y_id, inv_x_id, y_map, x_map
        winner_line = seeded["lines_y"][0]
    else:
        winner_id, loser_id, winner_map, loser_map = inv_x_id, inv_y_id, x_map, y_map
        winner_line = seeded["lines_x"][0]

    # The winner got its number written; the loser's write was rolled back entirely.
    assert winner_map == {winner_line: dup_number}
    assert loser_map == {}

    loser_collision = next(c for c in result["collisions"] if c["invoice_id"] == loser_id)
    assert loser_collision["other_invoice_id"] == winner_id
    assert loser_collision["document_number"] == dup_number
    assert loser_collision["supplier_id"] == SUPPLIER_ID
    assert loser_collision["series"] == "fiscal"


def test_backfill_is_idempotent(sm, repo, seeded):
    pc_base = _rand_base(3_000_000, 3_999_999)
    proforma_pc = sm.issue_proforma(
        seeded["anexa_pc"], Decimal("30000"),
        invoice_number=pc_base, doc_mode="per_car",
        created_by_user_id=USER_ID,
    )

    first = backfill(repo, apply=True)
    assert first["base_mismatches"] == []
    map_after_first = repo.get_document_number_map(proforma_pc.id)

    second = backfill(repo, apply=True)
    assert second["base_mismatches"] == []
    map_after_second = repo.get_document_number_map(proforma_pc.id)

    assert map_after_first == map_after_second == {
        seeded["lines_pc"][0]: pc_base,
        seeded["lines_pc"][1]: pc_base + 1,
        seeded["lines_pc"][2]: pc_base + 2,
    }

    # Idempotent: rerunning must not duplicate rows for this invoice.
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute(
            "SELECT COUNT(*) AS c FROM facturare_document_numbers WHERE invoice_id=%s",
            (proforma_pc.id,))
        assert cur.fetchone()["c"] == 3
    finally:
        release_db(conn)

    # Same set of invoices collide on both runs (deterministic, not flaky).
    first_collision_ids = {c["invoice_id"] for c in first["collisions"]}
    second_collision_ids = {c["invoice_id"] for c in second["collisions"]}
    assert first_collision_ids == second_collision_ids


def test_dry_run_predicts_collision_and_writes_nothing(repo, seeded):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("SELECT COUNT(*) AS c FROM facturare_document_numbers")
        before = cur.fetchone()["c"]
    finally:
        release_db(conn)

    result = backfill(repo, apply=False)
    assert result["base_mismatches"] == []

    inv_x_id, inv_y_id = seeded["inv_x_id"], seeded["inv_y_id"]
    collision_ids = {c["invoice_id"] for c in result["collisions"]}
    assert (inv_x_id in collision_ids) ^ (inv_y_id in collision_ids)

    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("SELECT COUNT(*) AS c FROM facturare_document_numbers")
        after = cur.fetchone()["c"]
    finally:
        release_db(conn)
    assert after == before, "dry run must not write anything"


def test_backfill_does_not_swallow_non_collision_integrity_errors(repo, seeded, monkeypatch):
    """Only a genuine ExclusionViolation (the cross-invoice number clash the
    EXCLUDE constraint is designed to reject) may be recorded as a
    `collisions` entry. Any OTHER IntegrityError (NotNullViolation,
    ForeignKeyViolation, CheckViolation, ...) signals a real data/schema bug
    and must propagate and blow up the run instead of being silently
    mislabeled as a collision.
    """
    original_replace = repo.replace_document_numbers
    inv_x_id = seeded["inv_x_id"]

    def _replace_with_injected_error(invoice_id, supplier_id, rows):
        if invoice_id == inv_x_id:
            raise psycopg2.errors.NotNullViolation("simulated non-collision integrity error")
        return original_replace(invoice_id, supplier_id, rows)

    monkeypatch.setattr(repo, "replace_document_numbers", _replace_with_injected_error)

    with pytest.raises(psycopg2.errors.NotNullViolation):
        backfill(repo, apply=True)
