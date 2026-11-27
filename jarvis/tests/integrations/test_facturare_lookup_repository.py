"""FacturareLookupRepository.by_order_numbers — batch lookup by nr_comanda.

DB-backed: joins facturare_anexa_lines -> facturare_invoices via jsonb line_ids.
Uses the dir-scoped require_real_db fixture (tests/integrations/conftest.py).
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import uuid
from datetime import date
from decimal import Decimal

import pytest

from database import get_db, get_cursor, release_db
from accounting.facturare.repositories.invoice_storage_repository import InvoiceStorageRepository
from accounting.facturare.models import InvoiceTypeEnum, InvoiceStateEnum
from core.integrations.facturare_lookup_repository import FacturareLookupRepository

SUPPLIER_ID, CUSTOMER_ID = 16, 18  # AUTOWORLD S.R.L. / customer (pre-existing, per facturare tests)


@pytest.fixture
def seeded(require_real_db):
    repo = InvoiceStorageRepository()
    tag = uuid.uuid4().hex[:8].upper()
    ord_a = f"TORDA-{tag}"   # full document chain
    ord_b = f"TORDB-{tag}"   # anexa line, no invoice
    absent = f"TNONE-{tag}"  # never seeded

    c = repo.create_contract(f"TEST-LOOKUP-{tag}", SUPPLIER_ID, CUSTOMER_ID)
    a = repo.create_anexa(c["id"], 1)
    line_a = repo.create_anexa_line(a["id"], 1, "Audi Q3 Test", Decimal("10000"), Decimal("10000"),
                                    nr_comanda=ord_a, vin=f"VINTEST{tag}")
    repo.create_anexa_line(a["id"], 2, "Audi Q5 Test", Decimal("20000"), Decimal("20000"),
                           nr_comanda=ord_b, vin=f"VINTESB{tag}")
    lids = [line_a["id"]]
    repo.create_invoice(a["id"], InvoiceTypeEnum.PROFORMA, InvoiceStateEnum.DRAFT, Decimal("10000"),
                        invoice_number=206, issued_date=date(2025, 10, 29), line_ids=lids)
    repo.create_invoice(a["id"], InvoiceTypeEnum.INVOICE, InvoiceStateEnum.DRAFT, Decimal("10000"),
                        total_amount_ron=Decimal("50000"), invoice_number=9200850,
                        issued_date=date(2026, 2, 13), line_ids=lids)
    repo.create_invoice(a["id"], InvoiceTypeEnum.STORNO, InvoiceStateEnum.DRAFT, Decimal("-10000"),
                        invoice_number=9200938, issued_date=date(2026, 3, 17), line_ids=lids)
    repo.create_invoice(a["id"], InvoiceTypeEnum.FINAL, InvoiceStateEnum.DRAFT, Decimal("10000"),
                        invoice_number=9200939, issued_date=date(2026, 3, 17), line_ids=lids)

    yield repo, ord_a, ord_b, absent

    conn = get_db(); cur = get_cursor(conn)
    try:
        cur.execute("DELETE FROM facturare_invoices WHERE anexa_id = %s", (a["id"],))
        cur.execute("DELETE FROM facturare_contracts WHERE id = %s", (c["id"],))
        conn.commit()
    finally:
        release_db(conn)


def test_by_order_numbers_returns_chain_and_bare_line(seeded):
    repo, ord_a, ord_b, absent = seeded
    rows = FacturareLookupRepository().by_order_numbers([f" {ord_a} ", ord_b, absent])
    a = [r for r in rows if r["nr_comanda"] == ord_a]
    assert {r["invoice_type"] for r in a} == {"PROFORMA", "INVOICE", "STORNO", "FINAL"}
    assert any(r["invoice_type"] == "FINAL" for r in a)
    b = [r for r in rows if r["nr_comanda"] == ord_b]
    assert len(b) == 1 and b[0]["invoice_number"] is None   # line present, no invoice
    assert all(r["nr_comanda"] != absent for r in rows)      # unknown order absent
