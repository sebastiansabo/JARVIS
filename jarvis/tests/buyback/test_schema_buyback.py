"""Schema tests for the buyback module tables.

DB-backed (uses `require_real_db` from tests/buyback/conftest.py), obtains
its connection via `database.get_db`/`get_cursor`/`release_db` — NOT raw
psycopg2.connect — because jarvis/conftest.py mocks psycopg2 at collection
time for the rest of the suite. See tests/accounting/facturare/test_archive_repo.py
for the same pattern.
"""
from database import get_db, get_cursor, release_db
from migrations.domains.schema_buyback import create_schema_buyback

DDL_TABLES = ['buyback_records', 'buyback_offers', 'buyback_photos', 'buyback_events']


def test_buyback_tables_exist_and_idempotent(require_real_db):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        create_schema_buyback(conn, cur)  # first run
        create_schema_buyback(conn, cur)  # second run must not raise
        conn.commit()
        for t in DDL_TABLES:
            cur.execute("SELECT to_regclass(%s)", (t,))
            row = cur.fetchone()
            val = row[0] if not isinstance(row, dict) else row.get('to_regclass')
            assert val is not None, f'{t} missing'
    finally:
        release_db(conn)


def test_records_has_company_and_status_columns(require_real_db):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        create_schema_buyback(conn, cur)
        conn.commit()
        cur.execute("""SELECT column_name FROM information_schema.columns
                       WHERE table_name='buyback_records'""")
        cols = {r[0] if not isinstance(r, dict) else r['column_name'] for r in cur.fetchall()}
        assert {'company_id', 'status', 'vin', 'record_code', 'purchase_price_eur',
                'carpark_vehicle_id', 'is_trade_in'}.issubset(cols)
    finally:
        release_db(conn)
