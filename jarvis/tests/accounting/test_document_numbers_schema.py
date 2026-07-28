import os, sys
JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if JARVIS_ROOT not in sys.path:
    sys.path.insert(0, JARVIS_ROOT)
os.environ.setdefault("DATABASE_URL", "postgresql://localhost/defaultdb")

from database import get_db, get_cursor, release_db


def test_document_numbers_table_and_unique_index_exist():
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'facturare_document_numbers' ORDER BY column_name
        """)
        cols = {r["column_name"] for r in cur.fetchall()}
        assert {"id","invoice_id","supplier_id","series","line_id","position","document_number","created_at"} <= cols
        cur.execute("""
            SELECT indexdef FROM pg_indexes WHERE tablename = 'facturare_document_numbers'
        """)
        defs = " ".join(r["indexdef"] for r in cur.fetchall())
        assert "UNIQUE" in defs and "supplier_id" in defs and "document_number" in defs
    finally:
        release_db(conn)
