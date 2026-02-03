"""JARVIS Core Database Module.

Re-exports database utilities from the main database module to ensure
a single unified connection pool across the entire application.

This prevents connection pool exhaustion by consolidating all database
connections into one pool managed by jarvis/database.py.

Usage:
    from core.database import get_db, get_cursor, release_db
    # or
    from core.database import get_db_connection, transaction
"""

# Re-export everything from the main database module
# This ensures a single connection pool for the entire application
import sys
import os

# Add parent directory to path to import from main database module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import (
    # Connection management
    get_db,
    release_db,
    get_db_connection,
    transaction,
    refresh_connection_pool,
    ping_db,

    # Cursor and utilities
    get_cursor,
    get_placeholder,
    dict_from_row,

    # Pool configuration (read-only)
    DATABASE_URL,
    POOL_MIN_CONN,
    POOL_MAX_CONN,

    # Cache utilities
    create_cache,
    get_cache_lock,
    _is_cache_valid,
    _get_cache_data,
    _set_cache_data,
)

# Also export psycopg2 for type hints and error handling
import psycopg2
from psycopg2.extras import RealDictCursor

__all__ = [
    'get_db',
    'release_db',
    'get_db_connection',
    'transaction',
    'refresh_connection_pool',
    'ping_db',
    'get_cursor',
    'get_placeholder',
    'dict_from_row',
    'DATABASE_URL',
    'POOL_MIN_CONN',
    'POOL_MAX_CONN',
    'create_cache',
    'get_cache_lock',
    '_is_cache_valid',
    '_get_cache_data',
    '_set_cache_data',
    'psycopg2',
    'RealDictCursor',
]
