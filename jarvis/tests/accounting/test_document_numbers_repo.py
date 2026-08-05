import os, sys
JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if JARVIS_ROOT not in sys.path:
    sys.path.insert(0, JARVIS_ROOT)
os.environ.setdefault("DATABASE_URL", "postgresql://localhost/defaultdb")

import pytest
from database import get_db, get_cursor, release_db
from accounting.facturare.repositories.invoice_storage_repository import InvoiceStorageRepository


@pytest.fixture
def temp_invoice():
    conn = get_db(); cur = get_cursor(conn)
    # Build the real FK chain: contract -> anexa -> invoice.
    # supplier_id=16 (AUTOWORLD S.R.L.) and customer_id=18 are pre-existing rows.
    cur.execute(
        """INSERT INTO facturare_contracts (contract_ref, supplier_id, customer_id)
           VALUES (%s, 16, 18) RETURNING id""",
        ("TEST-DOCNUM-REPO",))
    contract_id = cur.fetchone()["id"]

    cur.execute(
        """INSERT INTO facturare_anexas (contract_id, anexa_number)
           VALUES (%s, 999999) RETURNING id""",
        (contract_id,))
    anexa_id = cur.fetchone()["id"]

    cur.execute(
        """INSERT INTO facturare_invoices
            (anexa_id, invoice_type, invoice_state, sequence_number, total_amount_eur, total_amount_ron, currency)
            VALUES (%s,'INVOICE','DRAFT',1,0,0,'EUR') RETURNING id""",
        (anexa_id,))
    inv_id = cur.fetchone()["id"]
    conn.commit()

    yield inv_id

    # CASCADE from contract deletion removes anexa -> invoice -> document_numbers
    cur.execute("DELETE FROM facturare_contracts WHERE id=%s", (contract_id,))
    conn.commit()
    release_db(conn)


def test_replace_and_get_map(temp_invoice):
    repo = InvoiceStorageRepository()
    rows = [
        {"line_id": 10, "position": 0, "document_number": 9103042, "series": "fiscal"},
        {"line_id": 11, "position": 1, "document_number": 9103043, "series": "fiscal"},
    ]
    repo.replace_document_numbers(temp_invoice, supplier_id=16, rows=rows)
    # idempotent — second call must not duplicate or raise
    repo.replace_document_numbers(temp_invoice, supplier_id=16, rows=rows)
    assert repo.get_document_number_map(temp_invoice) == {10: 9103042, 11: 9103043}
