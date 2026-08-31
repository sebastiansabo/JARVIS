import pytest
from database import get_db, get_cursor, release_db

# Reuse the org conftest's REAL_DB probe convention.
try:
    _c = get_db(); _cur = get_cursor(_c); _cur.execute('SELECT 1'); release_db(_c)
    REAL_DB = True
except Exception:
    REAL_DB = False


@pytest.mark.skipif(not REAL_DB, reason='no real DB available (CI)')
def test_users_has_is_ghost_column():
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("""SELECT column_name, column_default
                       FROM information_schema.columns
                       WHERE table_name='users' AND column_name='is_ghost'""")
        row = cur.fetchone()
        assert row is not None, 'is_ghost column missing'
        assert 'false' in (row['column_default'] or '').lower()
    finally:
        release_db(conn)


@pytest.mark.skipif(not REAL_DB, reason='no real DB available (CI)')
def test_ghost_admin_setting_seeded():
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("SELECT setting_value FROM notification_settings WHERE setting_key='ghost_visible_admin_ids'")
        assert cur.fetchone() is not None, 'ghost_visible_admin_ids not seeded'
    finally:
        release_db(conn)
