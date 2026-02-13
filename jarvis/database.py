import os
import logging
import threading
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor


# Configure module logger
logger = logging.getLogger('jarvis.database')

# PostgreSQL connection - DATABASE_URL is required
DATABASE_URL = os.environ.get('DATABASE_URL')

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required. Set it to your PostgreSQL connection string.")

# Connection pool configuration
# DigitalOcean managed DB limit: 47 connections (Basic 1vCPU/2GB)
# 3 Gunicorn workers × 8 max = 24 connections (~50% of limit, rest for admin/health/scheduler)
_connection_pool = None
_pool_lock = threading.Lock()

POOL_MIN_CONN = int(os.environ.get('DB_POOL_MIN_CONN', '2'))
POOL_MAX_CONN = int(os.environ.get('DB_POOL_MAX_CONN', '8'))
POOL_GETCONN_TIMEOUT = int(os.environ.get('DB_POOL_TIMEOUT', '10'))


def _get_pool():
    """Get or create the connection pool (lazy initialization, thread-safe)."""
    global _connection_pool
    if _connection_pool is None:
        with _pool_lock:
            if _connection_pool is None:
                _connection_pool = pool.ThreadedConnectionPool(
                    minconn=POOL_MIN_CONN,
                    maxconn=POOL_MAX_CONN,
                    dsn=DATABASE_URL,
                    keepalives=1,
                    keepalives_idle=30,
                    keepalives_interval=10,
                    keepalives_count=5,
                    connect_timeout=5,
                )
                logger.info(f'Connection pool created: min={POOL_MIN_CONN}, max={POOL_MAX_CONN}')
    return _connection_pool


def _getconn_with_timeout(timeout=None):
    """Get connection from pool with timeout to prevent indefinite blocking.

    ThreadedConnectionPool.getconn() blocks forever when pool is exhausted.
    This wrapper uses a thread to enforce a timeout, preventing request hangs.
    """
    if timeout is None:
        timeout = POOL_GETCONN_TIMEOUT

    result = [None]
    error = [None]

    def _get():
        try:
            result[0] = _get_pool().getconn()
        except Exception as e:
            error[0] = e

    t = threading.Thread(target=_get, daemon=True)
    t.start()
    t.join(timeout=timeout)

    if t.is_alive():
        raise psycopg2.OperationalError(
            f"Connection pool exhausted — timed out after {timeout}s waiting for available connection"
        )
    if error[0]:
        raise error[0]
    return result[0]


def get_db():
    """Get PostgreSQL database connection from pool.

    Validates connection health before returning. If connection is stale
    (closed by server), it's discarded and a fresh one is obtained.
    Retries up to 3 times to handle multiple stale connections in pool.
    """
    max_retries = 3
    last_error = None

    for attempt in range(max_retries):
        conn = _getconn_with_timeout()

        # Check if connection is still alive
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT 1')
            conn.rollback()
            conn.autocommit = True
            return conn
        except (psycopg2.OperationalError, psycopg2.InterfaceError, psycopg2.DatabaseError) as e:
            last_error = e
            logger.warning(f'Stale connection discarded (attempt {attempt + 1}/{max_retries}): {e}')
            try:
                _get_pool().putconn(conn, close=True)
            except Exception:
                pass

    raise psycopg2.OperationalError(f"Failed to get valid connection after {max_retries} attempts: {last_error}")


def release_db(conn):
    """Return connection to pool.

    Handles stale/broken connections gracefully — closes them instead of
    returning broken connections back to the pool.
    """
    if conn and _connection_pool:
        try:
            # Check if connection is still usable before returning to pool
            if conn.closed:
                try:
                    _connection_pool.putconn(conn, close=True)
                except Exception:
                    pass
                return
            conn.autocommit = False
            _connection_pool.putconn(conn)
        except Exception:
            # Connection is in bad state — close it to prevent pool corruption
            try:
                _connection_pool.putconn(conn, close=True)
            except Exception:
                pass


@contextmanager
def transaction():
    """Context manager for atomic database transactions.

    Usage:
        with transaction() as conn:
            cursor = get_cursor(conn)
            cursor.execute('INSERT INTO ...')
            cursor.execute('UPDATE ...')
        # Auto-commits on success, auto-rollbacks on exception
    """
    conn = get_db()
    try:
        conn.autocommit = False
        yield conn
        conn.commit()
        logger.debug('Transaction committed successfully')
    except Exception as e:
        conn.rollback()
        logger.warning(f'Transaction rolled back: {e}')
        raise
    finally:
        release_db(conn)


def refresh_connection_pool():
    """Refresh all connections in the pool to ensure they're healthy."""
    global _connection_pool
    if _connection_pool is None:
        return

    connections = []
    try:
        for _ in range(POOL_MIN_CONN):
            try:
                conn = get_db()
                connections.append(conn)
            except Exception:
                pass
    finally:
        for conn in connections:
            try:
                release_db(conn)
            except Exception:
                pass


_ping_cache = {'ok': False, 'ts': 0}

def ping_db():
    """Ping the database to keep connections alive.

    Caches result for 5 seconds to avoid pool churn from frequent health checks
    (3 workers × 10s interval = checks every ~3s).

    Returns True if successful, False otherwise.
    """
    import time
    now = time.time()
    if _ping_cache['ok'] and (now - _ping_cache['ts']) < 5:
        return True

    try:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT 1')
            _ping_cache['ok'] = True
            _ping_cache['ts'] = now
            return True
        finally:
            release_db(conn)
    except Exception:
        _ping_cache['ok'] = False
        return False


@contextmanager
def get_db_connection():
    """Context manager for database connections - auto-releases to pool."""
    conn = get_db()
    try:
        yield conn
    finally:
        release_db(conn)


def get_cursor(conn):
    """Get cursor with dict row factory."""
    return conn.cursor(cursor_factory=RealDictCursor)


def get_placeholder():
    """Get PostgreSQL placeholder."""
    return '%s'



def init_db():
    """Initialize database tables, indexes, and seed data.

    Delegates to migrations.init_schema.create_schema() which contains
    all CREATE TABLE, ALTER TABLE, CREATE INDEX, and INSERT statements.

    Skips if schema already exists (checks for 'invoices' table) to avoid
    running ~100 SQL statements on every worker startup.
    """
    conn = get_db()
    cursor = get_cursor(conn)
    try:
        # Quick check: if core table exists, schema is already initialized
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'invoices'
            )
        """)
        if cursor.fetchone()['exists']:
            logger.info('Database schema already initialized — skipping init_db()')
            return

        from migrations.init_schema import create_schema
        create_schema(conn, cursor)
        conn.commit()
        logger.info('Database schema initialized successfully')
    finally:
        release_db(conn)


def dict_from_row(row):
    """Convert a database row to a dictionary with proper date serialization."""
    if row is None:
        return None
    result = dict(row)
    for key, value in result.items():
        if hasattr(value, 'isoformat'):
            if hasattr(value, 'hour'):
                result[key] = value.isoformat()
            else:
                result[key] = value.isoformat()
    return result


# Initialize database on import
init_db()
