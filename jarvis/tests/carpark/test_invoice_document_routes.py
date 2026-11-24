"""Pure unit test for the invoice-document-type guard in
carpark/routes/documents.py (Task 5).

Only `is_invoice_document_type` is exercised here — no Flask app, no DB.
The parse-invoice/transfer-to-cost route happy-paths (mock-based, mirroring
test_documents_routes.py) and the real-DB transfer flow (test_invoice_cost_
transfer_db.py) are covered elsewhere; end-to-end behavior against the live
app is verified in Task 8.

Importing carpark.routes.documents pulls in the carpark blueprint and (via
carpark.repositories.*/BaseRepository -> database.py) code that reads
DATABASE_URL at import time but does not connect. The root conftest.py
already mocks psycopg2 and sets a dummy DATABASE_URL before any test module
is imported, so this import is safe without a real DB; the setdefault below
just mirrors test_documents_routes.py's belt-and-suspenders guard in case
this file is ever run outside the full suite.
"""
import os

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

from carpark.routes.documents import is_invoice_document_type


def test_is_invoice_document_type():
    assert is_invoice_document_type('factura_achizitie')
    assert is_invoice_document_type('factura_transfer')
    assert not is_invoice_document_type('talon')
    assert not is_invoice_document_type('asigurare')
