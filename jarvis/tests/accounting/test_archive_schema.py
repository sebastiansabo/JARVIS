import os, sys

JARVIS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if JARVIS_ROOT not in sys.path:
    sys.path.insert(0, JARVIS_ROOT)
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import psycopg2
from database import get_db, get_cursor, release_db

EXPECTED = {
    ('facturare_anexas', 'archive_after'),
    ('facturare_anexas', 'archived_at'),
    ('facturare_anexas', 'archived'),
    ('facturare_anexas', 'status'),
    ('facturare_invoices', 'archived'),
    ('facturare_contracts', 'archived'),
    ('facturare_contracts', 'archive_after'),
    ('facturare_contracts', 'archived_at'),
}

def test_archive_columns_exist():
    conn = get_db(); cur = get_cursor(conn)
    try:
        cur.execute(
            """SELECT table_name, column_name FROM information_schema.columns
               WHERE table_name IN ('facturare_anexas','facturare_invoices','facturare_contracts')""")
        present = {(r['table_name'], r['column_name']) for r in cur.fetchall()}
    finally:
        release_db(conn)
    missing = EXPECTED - present
    assert not missing, f"Missing columns: {missing}"
