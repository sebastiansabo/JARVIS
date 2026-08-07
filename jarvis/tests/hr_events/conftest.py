"""Real-DB harness for the granular-presence-days tests.

Mirrors the probe/restore dance in tests/dept_pulse/conftest.py: jarvis/conftest.py
installs a psycopg2 MagicMock so the mocked suite runs without a DB; the DB-backed
tests here need the real driver. We probe localhost/defaultdb once at collection
time and skip cleanly (restoring the mock state) when it is unreachable, so a
no-DB / CI run does not fail or leak the real driver into other packages.
"""
import os
import sys
from unittest.mock import MagicMock

os.environ.setdefault('DATABASE_URL', 'postgresql://localhost/defaultdb')

import pytest

_MOCK_MODULE_NAMES = ('psycopg2', 'psycopg2.pool', 'psycopg2.extras', 'psycopg2.errors')
_saved_sys_modules = {name: sys.modules.get(name) for name in _MOCK_MODULE_NAMES}
_db_preexisting = 'database' in sys.modules
_saved_db_attrs = None
if _db_preexisting:
    _db_mod = sys.modules['database']
    _saved_db_attrs = {
        'psycopg2': getattr(_db_mod, 'psycopg2', None),
        'pool': getattr(_db_mod, 'pool', None),
        'RealDictCursor': getattr(_db_mod, 'RealDictCursor', None),
        '_connection_pool': getattr(_db_mod, '_connection_pool', None),
    }


def _drop_mocks_and_bind_real_driver():
    for _name in _MOCK_MODULE_NAMES:
        if isinstance(sys.modules.get(_name), MagicMock):
            del sys.modules[_name]
    import psycopg2 as _psycopg2
    import psycopg2.pool as _psycopg2_pool
    from psycopg2.extras import RealDictCursor as _RealDictCursor
    _db_mod = sys.modules.get('database')
    if _db_mod is not None and (
        isinstance(getattr(_db_mod, 'psycopg2', None), MagicMock)
        or isinstance(getattr(_db_mod, 'pool', None), MagicMock)
    ):
        _db_mod.psycopg2 = _psycopg2
        _db_mod.pool = _psycopg2_pool
        _db_mod.RealDictCursor = _RealDictCursor
        _db_mod._connection_pool = None


def _restore_pre_probe_state():
    for _name in _MOCK_MODULE_NAMES:
        _saved = _saved_sys_modules.get(_name)
        if _saved is not None:
            sys.modules[_name] = _saved
        else:
            sys.modules.pop(_name, None)
    if _db_preexisting:
        _db_mod = sys.modules.get('database')
        if _db_mod is not None and _saved_db_attrs is not None:
            _db_mod.psycopg2 = _saved_db_attrs['psycopg2']
            _db_mod.pool = _saved_db_attrs['pool']
            _db_mod.RealDictCursor = _saved_db_attrs['RealDictCursor']
            _db_mod._connection_pool = _saved_db_attrs['_connection_pool']
    else:
        sys.modules.pop('database', None)


def _probe_real_db():
    try:
        _drop_mocks_and_bind_real_driver()
        from database import get_db, get_cursor, release_db
        conn = get_db()
        try:
            cur = get_cursor(conn)
            cur.execute('SELECT 1 AS one')
            row = cur.fetchone()
            if not row or row.get('one') != 1:
                raise RuntimeError('probe query did not return a real row (mocked cursor?)')
        finally:
            release_db(conn)
        return True
    except Exception:
        _restore_pre_probe_state()
        return False


REAL_DB_AVAILABLE = _probe_real_db()

from database import get_db, get_cursor, release_db  # noqa: E402

_MARK = 'presence_test@example.invalid'


@pytest.fixture
def hr_ctx():
    """A throwaway user + event on a real DB, with the presence-days objects
    ensured. Yields (conn, cur, ctx) where ctx has user_id/event_id and the
    event's date range. Everything cascades from the event/user on teardown.
    """
    if not REAL_DB_AVAILABLE:
        pytest.skip('Real Postgres not available — skipping presence DB test')

    from migrations.domains.schema_hr import create_event_bonus_days

    conn = get_db()
    conn.autocommit = False
    cur = get_cursor(conn)
    create_event_bonus_days(conn, cur)  # idempotent — exact production DDL

    ctx = {}
    try:
        cur.execute("INSERT INTO users (name, email) VALUES (%s, %s) RETURNING id",
                    ('Presence Test', _MARK))
        ctx['user_id'] = cur.fetchone()['id']
        # Far-future dates so month/year aggregates never collide with the real
        # bonuses already in localhost/defaultdb.
        cur.execute("""INSERT INTO hr.events (name, start_date, end_date, company)
                       VALUES ('Presence Test Event', '2099-01-30', '2099-02-03', 'TESTCO')
                       RETURNING id""")
        ctx['event_id'] = cur.fetchone()['id']
        ctx['start_date'] = '2099-01-30'
        ctx['end_date'] = '2099-02-03'
        conn.commit()
        yield conn, cur, ctx
    finally:
        cur.execute("DELETE FROM hr.events WHERE id = %s", (ctx.get('event_id'),))
        cur.execute("DELETE FROM users WHERE email = %s", (_MARK,))
        conn.commit()
        release_db(conn)


def make_bonus(cur, ctx, *, year, month, bonus_net, bonus_days,
               participation_start=None, participation_end=None):
    """Insert one event_bonus for the throwaway user/event; return its id."""
    cur.execute("""
        INSERT INTO hr.event_bonuses
            (user_id, event_id, year, month, bonus_net, bonus_days,
             participation_start, participation_end)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (ctx['user_id'], ctx['event_id'], year, month, bonus_net, bonus_days,
          participation_start, participation_end))
    return cur.fetchone()['id']
