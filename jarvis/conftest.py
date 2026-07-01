"""Top-level pytest configuration for jarvis/ test suite.

Loaded BEFORE any test modules or conftest.py files in sub-packages,
so patches here take effect before any app code is imported.
"""
import sys
import os
from unittest.mock import MagicMock

# Set dummy DATABASE_URL before any imports trigger database.py
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

# Patch psycopg2 before database.py imports it and tries to create a pool
if 'psycopg2' not in sys.modules:
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_pool.getconn.return_value = mock_conn

    sys.modules['psycopg2'] = MagicMock()
    sys.modules['psycopg2.pool'] = MagicMock()
    sys.modules['psycopg2.pool'].ThreadedConnectionPool = MagicMock(return_value=mock_pool)
    sys.modules['psycopg2.extras'] = MagicMock()
    sys.modules['psycopg2.errors'] = MagicMock()
    sys.modules['psycopg2.errors'].UniqueViolation = type('UniqueViolation', (Exception,), {})
