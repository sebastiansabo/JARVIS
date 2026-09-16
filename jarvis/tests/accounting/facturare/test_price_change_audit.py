"""Real-DB tests for auditing sale-price edits on anexa lines (comenzi).

Finance needs to change an order's selling price after a proforma was already
issued (e.g. 34.550 -> 34.100 EUR on ctr. 2286). The edit must be recorded in
facturare_price_change_log so the change is never silent. Reason is optional.

localhost/defaultdb only — mirrors test_archive_repo.py's require_real_db idiom.
"""
import os
import uuid
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from decimal import Decimal

import pytest

from database import get_db, get_cursor, release_db
from accounting.facturare.repositories.invoice_storage_repository import InvoiceStorageRepository

SUPPLIER_ID = 16   # AUTOWORLD S.R.L. (pre-existing)
CUSTOMER_ID = 18
ACTOR_ID = 1


@pytest.fixture
def line(require_real_db):
    repo = InvoiceStorageRepository()
    ref = f"TEST-PRICE-{uuid.uuid4().hex[:8].upper()}"
    c = repo.create_contract(ref, SUPPLIER_ID, CUSTOMER_ID)
    a = repo.create_anexa(c["id"], 1)
    ln = repo.create_anexa_line(a["id"], 1, "Audi Q3 Sportback 35 TFSI",
                                Decimal("34550"), Decimal("34550"),
                                nr_comanda="151472", vin="WAUZZZFJXT1107487")
    yield repo, ln["id"]
    conn = get_db(); cur = get_cursor(conn)
    try:
        cur.execute("DELETE FROM facturare_contracts WHERE id = %s", (c["id"],)); conn.commit()
    finally:
        release_db(conn)


def _audit_rows(line_id):
    conn = get_db(); cur = get_cursor(conn)
    try:
        cur.execute(
            "SELECT * FROM facturare_price_change_log WHERE anexa_line_id = %s ORDER BY id",
            (line_id,))
        return cur.fetchall()
    finally:
        release_db(conn)


def test_update_selling_price_writes_audit_row(line):
    repo, line_id = line
    row = repo.update_anexa_line_audited(
        line_id, {"selling_price_eur": Decimal("34100")}, actor_id=ACTOR_ID)

    assert row["selling_price_eur"] == Decimal("34100.00")

    audit = _audit_rows(line_id)
    assert len(audit) == 1
    a = audit[0]
    assert a["field"] == "selling"
    assert a["old_price"] == Decimal("34550.00")
    assert a["new_price"] == Decimal("34100.00")
    assert a["changed_by"] == ACTOR_ID
    assert a["change_reason"] is None


def test_non_price_update_writes_no_audit(line):
    repo, line_id = line
    repo.update_anexa_line_audited(
        line_id, {"vin": "WAUZZZFJ1T1111198"}, actor_id=ACTOR_ID)
    assert _audit_rows(line_id) == []


def test_optional_reason_is_stored(line):
    repo, line_id = line
    repo.update_anexa_line_audited(
        line_id, {"selling_price_eur": Decimal("34100")},
        actor_id=ACTOR_ID, reason="Preț redus conf. ctr. 2286")
    audit = _audit_rows(line_id)
    assert len(audit) == 1
    assert audit[0]["change_reason"] == "Preț redus conf. ctr. 2286"


def test_unchanged_price_writes_no_audit(line):
    repo, line_id = line
    # Re-setting the same value must not create a spurious audit row.
    repo.update_anexa_line_audited(
        line_id, {"selling_price_eur": Decimal("34550")}, actor_id=ACTOR_ID)
    assert _audit_rows(line_id) == []
