"""JARVIS Core Database Module.

Provides the base database connection pool and utilities used by all modules.
Each section (accounting, hr, etc.) has its own database module that imports
from here for connection management.
"""
import os
import time
import threading
import logging
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

# Thread-safe lock for cache operations
# Prevents race conditions in multi-threaded Gunicorn environment
_cache_lock = threading.RLock()

# Configure module logger
logger = logging.getLogger('jarvis.core.database')

# PostgreSQL connection - DATABASE_URL is required
DATABASE_URL = os.environ.get('DATABASE_URL')

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required. Set it to your PostgreSQL connection string.")

# Connection pool configuration
_connection_pool = None

# Pool size configuration - can be tuned via environment variables
# Defaults optimized for 3 Gunicorn workers with 1-10 concurrent users
POOL_MIN_CONN = int(os.environ.get('DB_POOL_MIN_CONN', '3'))
POOL_MAX_CONN = int(os.environ.get('DB_POOL_MAX_CONN', '12'))


def _get_pool():
    """Get or create the connection pool (lazy initialization)."""
    global _connection_pool
    if _connection_pool is None:
        # Add keepalive options to prevent connections from being dropped
        # by the server after idle timeout
        _connection_pool = pool.ThreadedConnectionPool(
            minconn=POOL_MIN_CONN,
            maxconn=POOL_MAX_CONN,
            dsn=DATABASE_URL,
            keepalives=1,           # Enable keepalives
            keepalives_idle=30,     # Seconds before sending keepalive
            keepalives_interval=10, # Seconds between keepalives
            keepalives_count=5      # Failed keepalives before disconnect
        )
    return _connection_pool


def get_db():
    """Get PostgreSQL database connection from pool.

    Validates connection health before returning. If connection is stale
    (closed by server), it's discarded and a fresh one is obtained.
    Retries up to 3 times to handle multiple stale connections in pool.
    """
    max_retries = 3
    last_error = None

    for attempt in range(max_retries):
        conn = _get_pool().getconn()

        # Check if connection is still alive
        try:
            # Use a lightweight query to test connection
            with conn.cursor() as cur:
                cur.execute('SELECT 1')
            # End the implicit transaction started by health check
            conn.rollback()
            # Set autocommit mode so each query sees the latest committed data
            # without needing explicit transaction management
            conn.autocommit = True
            # Connection is good, return it
            return conn
        except (psycopg2.OperationalError, psycopg2.InterfaceError, psycopg2.DatabaseError) as e:
            last_error = e
            # Connection is dead - close it and try again
            try:
                _get_pool().putconn(conn, close=True)
            except Exception:
                pass
            # Continue to next attempt

    # All retries failed, raise the last error
    raise psycopg2.OperationalError(f"Failed to get valid connection after {max_retries} attempts: {last_error}")


def release_db(conn):
    """Return connection to pool.

    Resets autocommit to False before returning to pool.
    """
    if conn and _connection_pool:
        try:
            conn.autocommit = False  # Reset for next user
        except Exception:
            pass  # Ignore errors on closed connections
        _connection_pool.putconn(conn)


@contextmanager
def transaction():
    """Context manager for atomic database transactions.

    Usage:
        with transaction() as conn:
            cursor = get_cursor(conn)
            cursor.execute('INSERT INTO ...')
            cursor.execute('UPDATE ...')
        # Auto-commits on success, auto-rollbacks on exception

    For multi-step operations (invoice + allocations), wrap all DB
    operations in a single transaction block to ensure atomicity.
    """
    conn = get_db()
    try:
        # Disable autocommit for explicit transaction control
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
    """Refresh all connections in the pool to ensure they're healthy.

    Call this after heavy operations (file uploads, bulk processing) to
    prevent stale connections. Gets and releases multiple connections
    to cycle through the pool and validate each one.
    """
    global _connection_pool
    if _connection_pool is None:
        return

    # Get and release connections to validate them
    # This forces the pool to check each connection's health
    connections = []
    try:
        for _ in range(POOL_MIN_CONN):
            try:
                conn = get_db()  # get_db validates the connection
                connections.append(conn)
            except Exception:
                pass
    finally:
        for conn in connections:
            try:
                release_db(conn)
            except Exception:
                pass


def ping_db():
    """Ping the database to keep connections alive.

    Returns True if successful, False otherwise.
    Use this for health checks or keep-alive operations.
    """
    try:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT 1')
            return True
        finally:
            release_db(conn)
    except Exception:
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


def dict_from_row(row):
    """Convert database row to dictionary with proper serialization.

    Handles:
    - RealDictRow conversion to regular dict
    - Date objects to ISO format strings (YYYY-MM-DD)
    - Datetime objects to ISO format strings
    - None values preserved
    """
    if row is None:
        return None
    result = dict(row)
    # Convert date objects to ISO strings for JSON serialization
    for key, value in result.items():
        if hasattr(value, 'isoformat'):
            result[key] = value.isoformat()
    return result


# ============== CACHE UTILITIES ==============

def _is_cache_valid(cache_entry: dict) -> bool:
    """Check if a cache entry is still valid."""
    if cache_entry.get('data') is None:
        return False
    return (time.time() - cache_entry.get('timestamp', 0)) < cache_entry.get('ttl', 300)


def _get_cache_data(cache_dict: dict, key: str = 'data'):
    """Thread-safe getter for cache data."""
    with _cache_lock:
        return cache_dict.get(key)


def _set_cache_data(cache_dict: dict, data, key: str = 'data'):
    """Thread-safe setter for cache data with timestamp update."""
    with _cache_lock:
        cache_dict[key] = data
        cache_dict['timestamp'] = time.time()


def create_cache(ttl: int = 300) -> dict:
    """Create a new cache dictionary with specified TTL."""
    return {
        'data': None,
        'timestamp': 0,
        'ttl': ttl
    }


def get_cache_lock():
    """Get the shared cache lock for custom cache operations."""
    return _cache_lock
