"""Schema check: the mkt_td_* public test-drive booking tables exist on localhost Postgres,
including the partial-unique slot-race guard index.

Runs against the real localhost DB (DATABASE_URL, default postgresql://localhost/defaultdb),
via the require_real_db fixture in conftest.py (skips cleanly when no real DB is available).
"""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import psycopg2  # noqa: F401  (ensures the real driver is importable in this process)
import pytest
from database import get_db, get_cursor, release_db

TABLES = [
    'mkt_td_booking_pages', 'mkt_td_booking_cars',
    'mkt_td_booking_windows', 'mkt_td_slots', 'mkt_td_bookings',
]


@pytest.mark.parametrize('table', TABLES)
def test_td_tables_exist(require_real_db, table):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name=%s", (table,))
        row = cur.fetchone()
    finally:
        release_db(conn)
    assert row is not None, f"missing table {table}"


def test_partial_unique_index_exists(require_real_db):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute(
            "SELECT indexdef FROM pg_indexes "
            "WHERE indexname='uq_mkt_td_active_booking_per_slot'")
        row = cur.fetchone()
    finally:
        release_db(conn)
    assert row is not None
    assert "pending_confirm" in row['indexdef'] and "confirmed" in row['indexdef']
