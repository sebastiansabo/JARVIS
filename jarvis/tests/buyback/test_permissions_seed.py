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


def test_can_access_buyback_true_for_every_module_access_role(require_real_db):
    """The can_access_buyback boolean must be backfilled for EVERY role that
    holds buyback.module.access — not just Admin. Manager and Sales are seeded
    with module.access unconditionally in this DB (both exist); Acquisition
    and Service also receive module.access now but may be absent in the shared
    DB, so each assertion is guarded on the role actually existing (mirroring
    how the seed no-ops for absent role names). Regression guard for the
    Admin-only hardcoded UPDATE bug.
    """
    conn = get_db()
    try:
        cur = get_cursor(conn)
        _seed_buyback_permissions_v2(cur, conn)
        conn.commit()

        def _flag(role_name):
            cur.execute("SELECT can_access_buyback FROM roles WHERE name = %s", (role_name,))
            row = cur.fetchone()
            if row is None:
                return None  # role absent in this DB -> assertion skipped
            return row['can_access_buyback'] if isinstance(row, dict) else row[0]

        # Admin/Manager (all grants) and Sales (explicit module.access) always
        # exist in the seeded DB and MUST resolve TRUE.
        for role_name in ('Admin', 'Manager', 'Sales'):
            assert _flag(role_name) is True, f'{role_name} should have can_access_buyback=TRUE'

        # Acquisition/Service now also get module.access — TRUE when present,
        # harmlessly skipped when the role name is absent from the shared DB.
        for role_name in ('Acquisition', 'Service'):
            flag = _flag(role_name)
            if flag is not None:
                assert flag is True, f'{role_name} should have can_access_buyback=TRUE when present'

        # Viewer is explicit-deny on module.access -> must stay FALSE.
        viewer = _flag('Viewer')
        if viewer is not None:
            assert viewer is False, 'Viewer should have can_access_buyback=FALSE'
    finally:
        release_db(conn)


def test_acquisition_and_service_get_module_access(require_real_db):
    """Acquisition and Service must be granted buyback.module.access at scope
    'all' (controller ruling) so they can reach the module UI. Guarded on the
    role existing so it's a no-op when the role name is absent.
    """
    conn = get_db()
    try:
        cur = get_cursor(conn)
        _seed_buyback_permissions_v2(cur, conn)
        conn.commit()

        for role_name in ('Acquisition', 'Service'):
            cur.execute("SELECT 1 FROM roles WHERE name = %s", (role_name,))
            if cur.fetchone() is None:
                continue  # role absent in this DB -> guarded no-op
            cur.execute("""SELECT rp.scope FROM role_permissions_v2 rp
                           JOIN permissions_v2 p ON p.id = rp.permission_id
                           JOIN roles r ON r.id = rp.role_id
                           WHERE p.module_key = 'buyback' AND r.name = %s
                             AND p.entity_key = 'module' AND p.action_key = 'access'""",
                        (role_name,))
            row = cur.fetchone()
            scope = (row['scope'] if isinstance(row, dict) else row[0]) if row else None
            assert scope == 'all', f'{role_name} should hold buyback.module.access scope=all'
    finally:
        release_db(conn)
