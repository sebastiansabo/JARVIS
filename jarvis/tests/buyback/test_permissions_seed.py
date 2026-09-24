"""Permission seed tests for the Buyback module (Task 3).

DB-backed (uses `require_real_db` from tests/buyback/conftest.py), obtains
its connection via `database.get_db`/`get_cursor`/`release_db` — NOT raw
psycopg2.connect — because jarvis/conftest.py mocks psycopg2 at collection
time for the rest of the suite. See tests/buyback/test_schema_buyback.py for
the same pattern.

Commits after `_seed_buyback_permissions_v2` runs so the rows persist on the
shared localhost/defaultdb: later buyback route tasks depend on these grants
(and the Sales/Acquisition/Service role grants) already being present.
"""
from database import get_db, get_cursor, release_db
from migrations.domains.schema_roles import _seed_buyback_permissions_v2

EXPECTED_ACTIONS = {'access', 'view', 'create', 'edit', 'delete', 'finalize', 'manage'}


def test_buyback_perms_seeded(require_real_db):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        _seed_buyback_permissions_v2(cur, conn)
        conn.commit()

        cur.execute("SELECT entity_key, action_key FROM permissions_v2 WHERE module_key='buyback'")
        rows = cur.fetchall()
        pairs = {(r['entity_key'], r['action_key']) if isinstance(r, dict) else (r[0], r[1]) for r in rows}
        actions = {a for _, a in pairs}

        assert len(pairs) == 8, f'expected 8 buyback permissions, got {pairs}'
        assert 'access' in actions
        assert {'view', 'create', 'edit', 'delete', 'finalize'}.issubset(actions)
        assert ('offer', 'manage') in pairs
        assert ('inspection', 'manage') in pairs
    finally:
        release_db(conn)


def test_admin_gets_all_buyback_finalize(require_real_db):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        _seed_buyback_permissions_v2(cur, conn)
        conn.commit()

        cur.execute("""SELECT rp.scope FROM role_permissions_v2 rp
                       JOIN permissions_v2 p ON p.id = rp.permission_id
                       JOIN roles r ON r.id = rp.role_id
                       WHERE p.module_key = 'buyback' AND r.name = 'Admin'
                         AND p.entity_key = 'record' AND p.action_key = 'finalize'""")
        row = cur.fetchone()
        scope = (row['scope'] if isinstance(row, dict) else row[0]) if row else None
        assert scope == 'all'
    finally:
        release_db(conn)


def test_seed_is_idempotent(require_real_db):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        _seed_buyback_permissions_v2(cur, conn)  # first run
        _seed_buyback_permissions_v2(cur, conn)  # second run must not raise
        conn.commit()

        cur.execute("SELECT COUNT(*) AS cnt FROM permissions_v2 WHERE module_key='buyback'")
        row = cur.fetchone()
        cnt = row['cnt'] if isinstance(row, dict) else row[0]
        assert cnt == 8
    finally:
        release_db(conn)


def test_can_access_buyback_column_exists(require_real_db):
    conn = get_db()
    try:
        cur = get_cursor(conn)
        _seed_buyback_permissions_v2(cur, conn)
        conn.commit()

        cur.execute("""SELECT column_name FROM information_schema.columns
                       WHERE table_name = 'roles' AND column_name = 'can_access_buyback'""")
        assert cur.fetchone() is not None

        cur.execute("SELECT can_access_buyback FROM roles WHERE name = 'Admin'")
        row = cur.fetchone()
        val = row['can_access_buyback'] if isinstance(row, dict) else row[0]
        assert val is True
    finally:
        release_db(conn)
