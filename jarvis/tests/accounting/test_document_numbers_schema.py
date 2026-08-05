import os, sys
import uuid
import random

JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if JARVIS_ROOT not in sys.path:
    sys.path.insert(0, JARVIS_ROOT)
os.environ.setdefault("DATABASE_URL", "postgresql://localhost/defaultdb")

import psycopg2
import pytest
from database import get_db, get_cursor, release_db

SUPPLIER_ID = 16
CUSTOMER_ID = 18


def test_document_numbers_table_and_exclude_constraint_exist():
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'facturare_document_numbers' ORDER BY column_name
        """)
        cols = {r["column_name"] for r in cur.fetchall()}
        assert {"id","invoice_id","supplier_id","series","line_id","position","document_number","created_at"} <= cols
        # The uniqueness rule is now an EXCLUDE constraint (contype='x'), NOT a
        # plain UNIQUE index — a plain UNIQUE would reject single_doc multi-car
        # rows that legitimately share one document_number within one invoice.
        cur.execute("""
            SELECT contype FROM pg_constraint
            WHERE conname = 'excl_facturare_docnum_cross_invoice'
        """)
        row = cur.fetchone()
        assert row is not None, "excl_facturare_docnum_cross_invoice constraint missing"
        assert row["contype"] == "x", "constraint must be an EXCLUDE constraint (contype='x')"
    finally:
        release_db(conn)


@pytest.fixture
def two_invoices():
    """Contract -> anexa -> two DRAFT invoices; cleaned up via contract CASCADE.

    Yields (supplier_id, invoice_a_id, invoice_b_id).
    """
    conn = get_db(); cur = get_cursor(conn)
    ref = f"TEST-EXCL-{uuid.uuid4().hex[:8].upper()}"
    cur.execute(
        """INSERT INTO facturare_contracts (contract_ref, supplier_id, customer_id)
           VALUES (%s, %s, %s) RETURNING id""",
        (ref, SUPPLIER_ID, CUSTOMER_ID))
    contract_id = cur.fetchone()["id"]

    cur.execute(
        """INSERT INTO facturare_anexas (contract_id, anexa_number)
           VALUES (%s, %s) RETURNING id""",
        (contract_id, random.randint(900000, 999999)))
    anexa_id = cur.fetchone()["id"]

    inv_ids = []
    for seq in (1, 2):
        cur.execute(
            """INSERT INTO facturare_invoices
               (anexa_id, invoice_type, invoice_state, sequence_number,
                total_amount_eur, total_amount_ron, currency)
               VALUES (%s,'INVOICE','DRAFT',%s,0,0,'EUR') RETURNING id""",
            (anexa_id, seq))
        inv_ids.append(cur.fetchone()["id"])
    conn.commit()

    yield SUPPLIER_ID, inv_ids[0], inv_ids[1]

    cur.execute("DELETE FROM facturare_contracts WHERE id=%s", (contract_id,))
    conn.commit()
    release_db(conn)


def _insert_docnum(cur, invoice_id, supplier_id, document_number, line_id):
    cur.execute(
        """INSERT INTO facturare_document_numbers
           (invoice_id, supplier_id, series, line_id, position, document_number)
           VALUES (%s,%s,'fiscal',%s,0,%s)""",
        (invoice_id, supplier_id, line_id, document_number))


def test_same_number_within_one_invoice_is_allowed(two_invoices):
    """single_doc semantics: two cars of the SAME invoice share one number."""
    supplier_id, inv_a, _ = two_invoices
    conn = get_db()
    try:
        cur = get_cursor(conn)
        _insert_docnum(cur, inv_a, supplier_id, 7654321, line_id=1001)
        _insert_docnum(cur, inv_a, supplier_id, 7654321, line_id=1002)
        conn.commit()  # must NOT raise
        cur.execute(
            "SELECT COUNT(*) AS c FROM facturare_document_numbers "
            "WHERE invoice_id=%s AND document_number=7654321", (inv_a,))
        assert cur.fetchone()["c"] == 2
    finally:
        conn.rollback()
        release_db(conn)


def test_same_number_across_invoices_is_rejected(two_invoices):
    """A number used by one invoice cannot be reused by a DIFFERENT invoice."""
    supplier_id, inv_a, inv_b = two_invoices
    conn = get_db()
    try:
        cur = get_cursor(conn)
        _insert_docnum(cur, inv_a, supplier_id, 8765432, line_id=2001)
        conn.commit()
        with pytest.raises((psycopg2.errors.ExclusionViolation, psycopg2.IntegrityError)):
            _insert_docnum(cur, inv_b, supplier_id, 8765432, line_id=2002)
            conn.commit()
        conn.rollback()
    finally:
        conn.rollback()
        release_db(conn)
