"""Schema check: the Comenzi auto-archive columns exist on localhost Postgres.

Runs against the real localhost DB (DATABASE_URL, default postgresql://localhost/defaultdb).

Note: jarvis/conftest.py replaces psycopg2 with a MagicMock at collection time so
pure-logic tests can import app code without a database. That mock makes the usual
``from database import get_db`` path return mock rows, so this real-DB integration
test loads the genuine driver transiently (restoring the mock afterwards, to leave
sibling tests untouched) and connects directly.
"""
import os
import sys
import importlib

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

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


def _real_psycopg2():
    """Return the genuine psycopg2 module even if conftest mocked it.

    Pops any psycopg2* entries from sys.modules, imports the real package fresh,
    then restores the previous entries so the mock other tests rely on is intact.
    """
    saved = {k: sys.modules.pop(k) for k in list(sys.modules)
             if k == 'psycopg2' or k.startswith('psycopg2.')}
    try:
        return importlib.import_module('psycopg2')
    finally:
        for k in [k for k in sys.modules if k == 'psycopg2' or k.startswith('psycopg2.')]:
            del sys.modules[k]
        sys.modules.update(saved)


def test_archive_columns_exist():
    psycopg2 = _real_psycopg2()
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT table_name, column_name FROM information_schema.columns
               WHERE table_name IN ('facturare_anexas','facturare_invoices','facturare_contracts')""")
        present = {(r[0], r[1]) for r in cur.fetchall()}
    finally:
        conn.close()
    missing = EXPECTED - present
    assert not missing, f"Missing columns: {missing}"
