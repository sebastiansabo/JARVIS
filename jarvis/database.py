import os
import json
import time
import threading
import logging
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash

# Thread-safe lock for cache operations
# Prevents race conditions in multi-threaded Gunicorn environment
_cache_lock = threading.RLock()


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


# Configure module logger
logger = logging.getLogger('jarvis.database')

# PostgreSQL connection - DATABASE_URL is required
DATABASE_URL = os.environ.get('DATABASE_URL')

# In-memory cache for invoice templates (rarely change)
_templates_cache = {
    'data': None,
    'timestamp': 0,
    'ttl': 300  # 5 minutes TTL
}

# In-memory cache for companies with VAT
_companies_vat_cache = {
    'data': None,
    'timestamp': 0,
    'ttl': 300
}

# In-memory cache for responsables
_responsables_cache = {
    'data': None,
    'timestamp': 0,
    'ttl': 300
}

# In-memory cache for invoice list (shorter TTL since data changes more frequently)
_invoices_cache = {
    'data': None,
    'timestamp': 0,
    'ttl': 60,  # 1 minute TTL
    'key': None  # Cache key based on query params
}

# In-memory cache for summary queries (By Company, By Department, By Brand tabs)
# Uses dict to store multiple cached results with different filter combinations
_summary_cache = {
    'company': {},     # key -> {'data': [...], 'timestamp': ...}
    'department': {},
    'brand': {},
    'supplier': {},
    'ttl': 60  # 1 minute TTL
}

# Maximum entries per summary cache type to prevent unbounded growth
MAX_SUMMARY_CACHE_ENTRIES = 50


def _is_cache_valid(cache_entry: dict) -> bool:
    """Check if a cache entry is still valid."""
    if cache_entry.get('data') is None:
        return False
    return (time.time() - cache_entry.get('timestamp', 0)) < cache_entry.get('ttl', 300)


# Thread-safe cache access helpers
def _get_cache_data(cache_dict: dict, key: str = 'data'):
    """Thread-safe getter for cache data."""
    with _cache_lock:
        return cache_dict.get(key)


def _set_cache_data(cache_dict: dict, data, key: str = 'data'):
    """Thread-safe setter for cache data with timestamp update."""
    with _cache_lock:
        cache_dict[key] = data
        cache_dict['timestamp'] = time.time()


def _get_summary_cache(cache_type: str, cache_key: str):
    """Thread-safe getter for summary cache entries."""
    with _cache_lock:
        cache = _summary_cache.get(cache_type, {})
        entry = cache.get(cache_key)
        if entry and (time.time() - entry.get('timestamp', 0)) < _summary_cache.get('ttl', 60):
            return entry.get('data')
        return None


def _set_summary_cache(cache_type: str, cache_key: str, data):
    """Thread-safe setter for summary cache entries."""
    with _cache_lock:
        _summary_cache[cache_type][cache_key] = {'data': data, 'timestamp': time.time()}
        _enforce_summary_cache_limit(cache_type)


def clear_templates_cache():
    """Clear the templates cache. Call this after template updates."""
    global _templates_cache
    with _cache_lock:
        _templates_cache = {'data': None, 'timestamp': 0, 'ttl': 300}
    logger.debug('Templates cache cleared')


def clear_companies_vat_cache():
    """Clear the companies VAT cache. Call this after company updates."""
    global _companies_vat_cache
    with _cache_lock:
        _companies_vat_cache = {'data': None, 'timestamp': 0, 'ttl': 300}
    logger.debug('Companies VAT cache cleared')


def clear_responsables_cache():
    """Clear the responsables cache. Call this after responsable updates."""
    global _responsables_cache
    with _cache_lock:
        _responsables_cache = {'data': None, 'timestamp': 0, 'ttl': 300}
    logger.debug('Responsables cache cleared')


def clear_invoices_cache():
    """Clear the invoices and summary caches. Call this after invoice CRUD operations."""
    global _invoices_cache, _summary_cache
    with _cache_lock:
        _invoices_cache = {'data': None, 'timestamp': 0, 'ttl': 60, 'key': None}
        # Also clear summary cache since summaries depend on invoice/allocation data
        _summary_cache = {'company': {}, 'department': {}, 'brand': {}, 'supplier': {}, 'ttl': 60}
    logger.debug('Invoices and summary caches cleared')


def clear_summary_cache():
    """Clear the summary cache only. Call this for summary-specific invalidation."""
    global _summary_cache
    with _cache_lock:
        _summary_cache = {'company': {}, 'department': {}, 'brand': {}, 'supplier': {}, 'ttl': 60}
    logger.debug('Summary cache cleared')


def _enforce_summary_cache_limit(cache_type: str):
    """Remove oldest entries if cache exceeds MAX_SUMMARY_CACHE_ENTRIES.

    Note: Caller must hold _cache_lock.
    """
    global _summary_cache
    cache = _summary_cache.get(cache_type, {})
    if len(cache) > MAX_SUMMARY_CACHE_ENTRIES:
        # Sort by timestamp and remove oldest entries
        sorted_keys = sorted(cache.keys(), key=lambda k: cache[k].get('timestamp', 0))
        entries_to_remove = len(cache) - MAX_SUMMARY_CACHE_ENTRIES
        for key in sorted_keys[:entries_to_remove]:
            del cache[key]
        logger.debug(f'Evicted {entries_to_remove} entries from {cache_type} cache')


def cleanup_expired_caches():
    """Remove expired entries from summary caches. Call periodically to prevent memory growth."""
    global _summary_cache
    with _cache_lock:
        now = time.time()
        ttl = _summary_cache.get('ttl', 60)
        total_removed = 0

        for cache_type in ['company', 'department', 'brand']:
            cache = _summary_cache.get(cache_type, {})
            expired_keys = [k for k, v in cache.items() if (now - v.get('timestamp', 0)) > ttl]
            for key in expired_keys:
                del cache[key]
            total_removed += len(expired_keys)

        if total_removed > 0:
            logger.debug(f'Cleaned up {total_removed} expired cache entries')


if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required. Set it to your PostgreSQL connection string.")

# Connection pool configuration
# minconn: minimum connections kept open
# maxconn: maximum connections allowed
# Note: DigitalOcean managed DB has ~25 max connections total
# With multiple workers, keep pool small: 2 workers × 3 min = 6 connections
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


def init_db():
    """Initialize database tables."""
    conn = get_db()
    cursor = get_cursor(conn)

    # PostgreSQL table definitions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invoices (
            id SERIAL PRIMARY KEY,
            supplier TEXT NOT NULL,
            invoice_template TEXT,
            invoice_number TEXT NOT NULL UNIQUE,
            invoice_date DATE NOT NULL,
            invoice_value REAL NOT NULL,
            currency TEXT DEFAULT 'RON',
            value_ron REAL,
            value_eur REAL,
            exchange_rate REAL,
            drive_link TEXT,
            comment TEXT,
            status TEXT DEFAULT 'new',
            deleted_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Add status column if it doesn't exist (migration)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'invoices' AND column_name = 'status') THEN
                ALTER TABLE invoices ADD COLUMN status TEXT DEFAULT 'new';
            END IF;
        END $$;
    ''')

    # Add payment_status column if it doesn't exist (migration)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'invoices' AND column_name = 'payment_status') THEN
                ALTER TABLE invoices ADD COLUMN payment_status TEXT DEFAULT 'not_paid';
            END IF;
        END $$;
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS allocations (
            id SERIAL PRIMARY KEY,
            invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
            company TEXT NOT NULL,
            brand TEXT,
            department TEXT NOT NULL,
            subdepartment TEXT,
            allocation_percent REAL NOT NULL,
            allocation_value REAL NOT NULL,
            responsible TEXT,
            reinvoice_to TEXT,
            reinvoice_brand TEXT,
            reinvoice_department TEXT,
            reinvoice_subdepartment TEXT,
            locked BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invoice_templates (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            template_type TEXT DEFAULT 'fixed',
            supplier TEXT,
            supplier_vat TEXT,
            customer_vat TEXT,
            currency TEXT DEFAULT 'RON',
            description TEXT,
            invoice_number_regex TEXT,
            invoice_date_regex TEXT,
            invoice_value_regex TEXT,
            date_format TEXT DEFAULT '%Y-%m-%d',
            supplier_regex TEXT,
            supplier_vat_regex TEXT,
            customer_vat_regex TEXT,
            currency_regex TEXT,
            sample_invoice_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS department_structure (
            id SERIAL PRIMARY KEY,
            company TEXT NOT NULL,
            brand TEXT,
            department TEXT NOT NULL,
            subdepartment TEXT,
            manager TEXT,
            marketing TEXT,
            responsable_id INTEGER REFERENCES responsables(id) ON DELETE SET NULL,
            manager_ids INTEGER[],
            marketing_ids INTEGER[],
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Add manager_ids, marketing_ids, and cc_email columns if they don't exist
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'department_structure' AND column_name = 'manager_ids') THEN
                ALTER TABLE department_structure ADD COLUMN manager_ids INTEGER[];
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'department_structure' AND column_name = 'marketing_ids') THEN
                ALTER TABLE department_structure ADD COLUMN marketing_ids INTEGER[];
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'department_structure' AND column_name = 'cc_email') THEN
                ALTER TABLE department_structure ADD COLUMN cc_email TEXT;
            END IF;
        END $$;
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS companies (
            id SERIAL PRIMARY KEY,
            company TEXT NOT NULL UNIQUE,
            brands TEXT,
            vat TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS connectors (
            id SERIAL PRIMARY KEY,
            connector_type TEXT NOT NULL,
            name TEXT NOT NULL,
            status TEXT DEFAULT 'disconnected',
            config JSONB DEFAULT '{}',
            credentials JSONB DEFAULT '{}',
            last_sync TIMESTAMP,
            last_error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS connector_sync_log (
            id SERIAL PRIMARY KEY,
            connector_id INTEGER NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
            sync_type TEXT NOT NULL,
            status TEXT NOT NULL,
            invoices_found INTEGER DEFAULT 0,
            invoices_imported INTEGER DEFAULT 0,
            error_message TEXT,
            details JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ============== BANK STATEMENT TABLES ==============

    # Bank statements - tracks uploaded statement files
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bank_statements (
            id SERIAL PRIMARY KEY,
            filename TEXT NOT NULL,
            file_hash TEXT,
            company_name TEXT,
            company_cui TEXT,
            account_number TEXT,
            period_from DATE,
            period_to DATE,
            total_transactions INTEGER DEFAULT 0,
            new_transactions INTEGER DEFAULT 0,
            duplicate_transactions INTEGER DEFAULT 0,
            uploaded_by INTEGER REFERENCES users(id),
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Index for duplicate detection by file hash
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_statements_hash ON bank_statements(file_hash)')

    # Vendor mappings for bank statement transaction matching
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vendor_mappings (
            id SERIAL PRIMARY KEY,
            pattern TEXT NOT NULL,
            supplier_name TEXT NOT NULL,
            supplier_vat TEXT,
            template_id INTEGER REFERENCES invoice_templates(id) ON DELETE SET NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Bank statement transactions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bank_statement_transactions (
            id SERIAL PRIMARY KEY,
            statement_id INTEGER REFERENCES bank_statements(id) ON DELETE SET NULL,
            statement_file TEXT,
            company_name TEXT,
            company_cui TEXT,
            account_number TEXT,
            transaction_date DATE,
            value_date DATE,
            description TEXT,
            vendor_name TEXT,
            matched_supplier TEXT,
            amount REAL,
            currency TEXT DEFAULT 'RON',
            original_amount REAL,
            original_currency TEXT,
            exchange_rate REAL,
            auth_code TEXT,
            card_number TEXT,
            transaction_type TEXT,
            invoice_id INTEGER REFERENCES invoices(id) ON DELETE SET NULL,
            status TEXT DEFAULT 'pending',
            merged_into_id INTEGER REFERENCES bank_statement_transactions(id) ON DELETE SET NULL,
            is_merged_result BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Add statement_id column if it doesn't exist (for existing databases)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'bank_statement_transactions' AND column_name = 'statement_id'
            ) THEN
                ALTER TABLE bank_statement_transactions
                ADD COLUMN statement_id INTEGER REFERENCES bank_statements(id) ON DELETE SET NULL;
            END IF;
        END $$;
    ''')

    # Add invoice matching columns for auto-match feature
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'bank_statement_transactions' AND column_name = 'suggested_invoice_id') THEN
                ALTER TABLE bank_statement_transactions ADD COLUMN suggested_invoice_id INTEGER REFERENCES invoices(id) ON DELETE SET NULL;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'bank_statement_transactions' AND column_name = 'match_confidence') THEN
                ALTER TABLE bank_statement_transactions ADD COLUMN match_confidence REAL;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'bank_statement_transactions' AND column_name = 'match_method') THEN
                ALTER TABLE bank_statement_transactions ADD COLUMN match_method TEXT;
            END IF;
        END $$;
    ''')

    # Add merge columns for transaction merging feature
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'bank_statement_transactions' AND column_name = 'merged_into_id') THEN
                ALTER TABLE bank_statement_transactions ADD COLUMN merged_into_id INTEGER REFERENCES bank_statement_transactions(id) ON DELETE SET NULL;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'bank_statement_transactions' AND column_name = 'is_merged_result') THEN
                ALTER TABLE bank_statement_transactions ADD COLUMN is_merged_result BOOLEAN DEFAULT FALSE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'bank_statement_transactions' AND column_name = 'merged_dates_display') THEN
                ALTER TABLE bank_statement_transactions ADD COLUMN merged_dates_display TEXT;
            END IF;
        END $$;
    ''')

    # Indexes for bank_statement_transactions table
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_status ON bank_statement_transactions(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_date ON bank_statement_transactions(transaction_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_supplier ON bank_statement_transactions(matched_supplier)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_company ON bank_statement_transactions(company_cui)')
    # Unique constraint to prevent duplicate transactions
    # Note: If upgrading, drop old index first: DROP INDEX IF EXISTS idx_unique_transaction;
    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_transaction
        ON bank_statement_transactions (company_cui, account_number, transaction_date, amount, currency, description)
        WHERE company_cui IS NOT NULL
          AND transaction_date IS NOT NULL
          AND amount IS NOT NULL
          AND description IS NOT NULL
    ''')

    # Roles table - defines permission sets
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS roles (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            can_add_invoices BOOLEAN DEFAULT FALSE,
            can_edit_invoices BOOLEAN DEFAULT FALSE,
            can_delete_invoices BOOLEAN DEFAULT FALSE,
            can_view_invoices BOOLEAN DEFAULT FALSE,
            can_access_accounting BOOLEAN DEFAULT FALSE,
            can_access_settings BOOLEAN DEFAULT FALSE,
            can_access_connectors BOOLEAN DEFAULT FALSE,
            can_access_templates BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Users table - references role
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT,
            password_hash TEXT,
            role_id INTEGER REFERENCES roles(id),
            is_active BOOLEAN DEFAULT TRUE,
            last_login TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Add password_hash, last_login, and last_seen columns if they don't exist (migration)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'password_hash') THEN
                ALTER TABLE users ADD COLUMN password_hash TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'last_login') THEN
                ALTER TABLE users ADD COLUMN last_login TIMESTAMP;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'last_seen') THEN
                ALTER TABLE users ADD COLUMN last_seen TIMESTAMP;
            END IF;
        END $$;
    ''')

    # Add can_edit_invoices column to roles table if it doesn't exist (migration)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'roles' AND column_name = 'can_edit_invoices') THEN
                ALTER TABLE roles ADD COLUMN can_edit_invoices BOOLEAN DEFAULT FALSE;
                -- Set edit permission to TRUE for Admin and Manager roles by default
                UPDATE roles SET can_edit_invoices = TRUE WHERE name IN ('Admin', 'Manager');
            END IF;
        END $$;
    ''')

    # Add can_access_hr column to roles table if it doesn't exist (HR module permission)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'roles' AND column_name = 'can_access_hr') THEN
                ALTER TABLE roles ADD COLUMN can_access_hr BOOLEAN DEFAULT FALSE;
                -- Set HR permission to TRUE for Admin role by default
                UPDATE roles SET can_access_hr = TRUE WHERE name = 'Admin';
            END IF;
        END $$;
    ''')

    # Add is_hr_manager column to roles table if it doesn't exist (HR Manager permission - bonus amounts, export, by employee)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'roles' AND column_name = 'is_hr_manager') THEN
                ALTER TABLE roles ADD COLUMN is_hr_manager BOOLEAN DEFAULT FALSE;
                -- Set HR Manager permission to TRUE for Admin role by default
                UPDATE roles SET is_hr_manager = TRUE WHERE name = 'Admin';
            END IF;
        END $$;
    ''')

    # Permissions table - defines all available permissions grouped by module
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS permissions (
            id SERIAL PRIMARY KEY,
            module_key TEXT NOT NULL,
            permission_key TEXT NOT NULL,
            label TEXT NOT NULL,
            description TEXT,
            icon TEXT,
            sort_order INTEGER DEFAULT 0,
            parent_id INTEGER REFERENCES permissions(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(module_key, permission_key)
        )
    ''')

    # Role permissions junction table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS role_permissions (
            id SERIAL PRIMARY KEY,
            role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
            granted BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(role_id, permission_id)
        )
    ''')

    # ============== Enhanced Permission System (v2) ==============
    # Supports scope-based permissions (deny, own, department, all) and matrix UI

    # Create permission scope enum type if not exists
    cursor.execute('''
        DO $$ BEGIN
            CREATE TYPE permission_scope AS ENUM ('deny', 'own', 'department', 'all');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    ''')

    # Enhanced permissions table with module/entity/action structure
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS permissions_v2 (
            id SERIAL PRIMARY KEY,
            module_key TEXT NOT NULL,
            module_label TEXT NOT NULL,
            module_icon TEXT,
            entity_key TEXT NOT NULL,
            entity_label TEXT NOT NULL,
            action_key TEXT NOT NULL,
            action_label TEXT NOT NULL,
            description TEXT,
            is_scope_based BOOLEAN DEFAULT TRUE,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(module_key, entity_key, action_key)
        )
    ''')

    # Role permissions with scope support
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS role_permissions_v2 (
            id SERIAL PRIMARY KEY,
            role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            permission_id INTEGER NOT NULL REFERENCES permissions_v2(id) ON DELETE CASCADE,
            scope permission_scope DEFAULT 'deny',
            granted BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(role_id, permission_id)
        )
    ''')

    # Seed permissions_v2 if empty
    cursor.execute('SELECT COUNT(*) as cnt FROM permissions_v2')
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute('''
            INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order) VALUES
            -- System Module
            ('system', 'System', 'bi-gear-fill', 'settings', 'Settings', 'access', 'Access', 'Access system settings', FALSE, 1),
            ('system', 'System', 'bi-gear-fill', 'settings', 'Settings', 'edit', 'Edit', 'Modify system settings', FALSE, 2),
            ('system', 'System', 'bi-gear-fill', 'users', 'Users', 'view', 'View', 'View user list', FALSE, 3),
            ('system', 'System', 'bi-gear-fill', 'users', 'Users', 'add', 'Add', 'Create new users', FALSE, 4),
            ('system', 'System', 'bi-gear-fill', 'users', 'Users', 'edit', 'Edit', 'Modify users', FALSE, 5),
            ('system', 'System', 'bi-gear-fill', 'users', 'Users', 'delete', 'Delete', 'Remove users', FALSE, 6),
            ('system', 'System', 'bi-gear-fill', 'roles', 'Roles', 'view', 'View', 'View roles', FALSE, 7),
            ('system', 'System', 'bi-gear-fill', 'roles', 'Roles', 'edit', 'Edit', 'Modify role permissions', FALSE, 8),
            ('system', 'System', 'bi-gear-fill', 'activity_logs', 'Activity Logs', 'view', 'View', 'View activity logs', FALSE, 9),
            ('system', 'System', 'bi-gear-fill', 'theme', 'Theme', 'edit', 'Edit', 'Customize theme settings', FALSE, 10),

            -- Invoices Module
            ('invoices', 'Invoices', 'bi-receipt', 'records', 'Invoice Records', 'view', 'View', 'View invoices', TRUE, 1),
            ('invoices', 'Invoices', 'bi-receipt', 'records', 'Invoice Records', 'add', 'Add', 'Create new invoices', TRUE, 2),
            ('invoices', 'Invoices', 'bi-receipt', 'records', 'Invoice Records', 'edit', 'Edit', 'Modify invoices', TRUE, 3),
            ('invoices', 'Invoices', 'bi-receipt', 'records', 'Invoice Records', 'delete', 'Delete', 'Remove invoices', TRUE, 4),
            ('invoices', 'Invoices', 'bi-receipt', 'records', 'Invoice Records', 'export', 'Export', 'Export invoice data', FALSE, 5),
            ('invoices', 'Invoices', 'bi-receipt', 'templates', 'Templates', 'view', 'View', 'View invoice templates', FALSE, 6),
            ('invoices', 'Invoices', 'bi-receipt', 'templates', 'Templates', 'edit', 'Edit', 'Modify invoice templates', FALSE, 7),

            -- Accounting Module
            ('accounting', 'Accounting', 'bi-calculator', 'dashboard', 'Dashboard', 'access', 'Access', 'Access accounting dashboard', FALSE, 1),
            ('accounting', 'Accounting', 'bi-calculator', 'reports', 'Reports', 'view', 'View', 'View accounting reports', TRUE, 2),
            ('accounting', 'Accounting', 'bi-calculator', 'reports', 'Reports', 'export', 'Export', 'Export reports', FALSE, 3),
            ('accounting', 'Accounting', 'bi-calculator', 'allocations', 'Allocations', 'view', 'View', 'View allocations', TRUE, 4),
            ('accounting', 'Accounting', 'bi-calculator', 'allocations', 'Allocations', 'edit', 'Edit', 'Modify allocations', TRUE, 5),
            ('accounting', 'Accounting', 'bi-calculator', 'connectors', 'Connectors', 'access', 'Access', 'Access external connectors', FALSE, 6),

            -- HR Module
            ('hr', 'HR', 'bi-people-fill', 'employees', 'Employees', 'view', 'View', 'View employee list', TRUE, 1),
            ('hr', 'HR', 'bi-people-fill', 'employees', 'Employees', 'add', 'Add', 'Create new employees', FALSE, 2),
            ('hr', 'HR', 'bi-people-fill', 'employees', 'Employees', 'edit', 'Edit', 'Modify employee data', TRUE, 3),
            ('hr', 'HR', 'bi-people-fill', 'employees', 'Employees', 'delete', 'Delete', 'Remove employees', FALSE, 4),
            ('hr', 'HR', 'bi-people-fill', 'bonuses', 'Events', 'view', 'View', 'View events', TRUE, 5),
            ('hr', 'HR', 'bi-people-fill', 'bonuses', 'Events', 'view_amounts', 'View Amounts', 'View bonus amounts (HR Manager)', FALSE, 6),
            ('hr', 'HR', 'bi-people-fill', 'bonuses', 'Events', 'add_event', 'Add Event', 'Create new events', FALSE, 7),
            ('hr', 'HR', 'bi-people-fill', 'bonuses', 'Events', 'add_bonus', 'Add Bonus', 'Create new bonuses', FALSE, 8),
            ('hr', 'HR', 'bi-people-fill', 'bonuses', 'Events', 'edit', 'Edit', 'Modify events', TRUE, 9),
            ('hr', 'HR', 'bi-people-fill', 'bonuses', 'Events', 'export', 'Export', 'Export event data', FALSE, 10),
            ('hr', 'HR', 'bi-people-fill', 'payroll', 'Payroll', 'view', 'View', 'View payroll data', TRUE, 11),
            ('hr', 'HR', 'bi-people-fill', 'payroll', 'Payroll', 'edit', 'Edit', 'Modify payroll', FALSE, 12)
        ''')

        # Set default permissions for existing roles
        # Get all roles
        cursor.execute('SELECT id, name FROM roles')
        roles_list = cursor.fetchall()

        # Get all permissions
        cursor.execute('SELECT id, module_key, entity_key, action_key, is_scope_based FROM permissions_v2')
        perms_list = cursor.fetchall()

        for role in roles_list:
            role_id = role['id']
            role_name = role['name']

            for perm in perms_list:
                perm_id = perm['id']
                is_scope = perm['is_scope_based']
                module = perm['module_key']
                entity = perm['entity_key']
                action = perm['action_key']

                # Default scope/granted based on role
                if role_name == 'Admin':
                    scope = 'all' if is_scope else 'all'
                    granted = True
                elif role_name == 'Manager':
                    if module == 'system' and entity in ('users', 'roles', 'theme'):
                        scope = 'deny'
                        granted = False
                    elif action == 'delete':
                        scope = 'department' if is_scope else 'department'
                        granted = True
                    else:
                        scope = 'all' if is_scope else 'all'
                        granted = True
                elif role_name == 'User':
                    if module == 'system':
                        scope = 'deny'
                        granted = False
                    elif action in ('delete', 'export'):
                        scope = 'deny'
                        granted = False
                    elif action in ('view', 'add'):
                        scope = 'own' if is_scope else 'own'
                        granted = True
                    elif action == 'edit':
                        scope = 'own' if is_scope else 'own'
                        granted = True
                    else:
                        scope = 'deny'
                        granted = False
                else:  # Viewer
                    if action == 'view' or action == 'access':
                        scope = 'own' if is_scope else 'own'
                        granted = True
                    else:
                        scope = 'deny'
                        granted = False

                cursor.execute('''
                    INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (role_id, permission_id) DO NOTHING
                ''', (role_id, perm_id, scope, granted))

    # Seed default permissions if table is empty
    cursor.execute('SELECT COUNT(*) as cnt FROM permissions')
    if cursor.fetchone()['cnt'] == 0:
        # Insert module permissions
        cursor.execute('''
            INSERT INTO permissions (module_key, permission_key, label, description, icon, sort_order) VALUES
            -- System module
            ('system', 'settings', 'Settings Access', 'Access to system settings and configuration', 'bi-gear', 1),
            ('system', 'activity_logs', 'Activity Logs', 'View user activity logs', 'bi-clock-history', 2),

            -- Invoices module
            ('invoices', 'view', 'View Invoices', 'View invoice list and details', 'bi-eye', 1),
            ('invoices', 'add', 'Add Invoices', 'Create new invoices', 'bi-plus-circle', 2),
            ('invoices', 'edit', 'Edit Invoices', 'Modify existing invoices', 'bi-pencil', 3),
            ('invoices', 'delete', 'Delete Invoices', 'Remove invoices from system', 'bi-trash', 4),

            -- Accounting module
            ('accounting', 'dashboard', 'Dashboard Access', 'Access accounting dashboard', 'bi-calculator', 1),
            ('accounting', 'export', 'Export Data', 'Export accounting data', 'bi-download', 2),
            ('accounting', 'templates', 'Templates', 'Manage invoice templates', 'bi-file-earmark-text', 3),
            ('accounting', 'connectors', 'Connectors', 'Manage external connectors', 'bi-plug', 4),

            -- HR module
            ('hr', 'access', 'Access HR', 'Access HR module', 'bi-people', 1),
            ('hr', 'manager', 'HR Manager', 'View bonus amounts, export, employee details', 'bi-person-badge', 2)
        ''')

        # Set parent_id for HR manager (child of HR access)
        cursor.execute('''
            UPDATE permissions
            SET parent_id = (SELECT id FROM permissions WHERE module_key = 'hr' AND permission_key = 'access')
            WHERE module_key = 'hr' AND permission_key = 'manager'
        ''')

        # Sync existing role permissions to new table
        cursor.execute('SELECT id, name FROM roles')
        roles = cursor.fetchall()

        for role in roles:
            role_id = role['id']
            # Get current boolean permissions
            cursor.execute('SELECT * FROM roles WHERE id = %s', (role_id,))
            r = cursor.fetchone()

            # Map old columns to new permission keys
            permission_map = {
                ('system', 'settings'): r.get('can_access_settings', False),
                ('invoices', 'view'): r.get('can_view_invoices', False),
                ('invoices', 'add'): r.get('can_add_invoices', False),
                ('invoices', 'edit'): r.get('can_edit_invoices', False),
                ('invoices', 'delete'): r.get('can_delete_invoices', False),
                ('accounting', 'dashboard'): r.get('can_access_accounting', False),
                ('accounting', 'templates'): r.get('can_access_templates', False),
                ('accounting', 'connectors'): r.get('can_access_connectors', False),
                ('hr', 'access'): r.get('can_access_hr', False),
                ('hr', 'manager'): r.get('is_hr_manager', False),
            }

            for (module_key, perm_key), granted in permission_map.items():
                if granted:
                    cursor.execute('''
                        INSERT INTO role_permissions (role_id, permission_id, granted)
                        SELECT %s, id, TRUE FROM permissions
                        WHERE module_key = %s AND permission_key = %s
                        ON CONFLICT (role_id, permission_id) DO NOTHING
                    ''', (role_id, module_key, perm_key))

    # Insert default roles if they don't exist
    cursor.execute('''
        INSERT INTO roles (name, description, can_add_invoices, can_edit_invoices, can_delete_invoices, can_view_invoices,
                          can_access_accounting, can_access_settings, can_access_connectors, can_access_templates)
        VALUES
            ('Admin', 'Full access to all features', TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE),
            ('Manager', 'Can manage invoices and view reports', TRUE, TRUE, TRUE, TRUE, TRUE, FALSE, TRUE, TRUE),
            ('User', 'Can add and view invoices', TRUE, FALSE, FALSE, TRUE, TRUE, FALSE, FALSE, FALSE),
            ('Viewer', 'Read-only access to invoices', FALSE, FALSE, FALSE, TRUE, TRUE, FALSE, FALSE, FALSE)
        ON CONFLICT (name) DO NOTHING
    ''')

    # Responsables table - employees/people responsible for departments
    # Used for both notification recipients and HR event bonuses
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS responsables (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            departments TEXT,
            company TEXT,
            brand TEXT,
            notify_on_allocation BOOLEAN DEFAULT TRUE,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Migration: Add company, brand, subdepartment columns to responsables if they don't exist
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'responsables' AND column_name = 'company') THEN
                ALTER TABLE responsables ADD COLUMN company TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'responsables' AND column_name = 'brand') THEN
                ALTER TABLE responsables ADD COLUMN brand TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'responsables' AND column_name = 'subdepartment') THEN
                ALTER TABLE responsables ADD COLUMN subdepartment TEXT;
            END IF;
            -- Make email nullable for HR employees who may not have email
            ALTER TABLE responsables ALTER COLUMN email DROP NOT NULL;
        END $$
    ''')

    # Notification settings table - email/SMTP configuration
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notification_settings (
            id SERIAL PRIMARY KEY,
            setting_key TEXT NOT NULL UNIQUE,
            setting_value TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Notification log table - track sent notifications
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notification_log (
            id SERIAL PRIMARY KEY,
            responsable_id INTEGER REFERENCES responsables(id),
            invoice_id INTEGER REFERENCES invoices(id) ON DELETE CASCADE,
            notification_type TEXT NOT NULL,
            subject TEXT,
            message TEXT,
            status TEXT DEFAULT 'pending',
            error_message TEXT,
            sent_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # User events/audit log table - tracks user actions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_events (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            user_email TEXT,
            event_type TEXT NOT NULL,
            event_description TEXT,
            entity_type TEXT,
            entity_id INTEGER,
            ip_address TEXT,
            user_agent TEXT,
            details JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # VAT rates table - configurable VAT percentages
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vat_rates (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            rate REAL NOT NULL,
            is_default BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Insert default VAT rates (Romanian standard rates) only if table is empty
    cursor.execute('SELECT COUNT(*) as cnt FROM vat_rates')
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute('''
            INSERT INTO vat_rates (name, rate, is_default, is_active)
            VALUES
                ('19%', 19.0, TRUE, TRUE),
                ('9%', 9.0, FALSE, TRUE),
                ('5%', 5.0, FALSE, TRUE),
                ('0%', 0.0, FALSE, TRUE)
        ''')

    # Dropdown options table - configurable dropdown values for accounting
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dropdown_options (
            id SERIAL PRIMARY KEY,
            dropdown_type TEXT NOT NULL,
            value TEXT NOT NULL,
            label TEXT NOT NULL,
            color TEXT DEFAULT NULL,
            opacity REAL DEFAULT 0.7,
            sort_order INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(dropdown_type, value)
        )
    ''')

    # Add color column if it doesn't exist (for existing databases)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'dropdown_options' AND column_name = 'color') THEN
                ALTER TABLE dropdown_options ADD COLUMN color TEXT DEFAULT NULL;
            END IF;
        END $$;
    ''')

    # Add opacity column if it doesn't exist (for existing databases)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'dropdown_options' AND column_name = 'opacity') THEN
                ALTER TABLE dropdown_options ADD COLUMN opacity REAL DEFAULT 0.7;
            END IF;
        END $$;
    ''')

    # Insert default dropdown options if table is empty
    cursor.execute('SELECT COUNT(*) as cnt FROM dropdown_options')
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute('''
            INSERT INTO dropdown_options (dropdown_type, value, label, color, opacity, sort_order, is_active)
            VALUES
                ('invoice_status', 'new', 'New', '#0d6efd', 0.7, 1, TRUE),
                ('invoice_status', 'processed', 'Processed', '#198754', 0.7, 2, TRUE),
                ('invoice_status', 'incomplete', 'Incomplete', '#ffc107', 0.7, 3, TRUE),
                ('invoice_status', 'eronata', 'Eronata', '#dc3545', 0.7, 4, TRUE),
                ('payment_status', 'not_paid', 'Not Paid', '#dc3545', 0.7, 1, TRUE),
                ('payment_status', 'paid', 'Paid', '#198754', 0.7, 2, TRUE)
        ''')

    # Theme settings table - global theme configuration for Jarvis
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS theme_settings (
            id SERIAL PRIMARY KEY,
            theme_name TEXT NOT NULL DEFAULT 'default',
            is_active BOOLEAN DEFAULT TRUE,
            settings JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Insert default theme if table is empty
    cursor.execute('SELECT COUNT(*) as cnt FROM theme_settings')
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute('''
            INSERT INTO theme_settings (theme_name, is_active, settings)
            VALUES ('Jarvis Default', TRUE, %s)
        ''', (json.dumps({
            'light': {
                'bgBody': '#f5f5f5',
                'bgCard': '#ffffff',
                'bgTableHeader': '#f8f9fa',
                'bgTableHover': '#e3f2fd',
                'bgInput': '#ffffff',
                'textPrimary': '#212529',
                'textSecondary': '#6c757d',
                'borderColor': '#dee2e6',
                'accentPrimary': '#0d6efd',
                'accentSuccess': '#198754',
                'accentWarning': '#ffc107',
                'accentDanger': '#dc3545',
                'navbarBg': '#6c757d'
            },
            'dark': {
                'bgBody': '#1a1a2e',
                'bgCard': '#16213e',
                'bgTableHeader': '#0f3460',
                'bgTableHover': '#1f4068',
                'bgInput': '#0f3460',
                'textPrimary': '#e4e4e4',
                'textSecondary': '#a0a0a0',
                'borderColor': '#2d4a6e',
                'accentPrimary': '#64b5f6',
                'accentSuccess': '#81c784',
                'accentWarning': '#ffb74d',
                'accentDanger': '#ef5350',
                'navbarBg': 'linear-gradient(135deg, #0f3460 0%, #16213e 100%)'
            }
        }),))

    # Module menu items table - configurable navigation menu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS module_menu_items (
            id SERIAL PRIMARY KEY,
            parent_id INTEGER REFERENCES module_menu_items(id) ON DELETE CASCADE,
            module_key TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            icon TEXT DEFAULT 'bi-grid',
            url TEXT,
            color TEXT DEFAULT '#6c757d',
            status TEXT DEFAULT 'active' CHECK (status IN ('active', 'coming_soon', 'hidden')),
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Insert default module menu items if table is empty
    cursor.execute('SELECT COUNT(*) as cnt FROM module_menu_items')
    if cursor.fetchone()['cnt'] == 0:
        # Insert parent modules first
        cursor.execute('''
            INSERT INTO module_menu_items (module_key, name, description, icon, url, color, status, sort_order)
            VALUES
                ('accounting', 'Accounting', 'Invoices, Budgets, Statements', 'bi-calculator', '/accounting', '#0d6efd', 'active', 1),
                ('hr', 'HR', 'Events, Bonuses, Employees', 'bi-people', '/hr/events/', '#9c27b0', 'active', 2),
                ('sales', 'Sales', 'Orders, Customers, Reports', 'bi-cart3', '#', '#dc3545', 'coming_soon', 3),
                ('aftersales', 'After Sales', 'Service, Warranty, Support', 'bi-tools', '#', '#198754', 'coming_soon', 4),
                ('settings', 'Settings', 'System Configuration', 'bi-gear', '/settings', '#6c757d', 'active', 5)
            RETURNING id, module_key
        ''')
        parent_rows = cursor.fetchall()
        parent_ids = {row['module_key']: row['id'] for row in parent_rows}

        # Insert submenu items for Accounting
        if 'accounting' in parent_ids:
            cursor.execute('''
                INSERT INTO module_menu_items (parent_id, module_key, name, description, icon, url, color, status, sort_order)
                VALUES
                    (%s, 'accounting_dashboard', 'Dashboard', 'View invoices', 'bi-grid-1x2', '/accounting', '#0d6efd', 'active', 1),
                    (%s, 'accounting_add', 'Add Invoice', 'Create new invoice', 'bi-plus-circle', '/add-invoice', '#0d6efd', 'active', 2),
                    (%s, 'accounting_templates', 'Templates', 'Manage parsing templates', 'bi-file-earmark-code', '/templates', '#0d6efd', 'active', 3),
                    (%s, 'accounting_statements', 'Bank Statements', 'Parse statements', 'bi-bank', '/statements/', '#0d6efd', 'active', 4)
            ''', (parent_ids['accounting'], parent_ids['accounting'], parent_ids['accounting'], parent_ids['accounting']))

        # Insert submenu items for HR
        if 'hr' in parent_ids:
            cursor.execute('''
                INSERT INTO module_menu_items (parent_id, module_key, name, description, icon, url, color, status, sort_order)
                VALUES
                    (%s, 'hr_events', 'Event Bonuses', 'Manage bonuses', 'bi-gift', '/hr/events/', '#9c27b0', 'active', 1),
                    (%s, 'hr_manage_events', 'Manage Events', 'Create/edit events', 'bi-calendar-event', '/hr/events/events', '#9c27b0', 'active', 2),
                    (%s, 'hr_employees', 'Employees', 'Employee list', 'bi-person-lines-fill', '/hr/events/employees', '#9c27b0', 'active', 3)
            ''', (parent_ids['hr'], parent_ids['hr'], parent_ids['hr']))

    # Create indexes for invoice queries (most frequently accessed)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(invoice_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_invoices_date_desc ON invoices(invoice_date DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_invoices_supplier ON invoices(supplier)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_invoices_created_at ON invoices(created_at DESC)')
    # Composite index for common filtered queries (non-deleted, date ordered)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_invoices_deleted_date ON invoices(deleted_at, invoice_date DESC)')

    # Allocation indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_allocations_invoice_id ON allocations(invoice_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_allocations_company ON allocations(company)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_allocations_department ON allocations(department)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_allocations_brand ON allocations(brand)')
    # Composite index for invoice+company lookups (optimizes filtered allocation queries)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_allocations_invoice_company ON allocations(invoice_id, company)')

    # Partial index for non-deleted invoices ordered by date (most common query pattern)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_invoices_active_date ON invoices(invoice_date DESC) WHERE deleted_at IS NULL')

    # User events indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_events_user_id ON user_events(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_events_event_type ON user_events(event_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_events_created_at ON user_events(created_at DESC)')

    # Department structure indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_dept_structure_company ON department_structure(company)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_dept_structure_dept ON department_structure(department)')

    # Commit table creation before attempting migrations
    conn.commit()

    # Add comment column if it doesn't exist (for existing databases)
    try:
        cursor.execute('ALTER TABLE invoices ADD COLUMN comment TEXT')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add reinvoice_brand column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE allocations ADD COLUMN reinvoice_brand TEXT')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add reinvoice_department column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE allocations ADD COLUMN reinvoice_department TEXT')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add reinvoice_subdepartment column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE allocations ADD COLUMN reinvoice_subdepartment TEXT')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add comment column to allocations if it doesn't exist
    try:
        cursor.execute('ALTER TABLE allocations ADD COLUMN comment TEXT')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add value_ron column if it doesn't exist (for currency conversion)
    try:
        cursor.execute('ALTER TABLE invoices ADD COLUMN value_ron REAL')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add value_eur column if it doesn't exist (for currency conversion)
    try:
        cursor.execute('ALTER TABLE invoices ADD COLUMN value_eur REAL')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add exchange_rate column if it doesn't exist (for currency conversion)
    try:
        cursor.execute('ALTER TABLE invoices ADD COLUMN exchange_rate REAL')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add deleted_at column for soft delete (bin functionality)
    try:
        cursor.execute('ALTER TABLE invoices ADD COLUMN deleted_at TIMESTAMP')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Create index for soft delete queries
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_invoices_deleted_at ON invoices(deleted_at)')
    conn.commit()

    # Add vat_rate column if it doesn't exist (for VAT subtraction feature)
    try:
        cursor.execute('ALTER TABLE invoices ADD COLUMN vat_rate REAL')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add subtract_vat and net_value columns for VAT subtraction feature
    try:
        cursor.execute('ALTER TABLE invoices ADD COLUMN subtract_vat BOOLEAN DEFAULT FALSE')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    try:
        cursor.execute('ALTER TABLE invoices ADD COLUMN net_value REAL')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add role_id column to users table if it doesn't exist (migration from old schema)
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN role_id INTEGER REFERENCES roles(id)')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add is_active column to users table if it doesn't exist
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT TRUE')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add updated_at column to users table if it doesn't exist
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add responsable_id column to department_structure if it doesn't exist
    try:
        cursor.execute('ALTER TABLE department_structure ADD COLUMN responsable_id INTEGER REFERENCES responsables(id) ON DELETE SET NULL')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add locked column to allocations if it doesn't exist
    try:
        cursor.execute('ALTER TABLE allocations ADD COLUMN locked BOOLEAN DEFAULT FALSE')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Create reinvoice_destinations table for multi-destination reinvoicing
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reinvoice_destinations (
            id SERIAL PRIMARY KEY,
            allocation_id INTEGER NOT NULL REFERENCES allocations(id) ON DELETE CASCADE,
            company TEXT NOT NULL,
            brand TEXT,
            department TEXT,
            subdepartment TEXT,
            percentage REAL NOT NULL,
            value REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()

    # Create index for reinvoice_destinations (using IF NOT EXISTS for reliability)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_reinvoice_dest_allocation ON reinvoice_destinations(allocation_id)')
    conn.commit()

    # ============== HR Module Schema ==============
    # Create separate schema for HR data isolation
    cursor.execute('CREATE SCHEMA IF NOT EXISTS hr')
    conn.commit()

    # HR Employees table - standalone employee list with optional link to Jarvis users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hr.employees (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            department TEXT,
            brand TEXT,
            company TEXT,
            user_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # HR Events table - event definitions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hr.events (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            company TEXT,
            brand TEXT,
            description TEXT,
            created_by INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # HR Events table - individual bonus records
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hr.event_bonuses (
            id SERIAL PRIMARY KEY,
            employee_id INTEGER NOT NULL REFERENCES hr.employees(id) ON DELETE CASCADE,
            event_id INTEGER NOT NULL REFERENCES hr.events(id) ON DELETE CASCADE,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            participation_start DATE,
            participation_end DATE,
            bonus_days NUMERIC(3,1),
            hours_free INTEGER,
            bonus_net NUMERIC(10,2),
            details TEXT,
            allocation_month TEXT,
            bonus_type_id INTEGER,
            created_by INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # HR Bonus Types table - configurable bonus rates
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hr.bonus_types (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            amount NUMERIC(10,2) NOT NULL,
            days_per_amount NUMERIC(5,2) DEFAULT 1,
            description TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Add bonus_type_id column if not exists (migration for existing databases)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_schema = 'hr' AND table_name = 'event_bonuses'
                          AND column_name = 'bonus_type_id') THEN
                ALTER TABLE hr.event_bonuses ADD COLUMN bonus_type_id INTEGER;
            END IF;
        END $$
    ''')

    # Migration: Rename amount_per_day to amount and add days_per_amount (for existing databases)
    cursor.execute('''
        DO $$
        BEGIN
            -- Rename amount_per_day to amount if old column exists
            IF EXISTS (SELECT 1 FROM information_schema.columns
                      WHERE table_schema = 'hr' AND table_name = 'bonus_types'
                      AND column_name = 'amount_per_day') THEN
                ALTER TABLE hr.bonus_types RENAME COLUMN amount_per_day TO amount;
            END IF;
            -- Add days_per_amount column if not exists
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_schema = 'hr' AND table_name = 'bonus_types'
                          AND column_name = 'days_per_amount') THEN
                ALTER TABLE hr.bonus_types ADD COLUMN days_per_amount NUMERIC(5,2) DEFAULT 1;
            END IF;
        END $$
    ''')

    # HR indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hr_employees_name ON hr.employees(name)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hr_employees_company ON hr.employees(company)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hr_events_dates ON hr.events(start_date, end_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hr_bonuses_employee ON hr.event_bonuses(employee_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hr_bonuses_event ON hr.event_bonuses(event_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hr_bonuses_year_month ON hr.event_bonuses(year, month)')
    conn.commit()

    # Migration: Migrate hr.employees to responsables table and update FK
    # Step 1: Add hr_employee_id column to responsables to track migration
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'responsables' AND column_name = 'hr_employee_id') THEN
                ALTER TABLE responsables ADD COLUMN hr_employee_id INTEGER;
            END IF;
        END $$
    ''')
    conn.commit()

    # Step 2: Migrate hr.employees to responsables (only if not already migrated)
    cursor.execute('''
        INSERT INTO responsables (name, departments, company, brand, is_active, hr_employee_id, created_at, updated_at)
        SELECT e.name, e.department, e.company, e.brand, e.is_active, e.id, e.created_at, e.updated_at
        FROM hr.employees e
        WHERE NOT EXISTS (
            SELECT 1 FROM responsables r WHERE r.hr_employee_id = e.id
        )
    ''')
    conn.commit()

    # Step 3: Update hr.event_bonuses to reference responsables instead of hr.employees
    # First, add responsable_id column if not exists
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_schema = 'hr' AND table_name = 'event_bonuses'
                          AND column_name = 'responsable_id') THEN
                ALTER TABLE hr.event_bonuses ADD COLUMN responsable_id INTEGER REFERENCES responsables(id);
            END IF;
        END $$
    ''')
    conn.commit()

    # Step 4: Populate responsable_id from employee_id mapping
    cursor.execute('''
        UPDATE hr.event_bonuses eb
        SET responsable_id = r.id
        FROM responsables r
        WHERE r.hr_employee_id = eb.employee_id
          AND eb.responsable_id IS NULL
    ''')
    conn.commit()

    # Migrate existing single reinvoice data to new table (if not already migrated)
    cursor.execute('''
        INSERT INTO reinvoice_destinations (allocation_id, company, brand, department, subdepartment, percentage, value)
        SELECT id, reinvoice_to, reinvoice_brand, reinvoice_department, reinvoice_subdepartment, 100.0, allocation_value
        FROM allocations
        WHERE reinvoice_to IS NOT NULL AND reinvoice_to != ''
        AND NOT EXISTS (
            SELECT 1 FROM reinvoice_destinations rd WHERE rd.allocation_id = allocations.id
        )
    ''')
    conn.commit()

    # Migration: Fix invoices with subtract_vat=true but vat_rate=null
    # Calculate the implied VAT rate from invoice_value and net_value, then match to closest standard rate
    cursor.execute('''
        SELECT id, invoice_value, net_value
        FROM invoices
        WHERE subtract_vat = true AND vat_rate IS NULL AND net_value IS NOT NULL AND net_value > 0
    ''')
    invoices_to_fix = cursor.fetchall()

    if invoices_to_fix:
        # Get available VAT rates
        cursor.execute('SELECT rate FROM vat_rates WHERE is_active = true ORDER BY rate DESC')
        available_rates = [row['rate'] for row in cursor.fetchall()]

        for inv in invoices_to_fix:
            # Calculate implied VAT rate: vat_rate = (invoice_value / net_value - 1) * 100
            implied_rate = (inv['invoice_value'] / inv['net_value'] - 1) * 100

            # Find closest matching rate
            closest_rate = min(available_rates, key=lambda r: abs(r - implied_rate))

            # Update invoice with matched rate
            cursor.execute('UPDATE invoices SET vat_rate = %s WHERE id = %s', (closest_rate, inv['id']))

        conn.commit()

    # Seed initial data if tables are empty
    cursor.execute('SELECT COUNT(*) FROM department_structure')
    result = cursor.fetchone()
    if result['count'] == 0:
        _seed_department_structure(cursor)

    cursor.execute('SELECT COUNT(*) FROM companies')
    result = cursor.fetchone()
    if result['count'] == 0:
        _seed_companies(cursor)

    conn.commit()
    release_db(conn)


def _seed_department_structure(cursor):
    """Seed initial department structure data."""
    structure_data = [
        ('Autoworld PLUS S.R.L.', 'Mazda', 'Sales', None, 'Roxana Biris', 'Amanda Gadalean'),
        ('Autoworld PLUS S.R.L.', 'MG Motor', 'Aftersales', 'Piese si Accesorii', 'Mihai Ploscar', 'Amanda Gadalean'),
        ('Autoworld PLUS S.R.L.', 'MG Motor', 'Aftersales', 'Reparatii Generale', 'Mihai Ploscar', 'Amanda Gadalean'),
        ('Autoworld INTERNATIONAL S.R.L.', 'Volkswagen (PKW)', 'Sales', None, 'Ovidiu Ciobanca', 'Raluca Asztalos'),
        ('Autoworld INTERNATIONAL S.R.L.', 'Volkswagen (PKW)', 'Aftersales', 'Piese si Accesorii', 'Ioan Parocescu', 'Raluca Asztalos'),
        ('Autoworld INTERNATIONAL S.R.L.', 'Volkswagen (PKW)', 'Aftersales', 'Reparatii Generale', 'Ioan Parocescu', 'Raluca Asztalos'),
        ('Autoworld INTERNATIONAL S.R.L.', 'Volkswagen Comerciale (LNF)', 'Sales', None, 'Ovidiu Ciobanca', 'Raluca Asztalos'),
        ('Autoworld INTERNATIONAL S.R.L.', 'Volkswagen Comerciale (LNF)', 'Aftersales', 'Piese si Accesorii', 'Ioan Parocescu', 'Raluca Asztalos'),
        ('Autoworld INTERNATIONAL S.R.L.', 'Volkswagen Comerciale (LNF)', 'Aftersales', 'Reparatii Generale', 'Ioan Parocescu', 'Raluca Asztalos'),
        ('Autoworld PREMIUM S.R.L.', 'Audi', 'Sales', None, 'Roger Patrasc', 'George Pop'),
        ('Autoworld PREMIUM S.R.L.', 'AAP', 'Sales', None, 'Roger Patrasc', 'George Pop'),
        ('Autoworld PREMIUM S.R.L.', 'Audi', 'Aftersales', 'Piese si Accesorii', 'Calin Duca', 'George Pop'),
        ('Autoworld PREMIUM S.R.L.', 'Audi', 'Aftersales', 'Reparatii Generale', 'Calin Duca', 'George Pop'),
        ('Autoworld PRESTIGE S.R.L.', 'Volvo', 'Sales', None, 'Madalina Morutan', 'Amanda Gadalean'),
        ('Autoworld PRESTIGE S.R.L.', 'Volvo', 'Aftersales', 'Piese si Accesorii', 'Mihai Ploscar', 'Amanda Gadalean'),
        ('Autoworld PRESTIGE S.R.L.', 'Volvo', 'Aftersales', 'Reparatii Generale', 'Mihai Ploscar', 'Amanda Gadalean'),
        ('Autoworld NEXT S.R.L.', 'DasWeltAuto', 'Sales', None, 'Ovidiu Bucur', 'Raluca Asztalos'),
        ('Autoworld NEXT S.R.L.', 'Autoworld.ro', 'Sales', None, 'Ovidiu Bucur', 'Sebastian Sabo'),
        ('Autoworld ONE S.R.L.', 'Toyota', 'Sales', None, 'Monica Niculae', 'Sebastian Sabo'),
        ('Autoworld ONE S.R.L.', None, 'Aftersales', 'Piese si Accesorii', 'Ovidiu', 'Sebastian Sabo'),
        ('Autoworld ONE S.R.L.', None, 'Aftersales', 'Reparatii Generale', 'Ovidiu', 'Sebastian Sabo'),
        ('AUTOWORLD S.R.L.', None, 'Conducere', None, 'Ioan Mezei', 'Anyone'),
        ('AUTOWORLD S.R.L.', None, 'Administrativ', None, 'Istvan Papp', 'Anyone'),
        ('AUTOWORLD S.R.L.', None, 'HR', None, 'Diana Deac', 'Anyone'),
        ('AUTOWORLD S.R.L.', None, 'Marketing', None, 'Sebastian Sabo', 'Anyone'),
        ('AUTOWORLD S.R.L.', None, 'Contabilitate', None, 'Claudia Bruslea', 'Anyone'),
    ]

    query = '''
        INSERT INTO department_structure (company, brand, department, subdepartment, manager, marketing)
        VALUES (%s, %s, %s, %s, %s, %s)
    '''
    cursor.executemany(query, structure_data)


def _seed_companies(cursor):
    """Seed initial companies with VAT data."""
    companies_data = [
        ('Autoworld PLUS S.R.L.', 'Mazda & MG', 'RO 50022994'),
        ('Autoworld INTERNATIONAL S.R.L.', 'Volkswagen', 'RO 50186890'),
        ('Autoworld PREMIUM S.R.L.', 'Audi & Audi Approved Plus', 'RO 50188939'),
        ('Autoworld PRESTIGE S.R.L.', 'Volvo', 'RO 50186920'),
        ('Autoworld NEXT S.R.L.', 'DasWeltAuto', 'RO 50186814'),
        ('Autoworld INSURANCE S.R.L.', 'Dep Asigurari - partial', 'RO 48988808'),
        ('Autoworld ONE S.R.L.', 'Toyota', 'RO 15128629'),
        ('AUTOWORLD S.R.L.', 'Admin Conta Mkt PLR', 'RO 225615'),
    ]

    query = '''
        INSERT INTO companies (company, brands, vat)
        VALUES (%s, %s, %s)
    '''
    cursor.executemany(query, companies_data)


def dict_from_row(row):
    """Convert a database row to a dictionary with proper date serialization."""
    if row is None:
        return None
    result = dict(row)
    # Convert date/datetime objects to ISO format strings for JSON serialization
    for key, value in result.items():
        if hasattr(value, 'isoformat'):
            # For date objects, just return YYYY-MM-DD
            if hasattr(value, 'hour'):
                # datetime object - keep full ISO format
                result[key] = value.isoformat()
            else:
                # date object - just YYYY-MM-DD
                result[key] = value.isoformat()
    return result


def save_invoice(
    supplier: str,
    invoice_template: str,
    invoice_number: str,
    invoice_date: str,
    invoice_value: float,
    currency: str,
    drive_link: str,
    distributions: list[dict],
    value_ron: float = None,
    value_eur: float = None,
    exchange_rate: float = None,
    comment: str = None,
    payment_status: str = 'not_paid',
    subtract_vat: bool = False,
    vat_rate: float = None,
    net_value: float = None
) -> int:
    """
    Save invoice and its allocations to database.
    Returns the invoice ID.
    """
    conn = get_db()
    cursor = get_cursor(conn)

    try:
        cursor.execute('''
            INSERT INTO invoices (supplier, invoice_template, invoice_number, invoice_date, invoice_value, currency, drive_link, value_ron, value_eur, exchange_rate, comment, payment_status, subtract_vat, vat_rate, net_value)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (supplier, invoice_template, invoice_number, invoice_date, invoice_value, currency, drive_link, value_ron, value_eur, exchange_rate, comment, payment_status, subtract_vat, vat_rate, net_value))
        invoice_id = cursor.fetchone()['id']

        # Insert allocations
        # Use net_value for allocation calculations if VAT subtraction is enabled
        base_value = net_value if subtract_vat and net_value else invoice_value
        for dist in distributions:
            allocation_value = base_value * dist['allocation']

            # Look up the responsible (manager) from department_structure if not provided
            responsible = dist.get('responsible', '')
            if not responsible and dist['company'] and dist['department']:
                # Build query with optional brand and subdepartment filters
                conditions = ['ds.company = %s', 'ds.department = %s']
                params = [dist['company'], dist['department']]

                brand = dist.get('brand')
                if brand:
                    conditions.append('ds.brand = %s')
                    params.append(brand)

                subdept = dist.get('subdepartment')
                if subdept:
                    conditions.append('ds.subdepartment = %s')
                    params.append(subdept)

                # Use manager_ids joined with responsables to get manager names
                cursor.execute(f'''
                    SELECT COALESCE(
                        (SELECT string_agg(r.name, ', ')
                         FROM unnest(ds.manager_ids) AS mid
                         JOIN responsables r ON r.id = mid),
                        ds.manager,
                        ''
                    ) AS manager_name
                    FROM department_structure ds
                    WHERE {' AND '.join(conditions)}
                    LIMIT 1
                ''', tuple(params))
                row = cursor.fetchone()
                if row and row['manager_name']:
                    responsible = row['manager_name']

            cursor.execute('''
                INSERT INTO allocations (invoice_id, company, brand, department, subdepartment, allocation_percent, allocation_value, responsible, reinvoice_to, reinvoice_brand, reinvoice_department, reinvoice_subdepartment, locked, comment)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                invoice_id,
                dist['company'],
                dist.get('brand'),
                dist['department'],
                dist.get('subdepartment'),
                dist['allocation'] * 100,
                allocation_value,
                responsible,
                dist.get('reinvoice_to'),
                dist.get('reinvoice_brand'),
                dist.get('reinvoice_department'),
                dist.get('reinvoice_subdepartment'),
                dist.get('locked', False),
                dist.get('comment')
            ))
            allocation_id = cursor.fetchone()['id']

            # Insert reinvoice destinations if provided
            reinvoice_dests = dist.get('reinvoice_destinations', [])
            for rd in reinvoice_dests:
                rd_value = allocation_value * (rd['percentage'] / 100)
                cursor.execute('''
                    INSERT INTO reinvoice_destinations
                    (allocation_id, company, brand, department, subdepartment, percentage, value)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (
                    allocation_id,
                    rd['company'],
                    rd.get('brand'),
                    rd.get('department'),
                    rd.get('subdepartment'),
                    rd['percentage'],
                    rd_value
                ))

        conn.commit()
        clear_invoices_cache()  # Invalidate cache on new invoice
        return invoice_id

    except Exception as e:
        conn.rollback()
        if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
            raise ValueError(f"Invoice {invoice_number} already exists in database")
        raise
    finally:
        release_db(conn)


def get_all_invoices(limit: int = 100, offset: int = 0, company: Optional[str] = None,
                     start_date: Optional[str] = None, end_date: Optional[str] = None,
                     department: Optional[str] = None, subdepartment: Optional[str] = None,
                     brand: Optional[str] = None, status: Optional[str] = None,
                     payment_status: Optional[str] = None, include_deleted: bool = False) -> list[dict]:
    """Get all invoices with pagination and optional filtering by allocation fields.

    By default, deleted invoices (with deleted_at set) are excluded.
    Set include_deleted=True to get only deleted invoices (for the bin view).
    """
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        # Build query with optional joins and filters
        query = '''
            SELECT DISTINCT i.*
            FROM invoices i
        '''
        params = []
        conditions = []

        # If any allocation filter is set, join with allocations table
        if company or department or subdepartment or brand:
            query = '''
                SELECT DISTINCT i.*
                FROM invoices i
                JOIN allocations a ON a.invoice_id = i.id
            '''
            if company:
                conditions.append('a.company = %s')
                params.append(company)
            if department:
                conditions.append('a.department = %s')
                params.append(department)
            if subdepartment:
                conditions.append('a.subdepartment = %s')
                params.append(subdepartment)
            if brand:
                conditions.append('a.brand = %s')
                params.append(brand)

        # Soft delete filter
        if include_deleted:
            conditions.append('i.deleted_at IS NOT NULL')
        else:
            conditions.append('i.deleted_at IS NULL')

        # Date filters on invoice table
        if start_date:
            conditions.append('i.invoice_date >= %s')
            params.append(start_date)
        if end_date:
            conditions.append('i.invoice_date <= %s')
            params.append(end_date)

        # Status filters
        if status:
            conditions.append('i.status = %s')
            params.append(status)
        if payment_status:
            conditions.append('i.payment_status = %s')
            params.append(payment_status)

        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)

        query += ' ORDER BY i.created_at DESC LIMIT %s OFFSET %s'
        params.extend([limit, offset])

        cursor.execute(query, params)
        invoices = [dict_from_row(row) for row in cursor.fetchall()]
        return invoices
    finally:
        release_db(conn)


def get_invoice_with_allocations(invoice_id: int) -> Optional[dict]:
    """Get invoice with all its allocations and their reinvoice destinations.

    Optimized to use batch query for reinvoice_destinations instead of N+1 queries.
    """
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        cursor.execute('SELECT * FROM invoices WHERE id = %s', (invoice_id,))
        invoice = cursor.fetchone()

        if not invoice:
            return None

        invoice = dict_from_row(invoice)

        cursor.execute('SELECT * FROM allocations WHERE invoice_id = %s', (invoice_id,))
        allocations = [dict_from_row(row) for row in cursor.fetchall()]

        # Batch fetch all reinvoice destinations for this invoice's allocations (single query)
        allocation_ids = [alloc['id'] for alloc in allocations]
        reinvoice_map = {}  # allocation_id -> list of destinations

        if allocation_ids:
            placeholders = ','.join(['%s'] * len(allocation_ids))
            cursor.execute(f'''
                SELECT id, allocation_id, company, brand, department, subdepartment, percentage, value
                FROM reinvoice_destinations
                WHERE allocation_id IN ({placeholders})
            ''', allocation_ids)

            for row in cursor.fetchall():
                rd = dict_from_row(row)
                alloc_id = rd.pop('allocation_id')
                if alloc_id not in reinvoice_map:
                    reinvoice_map[alloc_id] = []
                reinvoice_map[alloc_id].append(rd)

        # Assign reinvoice destinations to their allocations
        for alloc in allocations:
            alloc['reinvoice_destinations'] = reinvoice_map.get(alloc['id'], [])

        invoice['allocations'] = allocations
        return invoice
    finally:
        release_db(conn)


def get_invoices_with_allocations(limit: int = 100, offset: int = 0, company: Optional[str] = None,
                                   start_date: Optional[str] = None, end_date: Optional[str] = None,
                                   department: Optional[str] = None, subdepartment: Optional[str] = None,
                                   brand: Optional[str] = None, status: Optional[str] = None,
                                   payment_status: Optional[str] = None, include_deleted: bool = False) -> list[dict]:
    """Get all invoices with their allocations in a single optimized query.

    Uses PostgreSQL JSON aggregation to fetch invoices and allocations together,
    avoiding N+1 query problems. This is much faster than fetching invoices
    then making separate queries for each invoice's allocations.

    Results are cached for 60 seconds to reduce database load on repeated page views.
    """
    global _invoices_cache

    # Build cache key from all parameters
    cache_key = f"{limit}:{offset}:{company}:{start_date}:{end_date}:{department}:{subdepartment}:{brand}:{status}:{payment_status}:{include_deleted}"

    # Check cache
    if _is_cache_valid(_invoices_cache) and _invoices_cache.get('key') == cache_key:
        return _invoices_cache['data']

    conn = get_db()
    try:
        cursor = get_cursor(conn)

        # Build the query with optional filters
        params = []
        conditions = []

        # Soft delete filter
        if include_deleted:
            conditions.append('i.deleted_at IS NOT NULL')
        else:
            conditions.append('i.deleted_at IS NULL')

        # Date filters
        if start_date:
            conditions.append('i.invoice_date >= %s')
            params.append(start_date)
        if end_date:
            conditions.append('i.invoice_date <= %s')
            params.append(end_date)

        # Status filters
        if status:
            conditions.append('i.status = %s')
            params.append(status)
        if payment_status:
            conditions.append('i.payment_status = %s')
            params.append(payment_status)

        # Allocation filters - if any are set, filter invoices that have matching allocations
        allocation_filters = []
        if company:
            allocation_filters.append('a.company = %s')
            params.append(company)
        if department:
            allocation_filters.append('a.department = %s')
            params.append(department)
        if subdepartment:
            allocation_filters.append('a.subdepartment = %s')
            params.append(subdepartment)
        if brand:
            allocation_filters.append('a.brand = %s')
            params.append(brand)

        where_clause = ' AND '.join(conditions) if conditions else '1=1'

        if allocation_filters:
            # If we have allocation filters, use a subquery to filter invoices
            allocation_filter_clause = ' AND '.join(allocation_filters)
            query = f'''
            WITH filtered_invoices AS (
                SELECT DISTINCT i.id
                FROM invoices i
                JOIN allocations a ON a.invoice_id = i.id
                WHERE {where_clause} AND {allocation_filter_clause}
                ORDER BY i.id DESC
                LIMIT %s OFFSET %s
            )
            SELECT
                i.*,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'id', a.id,
                            'invoice_id', a.invoice_id,
                            'company', a.company,
                            'brand', a.brand,
                            'department', a.department,
                            'subdepartment', a.subdepartment,
                            'allocation_percent', a.allocation_percent,
                            'allocation_value', a.allocation_value,
                            'responsible', a.responsible,
                            'reinvoice_to', a.reinvoice_to,
                            'reinvoice_brand', a.reinvoice_brand,
                            'reinvoice_department', a.reinvoice_department,
                            'reinvoice_subdepartment', a.reinvoice_subdepartment,
                            'locked', a.locked,
                            'comment', a.comment,
                            'reinvoice_destinations', COALESCE(
                                (SELECT json_agg(
                                    json_build_object(
                                        'id', rd.id,
                                        'company', rd.company,
                                        'brand', rd.brand,
                                        'department', rd.department,
                                        'subdepartment', rd.subdepartment,
                                        'percentage', rd.percentage,
                                        'value', rd.value
                                    )
                                ) FROM reinvoice_destinations rd WHERE rd.allocation_id = a.id),
                                '[]'::json
                            )
                        )
                    ) FILTER (WHERE a.id IS NOT NULL),
                    '[]'::json
                ) as allocations
            FROM filtered_invoices fi
            JOIN invoices i ON i.id = fi.id
            LEFT JOIN allocations a ON a.invoice_id = i.id
            GROUP BY i.id
            ORDER BY i.created_at DESC
            '''
        else:
            # No allocation filters - simpler query
            query = f'''
            WITH paginated_invoices AS (
                SELECT i.*
                FROM invoices i
                WHERE {where_clause}
                ORDER BY i.created_at DESC
                LIMIT %s OFFSET %s
            )
            SELECT
                pi.*,
                COALESCE(
                    json_agg(
                        json_build_object(
                            'id', a.id,
                            'invoice_id', a.invoice_id,
                            'company', a.company,
                            'brand', a.brand,
                            'department', a.department,
                            'subdepartment', a.subdepartment,
                            'allocation_percent', a.allocation_percent,
                            'allocation_value', a.allocation_value,
                            'responsible', a.responsible,
                            'reinvoice_to', a.reinvoice_to,
                            'reinvoice_brand', a.reinvoice_brand,
                            'reinvoice_department', a.reinvoice_department,
                            'reinvoice_subdepartment', a.reinvoice_subdepartment,
                            'locked', a.locked,
                            'comment', a.comment,
                            'reinvoice_destinations', COALESCE(
                                (SELECT json_agg(
                                    json_build_object(
                                        'id', rd.id,
                                        'company', rd.company,
                                        'brand', rd.brand,
                                        'department', rd.department,
                                        'subdepartment', rd.subdepartment,
                                        'percentage', rd.percentage,
                                        'value', rd.value
                                    )
                                ) FROM reinvoice_destinations rd WHERE rd.allocation_id = a.id),
                                '[]'::json
                            )
                        )
                    ) FILTER (WHERE a.id IS NOT NULL),
                    '[]'::json
                ) as allocations
            FROM paginated_invoices pi
            LEFT JOIN allocations a ON a.invoice_id = pi.id
            GROUP BY pi.id, pi.supplier, pi.invoice_template, pi.invoice_number, pi.invoice_date,
                     pi.invoice_value, pi.currency, pi.value_ron, pi.value_eur, pi.exchange_rate,
                     pi.drive_link, pi.comment, pi.status, pi.payment_status, pi.deleted_at,
                     pi.created_at, pi.updated_at, pi.subtract_vat, pi.vat_rate, pi.net_value
            ORDER BY pi.created_at DESC
            '''

        params.extend([limit, offset])
        cursor.execute(query, params)

        invoices = []
        for row in cursor.fetchall():
            invoice = dict_from_row(row)
            # The allocations field is already JSON from the query
            if isinstance(invoice.get('allocations'), str):
                invoice['allocations'] = json.loads(invoice['allocations'])
            invoices.append(invoice)

        # Cache the results
        _invoices_cache['data'] = invoices
        _invoices_cache['timestamp'] = time.time()
        _invoices_cache['key'] = cache_key

        return invoices
    finally:
        release_db(conn)


def get_allocations_by_company(company: str) -> list[dict]:
    """Get all allocations for a specific company."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT a.*, i.supplier, i.invoice_number, i.invoice_date
        FROM allocations a
        JOIN invoices i ON a.invoice_id = i.id
        WHERE a.company = %s
        ORDER BY i.invoice_date DESC
    ''', (company,))

    results = [dict_from_row(row) for row in cursor.fetchall()]
    release_db(conn)
    return results


def get_allocations_by_department(company: str, department: str) -> list[dict]:
    """Get all allocations for a specific department."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT a.*, i.supplier, i.invoice_number, i.invoice_date
        FROM allocations a
        JOIN invoices i ON a.invoice_id = i.id
        WHERE a.company = %s AND a.department = %s
        ORDER BY i.invoice_date DESC
    ''', (company, department))

    results = [dict_from_row(row) for row in cursor.fetchall()]
    release_db(conn)
    return results


def get_summary_by_company(start_date: Optional[str] = None, end_date: Optional[str] = None,
                          department: Optional[str] = None, subdepartment: Optional[str] = None,
                          brand: Optional[str] = None) -> list[dict]:
    """Get total allocation values grouped by company.

    Returns totals in both RON and EUR for currency toggle support.
    Results are cached for 60 seconds to reduce DB load on dashboard tab switches.
    """
    global _summary_cache

    # Build cache key from parameters
    cache_key = f"{start_date}:{end_date}:{department}:{subdepartment}:{brand}"
    cache_entry = _summary_cache['company'].get(cache_key)

    # Check cache
    if cache_entry and (time.time() - cache_entry['timestamp']) < _summary_cache['ttl']:
        return cache_entry['data']

    conn = get_db()
    try:
        cursor = get_cursor(conn)

        # Calculate allocation values in RON and EUR based on invoice conversion rates
        query = '''
            SELECT
                a.company,
                SUM(CASE WHEN i.invoice_value > 0 AND i.value_ron IS NOT NULL
                    THEN a.allocation_value * i.value_ron / i.invoice_value
                    ELSE a.allocation_value END) as total_value_ron,
                SUM(CASE WHEN i.invoice_value > 0 AND i.value_eur IS NOT NULL
                    THEN a.allocation_value * i.value_eur / i.invoice_value
                    ELSE a.allocation_value / COALESCE(i.exchange_rate, 5.0) END) as total_value_eur,
                COUNT(DISTINCT a.invoice_id) as invoice_count,
                AVG(COALESCE(i.exchange_rate, 5.0)) as avg_exchange_rate
            FROM allocations a
            JOIN invoices i ON a.invoice_id = i.id
            WHERE i.deleted_at IS NULL
        '''
        params = []
        conditions = []

        if start_date:
            conditions.append('i.invoice_date >= %s')
            params.append(start_date)
        if end_date:
            conditions.append('i.invoice_date <= %s')
            params.append(end_date)
        if department:
            conditions.append('a.department = %s')
            params.append(department)
        if subdepartment:
            conditions.append('a.subdepartment = %s')
            params.append(subdepartment)
        if brand:
            conditions.append('a.brand = %s')
            params.append(brand)

        if conditions:
            query += ' AND ' + ' AND '.join(conditions)

        query += ' GROUP BY a.company ORDER BY total_value_ron DESC'

        cursor.execute(query, params)
        results = [dict_from_row(row) for row in cursor.fetchall()]

        # Cache results and enforce size limit
        _summary_cache['company'][cache_key] = {'data': results, 'timestamp': time.time()}
        _enforce_summary_cache_limit('company')

        return results
    finally:
        release_db(conn)


def get_summary_by_department(company: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None,
                              department: Optional[str] = None, subdepartment: Optional[str] = None,
                              brand: Optional[str] = None) -> list[dict]:
    """Get total allocation values grouped by department.

    Results are cached for 60 seconds to reduce DB load on dashboard tab switches.
    """
    global _summary_cache

    # Build cache key from parameters
    cache_key = f"{company}:{start_date}:{end_date}:{department}:{subdepartment}:{brand}"
    cache_entry = _summary_cache['department'].get(cache_key)

    # Check cache
    if cache_entry and (time.time() - cache_entry['timestamp']) < _summary_cache['ttl']:
        return cache_entry['data']

    conn = get_db()
    try:
        cursor = get_cursor(conn)

        # Calculate allocation values in RON and EUR based on invoice conversion rates
        query = '''
            SELECT
                a.company,
                a.department,
                a.subdepartment,
                SUM(CASE WHEN i.invoice_value > 0 AND i.value_ron IS NOT NULL
                    THEN a.allocation_value * i.value_ron / i.invoice_value
                    ELSE a.allocation_value END) as total_value_ron,
                SUM(CASE WHEN i.invoice_value > 0 AND i.value_eur IS NOT NULL
                    THEN a.allocation_value * i.value_eur / i.invoice_value
                    ELSE a.allocation_value / COALESCE(i.exchange_rate, 5.0) END) as total_value_eur,
                COUNT(DISTINCT a.invoice_id) as invoice_count,
                AVG(COALESCE(i.exchange_rate, 5.0)) as avg_exchange_rate
            FROM allocations a
            JOIN invoices i ON a.invoice_id = i.id
            WHERE i.deleted_at IS NULL
        '''
        params = []
        conditions = []

        if company:
            conditions.append('a.company = %s')
            params.append(company)
        if start_date:
            conditions.append('i.invoice_date >= %s')
            params.append(start_date)
        if end_date:
            conditions.append('i.invoice_date <= %s')
            params.append(end_date)
        if department:
            conditions.append('a.department = %s')
            params.append(department)
        if subdepartment:
            conditions.append('a.subdepartment = %s')
            params.append(subdepartment)
        if brand:
            conditions.append('a.brand = %s')
            params.append(brand)

        if conditions:
            query += ' AND ' + ' AND '.join(conditions)

        query += ' GROUP BY a.company, a.department, a.subdepartment ORDER BY total_value_ron DESC'

        cursor.execute(query, params)
        results = [dict_from_row(row) for row in cursor.fetchall()]

        # Cache results and enforce size limit
        _summary_cache['department'][cache_key] = {'data': results, 'timestamp': time.time()}
        _enforce_summary_cache_limit('department')

        return results
    finally:
        release_db(conn)


def get_summary_by_brand(company: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None,
                         department: Optional[str] = None, subdepartment: Optional[str] = None,
                         brand: Optional[str] = None) -> list[dict]:
    """Get total allocation values grouped by brand (Linie de business) with invoice details.

    Results are cached for 60 seconds to reduce DB load on dashboard tab switches.
    """
    global _summary_cache

    # Build cache key from parameters
    cache_key = f"{company}:{start_date}:{end_date}:{department}:{subdepartment}:{brand}"
    cache_entry = _summary_cache['brand'].get(cache_key)

    # Check cache
    if cache_entry and (time.time() - cache_entry['timestamp']) < _summary_cache['ttl']:
        return cache_entry['data']

    conn = get_db()
    try:
        cursor = get_cursor(conn)

        # Calculate allocation values in RON and EUR based on invoice conversion rates
        query = '''
            SELECT a.brand,
                   SUM(CASE WHEN i.invoice_value > 0 AND i.value_ron IS NOT NULL
                       THEN a.allocation_value * i.value_ron / i.invoice_value
                       ELSE a.allocation_value END) as total_value_ron,
                   SUM(CASE WHEN i.invoice_value > 0 AND i.value_eur IS NOT NULL
                       THEN a.allocation_value * i.value_eur / i.invoice_value
                       ELSE a.allocation_value / COALESCE(i.exchange_rate, 5.0) END) as total_value_eur,
                   COUNT(DISTINCT a.invoice_id) as invoice_count,
                   AVG(COALESCE(i.exchange_rate, 5.0)) as avg_exchange_rate,
                   STRING_AGG(DISTINCT i.invoice_number, ', ') as invoice_numbers,
                   JSON_AGG(JSON_BUILD_OBJECT(
                       'department', a.department,
                       'subdepartment', a.subdepartment,
                       'brand', a.brand,
                       'value', a.allocation_value,
                       'value_ron', CASE WHEN i.invoice_value > 0 AND i.value_ron IS NOT NULL
                           THEN a.allocation_value * i.value_ron / i.invoice_value
                           ELSE a.allocation_value END,
                       'value_eur', CASE WHEN i.invoice_value > 0 AND i.value_eur IS NOT NULL
                           THEN a.allocation_value * i.value_eur / i.invoice_value
                           ELSE a.allocation_value / COALESCE(i.exchange_rate, 5.0) END,
                       'percent', ROUND(a.allocation_percent),
                       'reinvoice_to', a.reinvoice_to,
                       'reinvoice_brand', a.reinvoice_brand,
                       'reinvoice_department', a.reinvoice_department,
                       'reinvoice_subdepartment', a.reinvoice_subdepartment,
                       'currency', i.currency
                   )) as split_values
            FROM allocations a
            JOIN invoices i ON a.invoice_id = i.id
            WHERE i.deleted_at IS NULL
        '''
        params = []
        conditions = []

        if company:
            conditions.append('a.company = %s')
            params.append(company)
        if start_date:
            conditions.append('i.invoice_date >= %s')
            params.append(start_date)
        if end_date:
            conditions.append('i.invoice_date <= %s')
            params.append(end_date)
        if department:
            conditions.append('a.department = %s')
            params.append(department)
        if subdepartment:
            conditions.append('a.subdepartment = %s')
            params.append(subdepartment)
        if brand:
            conditions.append('a.brand = %s')
            params.append(brand)

        if conditions:
            query += ' AND ' + ' AND '.join(conditions)

        query += ' GROUP BY a.brand ORDER BY total_value_ron DESC'

        cursor.execute(query, params)
        results = [dict_from_row(row) for row in cursor.fetchall()]

        # Cache results and enforce size limit
        _summary_cache['brand'][cache_key] = {'data': results, 'timestamp': time.time()}
        _enforce_summary_cache_limit('brand')

        return results
    finally:
        release_db(conn)


def get_summary_by_supplier(company: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None,
                            department: Optional[str] = None, subdepartment: Optional[str] = None,
                            brand: Optional[str] = None) -> list[dict]:
    """Get allocation values grouped by supplier.

    Uses allocation values (like other summary functions) so VAT subtraction is accounted for.
    Each invoice has exactly one supplier, so invoice_count per supplier is accurate.
    Results are cached for 60 seconds to reduce DB load on dashboard tab switches.
    """
    global _summary_cache

    # Build cache key from parameters
    cache_key = f"{company}:{start_date}:{end_date}:{department}:{subdepartment}:{brand}"
    cache_entry = _summary_cache['supplier'].get(cache_key)

    # Check cache
    if cache_entry and (time.time() - cache_entry['timestamp']) < _summary_cache['ttl']:
        return cache_entry['data']

    conn = get_db()
    try:
        cursor = get_cursor(conn)

        # Use allocation values (same as other summaries) so VAT subtraction is accounted for
        # Group by supplier - each invoice has exactly one supplier
        query = '''
            SELECT
                i.supplier,
                SUM(CASE WHEN i.invoice_value > 0 AND i.value_ron IS NOT NULL
                    THEN a.allocation_value * i.value_ron / i.invoice_value
                    ELSE a.allocation_value END) as total_value_ron,
                SUM(CASE WHEN i.invoice_value > 0 AND i.value_eur IS NOT NULL
                    THEN a.allocation_value * i.value_eur / i.invoice_value
                    ELSE a.allocation_value / COALESCE(i.exchange_rate, 5.0) END) as total_value_eur,
                COUNT(DISTINCT a.invoice_id) as invoice_count,
                AVG(COALESCE(i.exchange_rate, 5.0)) as avg_exchange_rate
            FROM allocations a
            JOIN invoices i ON a.invoice_id = i.id
            WHERE i.deleted_at IS NULL
        '''
        params = []
        conditions = []

        if company:
            conditions.append('a.company = %s')
            params.append(company)
        if start_date:
            conditions.append('i.invoice_date >= %s')
            params.append(start_date)
        if end_date:
            conditions.append('i.invoice_date <= %s')
            params.append(end_date)
        if department:
            conditions.append('a.department = %s')
            params.append(department)
        if subdepartment:
            conditions.append('a.subdepartment = %s')
            params.append(subdepartment)
        if brand:
            conditions.append('a.brand = %s')
            params.append(brand)

        if conditions:
            query += ' AND ' + ' AND '.join(conditions)

        query += ' GROUP BY i.supplier ORDER BY total_value_ron DESC'

        cursor.execute(query, params)
        results = [dict_from_row(row) for row in cursor.fetchall()]

        # Cache results and enforce size limit
        _summary_cache['supplier'][cache_key] = {'data': results, 'timestamp': time.time()}
        _enforce_summary_cache_limit('supplier')

        return results
    finally:
        release_db(conn)


def delete_invoice(invoice_id: int) -> bool:
    """Soft delete an invoice (move to bin)."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('UPDATE invoices SET deleted_at = CURRENT_TIMESTAMP WHERE id = %s AND deleted_at IS NULL', (invoice_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    release_db(conn)
    if deleted:
        clear_invoices_cache()
    return deleted


def restore_invoice(invoice_id: int) -> bool:
    """Restore a soft-deleted invoice from the bin."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('UPDATE invoices SET deleted_at = NULL WHERE id = %s AND deleted_at IS NOT NULL', (invoice_id,))
    restored = cursor.rowcount > 0

    conn.commit()
    release_db(conn)
    if restored:
        clear_invoices_cache()
    return restored


def get_invoice_drive_link(invoice_id: int) -> str | None:
    """Get the drive_link for a single invoice."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('SELECT drive_link FROM invoices WHERE id = %s', (invoice_id,))
    result = cursor.fetchone()
    release_db(conn)
    return result['drive_link'] if result else None


def get_invoice_drive_links(invoice_ids: list[int]) -> list[str]:
    """Get drive_links for multiple invoices. Returns list of non-null links."""
    if not invoice_ids:
        return []

    conn = get_db()
    cursor = get_cursor(conn)
    placeholders = ','.join(['%s'] * len(invoice_ids))
    cursor.execute(f'SELECT drive_link FROM invoices WHERE id IN ({placeholders}) AND drive_link IS NOT NULL', invoice_ids)
    results = cursor.fetchall()
    release_db(conn)
    return [r['drive_link'] for r in results if r['drive_link']]


def permanently_delete_invoice(invoice_id: int) -> bool:
    """Permanently delete an invoice and its allocations."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('DELETE FROM invoices WHERE id = %s', (invoice_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    release_db(conn)
    if deleted:
        clear_invoices_cache()
    return deleted


def bulk_soft_delete_invoices(invoice_ids: list[int]) -> int:
    """Soft delete multiple invoices. Returns count of deleted invoices."""
    if not invoice_ids:
        return 0

    conn = get_db()
    cursor = get_cursor(conn)

    placeholders = ','.join(['%s'] * len(invoice_ids))
    cursor.execute(f'UPDATE invoices SET deleted_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders}) AND deleted_at IS NULL', invoice_ids)
    deleted_count = cursor.rowcount

    conn.commit()
    release_db(conn)
    if deleted_count > 0:
        clear_invoices_cache()
    return deleted_count


def bulk_restore_invoices(invoice_ids: list[int]) -> int:
    """Restore multiple soft-deleted invoices. Returns count of restored invoices."""
    if not invoice_ids:
        return 0

    conn = get_db()
    cursor = get_cursor(conn)

    placeholders = ','.join(['%s'] * len(invoice_ids))
    cursor.execute(f'UPDATE invoices SET deleted_at = NULL WHERE id IN ({placeholders}) AND deleted_at IS NOT NULL', invoice_ids)
    restored_count = cursor.rowcount

    conn.commit()
    release_db(conn)
    if restored_count > 0:
        clear_invoices_cache()
    return restored_count


def bulk_permanently_delete_invoices(invoice_ids: list[int]) -> int:
    """Permanently delete multiple invoices. Returns count of deleted invoices."""
    if not invoice_ids:
        return 0

    conn = get_db()
    cursor = get_cursor(conn)

    placeholders = ','.join(['%s'] * len(invoice_ids))
    cursor.execute(f'DELETE FROM invoices WHERE id IN ({placeholders})', invoice_ids)
    deleted_count = cursor.rowcount

    conn.commit()
    release_db(conn)
    if deleted_count > 0:
        clear_invoices_cache()
    return deleted_count


def cleanup_old_deleted_invoices(days: int = 30) -> int:
    """Permanently delete invoices that have been in the bin for more than specified days."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        DELETE FROM invoices
        WHERE deleted_at IS NOT NULL
        AND deleted_at < CURRENT_TIMESTAMP - INTERVAL '%s days'
    ''', (days,))
    deleted_count = cursor.rowcount

    conn.commit()
    release_db(conn)
    return deleted_count


def update_invoice(
    invoice_id: int,
    supplier: str = None,
    invoice_number: str = None,
    invoice_date: str = None,
    invoice_value: float = None,
    currency: str = None,
    drive_link: str = None,
    comment: str = None,
    status: str = None,
    payment_status: str = None,
    subtract_vat: bool = None,
    vat_rate: float = None,
    net_value: float = None
) -> bool:
    """Update an existing invoice."""
    conn = get_db()
    cursor = get_cursor(conn)

    # Build dynamic update query
    updates = []
    params = []

    if supplier is not None:
        updates.append('supplier = %s')
        params.append(supplier)
    if invoice_number is not None:
        updates.append('invoice_number = %s')
        params.append(invoice_number)
    if invoice_date is not None:
        updates.append('invoice_date = %s')
        params.append(invoice_date)
    if invoice_value is not None:
        updates.append('invoice_value = %s')
        params.append(invoice_value)
    if currency is not None:
        updates.append('currency = %s')
        params.append(currency)
    if drive_link is not None:
        updates.append('drive_link = %s')
        params.append(drive_link)
    if comment is not None:
        updates.append('comment = %s')
        params.append(comment)
    if status is not None:
        updates.append('status = %s')
        params.append(status)
    if payment_status is not None:
        updates.append('payment_status = %s')
        params.append(payment_status)
    if subtract_vat is not None:
        updates.append('subtract_vat = %s')
        params.append(subtract_vat)
    if vat_rate is not None:
        updates.append('vat_rate = %s')
        params.append(vat_rate)
    elif subtract_vat is False:
        # Clear vat_rate when disabling VAT subtraction
        updates.append('vat_rate = %s')
        params.append(None)
    if net_value is not None:
        updates.append('net_value = %s')
        params.append(net_value)
    elif subtract_vat is False:
        # Clear net_value when disabling VAT subtraction
        updates.append('net_value = %s')
        params.append(None)

    if not updates:
        release_db(conn)
        return False

    updates.append('updated_at = CURRENT_TIMESTAMP')
    params.append(invoice_id)

    query = f"UPDATE invoices SET {', '.join(updates)} WHERE id = %s"

    try:
        cursor.execute(query, params)
        updated = cursor.rowcount > 0
        conn.commit()
        if updated:
            clear_invoices_cache()
        return updated
    except Exception as e:
        conn.rollback()
        if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
            raise ValueError(f"Invoice number already exists in database")
        raise
    finally:
        release_db(conn)


def check_invoice_number_exists(invoice_number: str, exclude_id: int = None) -> dict:
    """Check if invoice number already exists in database.

    Args:
        invoice_number: The invoice number to check
        exclude_id: Optional invoice ID to exclude (for edit operations)

    Returns:
        dict with 'exists' (bool) and 'invoice' (existing invoice data if found)
    """
    conn = get_db()
    cursor = get_cursor(conn)

    if exclude_id:
        cursor.execute('''
            SELECT id, supplier, invoice_number, invoice_date, invoice_value, currency
            FROM invoices WHERE invoice_number = %s AND id != %s
        ''', (invoice_number, exclude_id))
    else:
        cursor.execute('''
            SELECT id, supplier, invoice_number, invoice_date, invoice_value, currency
            FROM invoices WHERE invoice_number = %s
        ''', (invoice_number,))

    row = cursor.fetchone()
    release_db(conn)

    if row:
        return {
            'exists': True,
            'invoice': dict_from_row(row)
        }
    return {'exists': False, 'invoice': None}


def search_invoices(query: str, filters: dict = None) -> list[dict]:
    """Search invoices by supplier, invoice number, or value (Elasticsearch-like).

    Splits query into words and matches ALL words against supplier OR invoice_number OR invoice_value.
    Each word can match anywhere in the fields (partial matching).
    Case-insensitive. Numeric values are matched against invoice_value.

    Args:
        query: Search text
        filters: Optional dict with filter params (company, department, subdepartment, brand,
                 status, payment_status, start_date, end_date)
    """
    conn = get_db()
    cursor = get_cursor(conn)
    filters = filters or {}

    # Split query into words and filter empty strings
    words = [w.strip() for w in query.split() if w.strip()]

    if not words:
        release_db(conn)
        return []

    # Helper to parse numeric value (handles European format: 123,45 or 123.45)
    def parse_numeric(word):
        # Remove thousands separators and normalize decimal
        cleaned = word.replace(' ', '').replace('.', '').replace(',', '.')
        try:
            return float(cleaned)
        except ValueError:
            return None

    # Build search conditions: each word must match somewhere in supplier OR invoice_number OR invoice_value
    search_conditions = []
    params = []
    for word in words:
        term = f'%{word}%'
        # Check if word looks like a number (possibly with decimal)
        numeric_val = parse_numeric(word)
        if numeric_val is not None:
            # Match against text fields OR exact/approximate value match
            search_conditions.append('(i.supplier ILIKE %s OR i.invoice_number ILIKE %s OR ABS(i.invoice_value - %s) < 0.01)')
            params.extend([term, term, numeric_val])
        else:
            search_conditions.append('(i.supplier ILIKE %s OR i.invoice_number ILIKE %s)')
            params.extend([term, term])

    # Build base query
    company = filters.get('company')
    department = filters.get('department')
    subdepartment = filters.get('subdepartment')
    brand = filters.get('brand')

    # If any allocation filter is set, join with allocations table
    if company or department or subdepartment or brand:
        base_query = '''
            SELECT DISTINCT i.*
            FROM invoices i
            JOIN allocations a ON a.invoice_id = i.id
        '''
    else:
        base_query = '''
            SELECT DISTINCT i.*
            FROM invoices i
        '''

    # Build filter conditions
    filter_conditions = ['i.deleted_at IS NULL']  # Always exclude deleted invoices

    if company:
        filter_conditions.append('a.company = %s')
        params.append(company)
    if department:
        filter_conditions.append('a.department = %s')
        params.append(department)
    if subdepartment:
        filter_conditions.append('a.subdepartment = %s')
        params.append(subdepartment)
    if brand:
        filter_conditions.append('a.brand = %s')
        params.append(brand)

    # Date filters
    start_date = filters.get('start_date')
    end_date = filters.get('end_date')
    if start_date:
        filter_conditions.append('i.invoice_date >= %s')
        params.append(start_date)
    if end_date:
        filter_conditions.append('i.invoice_date <= %s')
        params.append(end_date)

    # Status filters
    status = filters.get('status')
    payment_status = filters.get('payment_status')
    if status:
        filter_conditions.append('i.status = %s')
        params.append(status)
    if payment_status:
        filter_conditions.append('i.payment_status = %s')
        params.append(payment_status)

    # Combine search conditions with filter conditions
    # Search conditions come first (they use the initial params), filter conditions come after
    all_conditions = search_conditions + filter_conditions

    # Reorder params: search params first, then filter params
    # But we already built params in this order, so just join conditions
    where_clause = ' AND '.join(all_conditions)

    cursor.execute(f'''
        {base_query}
        WHERE {where_clause}
        ORDER BY i.created_at DESC
        LIMIT 50
    ''', params)

    results = [dict_from_row(row) for row in cursor.fetchall()]
    release_db(conn)
    return results


# ============== ALLOCATION FUNCTIONS ==============

def update_allocation(
    allocation_id: int,
    company: str = None,
    brand: str = None,
    department: str = None,
    subdepartment: str = None,
    allocation_percent: float = None,
    allocation_value: float = None,
    responsible: str = None,
    reinvoice_to: str = None,
    reinvoice_brand: str = None,
    reinvoice_department: str = None,
    reinvoice_subdepartment: str = None,
    comment: str = None
) -> bool:
    """Update an existing allocation."""
    conn = get_db()
    cursor = get_cursor(conn)

    updates = []
    params = []

    if company is not None:
        updates.append('company = %s')
        params.append(company)
    if brand is not None:
        updates.append('brand = %s')
        params.append(brand)
    if department is not None:
        updates.append('department = %s')
        params.append(department)
    if subdepartment is not None:
        updates.append('subdepartment = %s')
        params.append(subdepartment)
    if allocation_percent is not None:
        updates.append('allocation_percent = %s')
        params.append(allocation_percent)
    if allocation_value is not None:
        updates.append('allocation_value = %s')
        params.append(allocation_value)
    if responsible is not None:
        updates.append('responsible = %s')
        params.append(responsible)
    if reinvoice_to is not None:
        updates.append('reinvoice_to = %s')
        params.append(reinvoice_to)
    if reinvoice_brand is not None:
        updates.append('reinvoice_brand = %s')
        params.append(reinvoice_brand)
    if reinvoice_department is not None:
        updates.append('reinvoice_department = %s')
        params.append(reinvoice_department)
    if reinvoice_subdepartment is not None:
        updates.append('reinvoice_subdepartment = %s')
        params.append(reinvoice_subdepartment)
    if comment is not None:
        updates.append('comment = %s')
        params.append(comment)

    if not updates:
        release_db(conn)
        return False

    params.append(allocation_id)
    query = f"UPDATE allocations SET {', '.join(updates)} WHERE id = %s"
    cursor.execute(query, params)
    updated = cursor.rowcount > 0

    conn.commit()
    release_db(conn)
    return updated


def delete_allocation(allocation_id: int) -> bool:
    """Delete an allocation."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('DELETE FROM allocations WHERE id = %s', (allocation_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    release_db(conn)
    return deleted


def update_allocation_comment(allocation_id: int, comment: str) -> bool:
    """Update just the comment for an allocation."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('UPDATE allocations SET comment = %s WHERE id = %s', (comment, allocation_id))
    updated = cursor.rowcount > 0

    conn.commit()
    release_db(conn)
    return updated


def add_allocation(
    invoice_id: int,
    company: str,
    department: str,
    allocation_percent: float,
    allocation_value: float,
    brand: str = None,
    subdepartment: str = None,
    responsible: str = None,
    reinvoice_to: str = None,
    reinvoice_brand: str = None,
    reinvoice_department: str = None,
    reinvoice_subdepartment: str = None
) -> int:
    """Add a new allocation to an invoice. Returns allocation ID."""
    conn = get_db()
    cursor = get_cursor(conn)

    try:
        cursor.execute('''
            INSERT INTO allocations (invoice_id, company, brand, department, subdepartment,
                allocation_percent, allocation_value, responsible, reinvoice_to, reinvoice_brand, reinvoice_department, reinvoice_subdepartment)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (invoice_id, company, brand, department, subdepartment,
              allocation_percent, allocation_value, responsible, reinvoice_to, reinvoice_brand, reinvoice_department, reinvoice_subdepartment))
        allocation_id = cursor.fetchone()['id']

        conn.commit()
        return allocation_id
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_db(conn)


def update_invoice_allocations(invoice_id: int, allocations: list[dict]) -> bool:
    """
    Replace all allocations for an invoice with new ones.
    This is a transactional operation - either all succeed or all fail.
    allocation_value is calculated from invoice_value * (allocation_percent / 100)
    """
    conn = get_db()
    cursor = get_cursor(conn)

    try:
        # Get invoice value to calculate allocation values
        cursor.execute('SELECT invoice_value, subtract_vat, net_value FROM invoices WHERE id = %s', (invoice_id,))
        result = cursor.fetchone()
        if not result:
            raise ValueError(f"Invoice {invoice_id} not found")
        invoice_value = result['invoice_value']
        # Use net_value if VAT subtraction is enabled
        base_value = result['net_value'] if result['subtract_vat'] and result['net_value'] else invoice_value

        # Delete existing allocations
        cursor.execute('DELETE FROM allocations WHERE invoice_id = %s', (invoice_id,))

        # Insert new allocations
        for alloc in allocations:
            allocation_percent = alloc['allocation_percent']
            # Calculate value from percent if not provided (use base_value which is net_value when VAT subtraction enabled)
            allocation_value = alloc.get('allocation_value') or (base_value * allocation_percent / 100)

            cursor.execute('''
                INSERT INTO allocations (invoice_id, company, brand, department, subdepartment,
                    allocation_percent, allocation_value, responsible, reinvoice_to, reinvoice_brand, reinvoice_department, reinvoice_subdepartment, locked, comment)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                invoice_id,
                alloc['company'],
                alloc.get('brand'),
                alloc['department'],
                alloc.get('subdepartment'),
                allocation_percent,
                allocation_value,
                alloc.get('responsible'),
                alloc.get('reinvoice_to'),
                alloc.get('reinvoice_brand'),
                alloc.get('reinvoice_department'),
                alloc.get('reinvoice_subdepartment'),
                alloc.get('locked', False),
                alloc.get('comment')
            ))
            allocation_id = cursor.fetchone()['id']

            # Insert reinvoice destinations if provided
            reinvoice_dests = alloc.get('reinvoice_destinations', [])
            for rd in reinvoice_dests:
                rd_value = allocation_value * (rd['percentage'] / 100)
                cursor.execute('''
                    INSERT INTO reinvoice_destinations
                    (allocation_id, company, brand, department, subdepartment, percentage, value)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (
                    allocation_id,
                    rd['company'],
                    rd.get('brand'),
                    rd.get('department'),
                    rd.get('subdepartment'),
                    rd['percentage'],
                    rd_value
                ))

        conn.commit()
        clear_invoices_cache()  # Allocations changed
        return True
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_db(conn)


# ============== REINVOICE DESTINATIONS FUNCTIONS ==============

def get_reinvoice_destinations(allocation_id: int) -> list[dict]:
    """Get all reinvoice destinations for an allocation."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('''
        SELECT * FROM reinvoice_destinations WHERE allocation_id = %s ORDER BY id
    ''', (allocation_id,))
    results = [dict_from_row(row) for row in cursor.fetchall()]
    release_db(conn)
    return results


def save_reinvoice_destinations(allocation_id: int, destinations: list[dict], allocation_value: float = None) -> bool:
    """
    Replace all reinvoice destinations for an allocation.
    If allocation_value is provided, calculates each destination's value from its percentage.
    """
    conn = get_db()
    cursor = get_cursor(conn)
    try:
        # Delete existing destinations
        cursor.execute('DELETE FROM reinvoice_destinations WHERE allocation_id = %s', (allocation_id,))

        # Insert new destinations
        for dest in destinations:
            dest_value = None
            if allocation_value is not None and dest.get('percentage'):
                dest_value = allocation_value * (dest['percentage'] / 100)
            cursor.execute('''
                INSERT INTO reinvoice_destinations
                (allocation_id, company, brand, department, subdepartment, percentage, value)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (
                allocation_id,
                dest['company'],
                dest.get('brand'),
                dest.get('department'),
                dest.get('subdepartment'),
                dest['percentage'],
                dest_value or dest.get('value')
            ))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        release_db(conn)


def save_reinvoice_destinations_batch(allocation_destinations: list[tuple[int, list[dict], float]]) -> bool:
    """
    Save reinvoice destinations for multiple allocations in a single transaction.
    Each tuple is (allocation_id, destinations_list, allocation_value).
    """
    conn = get_db()
    cursor = get_cursor(conn)
    try:
        for allocation_id, destinations, allocation_value in allocation_destinations:
            # Delete existing destinations
            cursor.execute('DELETE FROM reinvoice_destinations WHERE allocation_id = %s', (allocation_id,))

            # Insert new destinations
            for dest in destinations:
                dest_value = allocation_value * (dest['percentage'] / 100) if allocation_value else dest.get('value')
                cursor.execute('''
                    INSERT INTO reinvoice_destinations
                    (allocation_id, company, brand, department, subdepartment, percentage, value)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (
                    allocation_id,
                    dest['company'],
                    dest.get('brand'),
                    dest.get('department'),
                    dest.get('subdepartment'),
                    dest['percentage'],
                    dest_value
                ))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        release_db(conn)


# ============== INVOICE TEMPLATE FUNCTIONS ==============

def save_invoice_template(
    name: str,
    supplier: str = None,
    supplier_vat: str = None,
    customer_vat: str = None,
    currency: str = 'RON',
    description: str = None,
    invoice_number_regex: str = None,
    invoice_date_regex: str = None,
    invoice_value_regex: str = None,
    date_format: str = '%Y-%m-%d',
    sample_invoice_path: str = None,
    template_type: str = 'fixed',
    supplier_regex: str = None,
    supplier_vat_regex: str = None,
    customer_vat_regex: str = None,
    currency_regex: str = None
) -> int:
    """Save a new invoice template. Returns the template ID."""
    conn = get_db()
    cursor = get_cursor(conn)

    try:
        cursor.execute('''
            INSERT INTO invoice_templates (
                name, template_type, supplier, supplier_vat, customer_vat, currency, description,
                invoice_number_regex, invoice_date_regex, invoice_value_regex,
                date_format, sample_invoice_path,
                supplier_regex, supplier_vat_regex, customer_vat_regex, currency_regex
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            name, template_type, supplier, supplier_vat, customer_vat, currency, description,
            invoice_number_regex, invoice_date_regex, invoice_value_regex,
            date_format, sample_invoice_path,
            supplier_regex, supplier_vat_regex, customer_vat_regex, currency_regex
        ))
        template_id = cursor.fetchone()['id']

        conn.commit()

        # Clear cache after successful insert
        clear_templates_cache()

        return template_id

    except Exception as e:
        conn.rollback()
        if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
            raise ValueError(f"Template '{name}' already exists")
        raise
    finally:
        release_db(conn)


def update_invoice_template(
    template_id: int,
    name: str = None,
    supplier: str = None,
    supplier_vat: str = None,
    customer_vat: str = None,
    currency: str = None,
    description: str = None,
    invoice_number_regex: str = None,
    invoice_date_regex: str = None,
    invoice_value_regex: str = None,
    date_format: str = None,
    sample_invoice_path: str = None,
    template_type: str = None,
    supplier_regex: str = None,
    supplier_vat_regex: str = None,
    customer_vat_regex: str = None,
    currency_regex: str = None
) -> bool:
    """Update an existing invoice template."""
    conn = get_db()
    cursor = get_cursor(conn)

    # Build dynamic update query
    updates = []
    params = []

    if name is not None:
        updates.append('name = %s')
        params.append(name)
    if template_type is not None:
        updates.append('template_type = %s')
        params.append(template_type)
    if supplier is not None:
        updates.append('supplier = %s')
        params.append(supplier)
    if supplier_vat is not None:
        updates.append('supplier_vat = %s')
        params.append(supplier_vat)
    if customer_vat is not None:
        updates.append('customer_vat = %s')
        params.append(customer_vat)
    if currency is not None:
        updates.append('currency = %s')
        params.append(currency)
    if description is not None:
        updates.append('description = %s')
        params.append(description)
    if invoice_number_regex is not None:
        updates.append('invoice_number_regex = %s')
        params.append(invoice_number_regex)
    if invoice_date_regex is not None:
        updates.append('invoice_date_regex = %s')
        params.append(invoice_date_regex)
    if invoice_value_regex is not None:
        updates.append('invoice_value_regex = %s')
        params.append(invoice_value_regex)
    if date_format is not None:
        updates.append('date_format = %s')
        params.append(date_format)
    if sample_invoice_path is not None:
        updates.append('sample_invoice_path = %s')
        params.append(sample_invoice_path)
    if supplier_regex is not None:
        updates.append('supplier_regex = %s')
        params.append(supplier_regex)
    if supplier_vat_regex is not None:
        updates.append('supplier_vat_regex = %s')
        params.append(supplier_vat_regex)
    if customer_vat_regex is not None:
        updates.append('customer_vat_regex = %s')
        params.append(customer_vat_regex)
    if currency_regex is not None:
        updates.append('currency_regex = %s')
        params.append(currency_regex)

    if not updates:
        release_db(conn)
        return False

    updates.append('updated_at = CURRENT_TIMESTAMP')
    params.append(template_id)

    query = f"UPDATE invoice_templates SET {', '.join(updates)} WHERE id = %s"
    cursor.execute(query, params)
    updated = cursor.rowcount > 0

    conn.commit()
    release_db(conn)

    # Clear cache after update
    if updated:
        clear_templates_cache()

    return updated


def delete_invoice_template(template_id: int) -> bool:
    """Delete an invoice template."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('DELETE FROM invoice_templates WHERE id = %s', (template_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    release_db(conn)

    # Clear cache after delete
    if deleted:
        clear_templates_cache()

    return deleted


def get_all_invoice_templates() -> list[dict]:
    """Get all invoice templates (with caching)."""
    global _templates_cache

    # Return cached data if valid
    if _is_cache_valid(_templates_cache):
        return _templates_cache['data']

    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('SELECT * FROM invoice_templates ORDER BY name')
    templates = [dict_from_row(row) for row in cursor.fetchall()]

    release_db(conn)

    # Cache the result
    _templates_cache['data'] = templates
    _templates_cache['timestamp'] = time.time()

    return templates


def get_invoice_template(template_id: int) -> Optional[dict]:
    """Get a specific invoice template by ID."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('SELECT * FROM invoice_templates WHERE id = %s', (template_id,))
    template = cursor.fetchone()

    release_db(conn)
    return dict_from_row(template) if template else None


def get_invoice_template_by_name(name: str) -> Optional[dict]:
    """Get a specific invoice template by name."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('SELECT * FROM invoice_templates WHERE name = %s', (name,))
    template = cursor.fetchone()

    release_db(conn)
    return dict_from_row(template) if template else None


# ============ Connector Functions ============

def get_all_connectors() -> list[dict]:
    """Get all connectors."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('SELECT * FROM connectors ORDER BY name')
    connectors = [dict_from_row(row) for row in cursor.fetchall()]

    release_db(conn)
    return connectors


def get_connector(connector_id: int) -> Optional[dict]:
    """Get a specific connector by ID."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('SELECT * FROM connectors WHERE id = %s', (connector_id,))
    connector = cursor.fetchone()

    release_db(conn)
    return dict_from_row(connector) if connector else None


def get_connector_by_type(connector_type: str) -> Optional[dict]:
    """Get a connector by type (e.g., 'google_ads', 'meta')."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('SELECT * FROM connectors WHERE connector_type = %s', (connector_type,))
    connector = cursor.fetchone()

    release_db(conn)
    return dict_from_row(connector) if connector else None


def get_connectors_by_type(connector_type: str) -> list[dict]:
    """Get all connectors of a given type (supports multi-account connectors like Google Ads)."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('SELECT * FROM connectors WHERE connector_type = %s ORDER BY name', (connector_type,))
    connectors = [dict_from_row(row) for row in cursor.fetchall()]

    release_db(conn)
    return connectors


def save_connector(
    connector_type: str,
    name: str,
    status: str = 'disconnected',
    config: dict = None,
    credentials: dict = None
) -> int:
    """Save a new connector. Returns connector ID."""
    import json
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        INSERT INTO connectors (connector_type, name, status, config, credentials)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
    ''', (
        connector_type,
        name,
        status,
        json.dumps(config or {}),
        json.dumps(credentials or {})
    ))

    connector_id = cursor.fetchone()['id']
    conn.commit()
    release_db(conn)
    return connector_id


def update_connector(
    connector_id: int,
    name: str = None,
    status: str = None,
    config: dict = None,
    credentials: dict = None,
    last_sync: datetime = None,
    last_error: str = None
) -> bool:
    """Update a connector. Returns True if updated."""
    import json
    conn = get_db()
    cursor = get_cursor(conn)

    updates = []
    params = []

    if name is not None:
        updates.append('name = %s')
        params.append(name)
    if status is not None:
        updates.append('status = %s')
        params.append(status)
    if config is not None:
        updates.append('config = %s')
        params.append(json.dumps(config))
    if credentials is not None:
        updates.append('credentials = %s')
        params.append(json.dumps(credentials))
    if last_sync is not None:
        updates.append('last_sync = %s')
        params.append(last_sync)
    if last_error is not None:
        updates.append('last_error = %s')
        params.append(last_error)

    if not updates:
        release_db(conn)
        return False

    updates.append('updated_at = CURRENT_TIMESTAMP')
    params.append(connector_id)

    query = f"UPDATE connectors SET {', '.join(updates)} WHERE id = %s"
    cursor.execute(query, params)
    updated = cursor.rowcount > 0

    conn.commit()
    release_db(conn)
    return updated


def delete_connector(connector_id: int) -> bool:
    """Delete a connector and its sync logs."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('DELETE FROM connectors WHERE id = %s', (connector_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    release_db(conn)
    return deleted


def add_connector_sync_log(
    connector_id: int,
    sync_type: str,
    status: str,
    invoices_found: int = 0,
    invoices_imported: int = 0,
    error_message: str = None,
    details: dict = None
) -> int:
    """Add a sync log entry. Returns log ID."""
    import json
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        INSERT INTO connector_sync_log
        (connector_id, sync_type, status, invoices_found, invoices_imported, error_message, details)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    ''', (
        connector_id,
        sync_type,
        status,
        invoices_found,
        invoices_imported,
        error_message,
        json.dumps(details or {})
    ))

    log_id = cursor.fetchone()['id']
    conn.commit()
    release_db(conn)
    return log_id


def get_connector_sync_logs(connector_id: int, limit: int = 20) -> list[dict]:
    """Get sync logs for a connector, most recent first."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT * FROM connector_sync_log
        WHERE connector_id = %s
        ORDER BY created_at DESC
        LIMIT %s
    ''', (connector_id, limit))

    logs = [dict_from_row(row) for row in cursor.fetchall()]
    release_db(conn)
    return logs


# ============ Role Management Functions ============

def get_all_roles() -> list[dict]:
    """Get all roles."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('SELECT * FROM roles ORDER BY name')
    roles = [dict_from_row(row) for row in cursor.fetchall()]

    release_db(conn)
    return roles


def get_role(role_id: int) -> Optional[dict]:
    """Get a specific role by ID."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('SELECT * FROM roles WHERE id = %s', (role_id,))
    role = cursor.fetchone()

    release_db(conn)
    return dict_from_row(role) if role else None


def save_role(
    name: str,
    description: str = None,
    can_add_invoices: bool = False,
    can_edit_invoices: bool = False,
    can_delete_invoices: bool = False,
    can_view_invoices: bool = False,
    can_access_accounting: bool = False,
    can_access_settings: bool = False,
    can_access_connectors: bool = False,
    can_access_templates: bool = False,
    can_access_hr: bool = False,
    is_hr_manager: bool = False
) -> int:
    """Save a new role. Returns role ID."""
    conn = get_db()
    cursor = get_cursor(conn)

    try:
        cursor.execute('''
            INSERT INTO roles (name, description, can_add_invoices, can_edit_invoices, can_delete_invoices,
                can_view_invoices, can_access_accounting, can_access_settings,
                can_access_connectors, can_access_templates, can_access_hr, is_hr_manager)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            name, description, can_add_invoices, can_edit_invoices, can_delete_invoices,
            can_view_invoices, can_access_accounting, can_access_settings,
            can_access_connectors, can_access_templates, can_access_hr, is_hr_manager
        ))

        role_id = cursor.fetchone()['id']
        conn.commit()
        return role_id

    except Exception as e:
        conn.rollback()
        if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
            raise ValueError(f"Role '{name}' already exists")
        raise
    finally:
        release_db(conn)


def update_role(
    role_id: int,
    name: str = None,
    description: str = None,
    can_add_invoices: bool = None,
    can_edit_invoices: bool = None,
    can_delete_invoices: bool = None,
    can_view_invoices: bool = None,
    can_access_accounting: bool = None,
    can_access_settings: bool = None,
    can_access_connectors: bool = None,
    can_access_templates: bool = None,
    can_access_hr: bool = None,
    is_hr_manager: bool = None
) -> bool:
    """Update a role. Returns True if updated."""
    conn = get_db()
    cursor = get_cursor(conn)

    updates = []
    params = []

    if name is not None:
        updates.append('name = %s')
        params.append(name)
    if description is not None:
        updates.append('description = %s')
        params.append(description)
    if can_add_invoices is not None:
        updates.append('can_add_invoices = %s')
        params.append(can_add_invoices)
    if can_edit_invoices is not None:
        updates.append('can_edit_invoices = %s')
        params.append(can_edit_invoices)
    if can_delete_invoices is not None:
        updates.append('can_delete_invoices = %s')
        params.append(can_delete_invoices)
    if can_view_invoices is not None:
        updates.append('can_view_invoices = %s')
        params.append(can_view_invoices)
    if can_access_accounting is not None:
        updates.append('can_access_accounting = %s')
        params.append(can_access_accounting)
    if can_access_settings is not None:
        updates.append('can_access_settings = %s')
        params.append(can_access_settings)
    if can_access_connectors is not None:
        updates.append('can_access_connectors = %s')
        params.append(can_access_connectors)
    if can_access_templates is not None:
        updates.append('can_access_templates = %s')
        params.append(can_access_templates)
    if can_access_hr is not None:
        updates.append('can_access_hr = %s')
        params.append(can_access_hr)
    if is_hr_manager is not None:
        updates.append('is_hr_manager = %s')
        params.append(is_hr_manager)

    if not updates:
        release_db(conn)
        return False

    params.append(role_id)
    query = f"UPDATE roles SET {', '.join(updates)} WHERE id = %s"

    try:
        cursor.execute(query, params)
        updated = cursor.rowcount > 0
        conn.commit()
        return updated
    except Exception as e:
        conn.rollback()
        if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
            raise ValueError(f"Role with that name already exists")
        raise
    finally:
        release_db(conn)


def delete_role(role_id: int) -> bool:
    """Delete a role. Returns False if role is in use by users."""
    conn = get_db()
    cursor = get_cursor(conn)

    # Check if role is in use
    cursor.execute('SELECT COUNT(*) as count FROM users WHERE role_id = %s', (role_id,))
    if cursor.fetchone()['count'] > 0:
        release_db(conn)
        raise ValueError("Cannot delete role that is assigned to users")

    cursor.execute('DELETE FROM roles WHERE id = %s', (role_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    release_db(conn)
    return deleted


# ============ User Management Functions ============

def get_all_users() -> list[dict]:
    """Get all users with their role information."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT u.*, r.name as role_name, r.description as role_description
        FROM users u
        LEFT JOIN roles r ON u.role_id = r.id
        ORDER BY u.name
    ''')
    users = [dict_from_row(row) for row in cursor.fetchall()]

    release_db(conn)
    return users


def get_user(user_id: int) -> Optional[dict]:
    """Get a specific user by ID with role information."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        cursor.execute('''
            SELECT u.*, r.name as role_name, r.description as role_description,
                   r.can_add_invoices, r.can_edit_invoices, r.can_delete_invoices, r.can_view_invoices,
                   r.can_access_accounting, r.can_access_settings, r.can_access_connectors,
                   r.can_access_templates, r.can_access_hr, r.is_hr_manager
            FROM users u
            LEFT JOIN roles r ON u.role_id = r.id
            WHERE u.id = %s
        ''', (user_id,))
        user = cursor.fetchone()
        return dict_from_row(user) if user else None
    finally:
        release_db(conn)


def get_user_by_email(email: str) -> Optional[dict]:
    """Get a user by email address with role information."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        cursor.execute('''
            SELECT u.*, r.name as role_name, r.description as role_description,
                   r.can_add_invoices, r.can_edit_invoices, r.can_delete_invoices, r.can_view_invoices,
                   r.can_access_accounting, r.can_access_settings, r.can_access_connectors,
                   r.can_access_templates, r.can_access_hr, r.is_hr_manager
            FROM users u
            LEFT JOIN roles r ON u.role_id = r.id
            WHERE u.email = %s
        ''', (email,))
        user = cursor.fetchone()
        return dict_from_row(user) if user else None
    finally:
        release_db(conn)


def save_user(
    name: str,
    email: str,
    phone: str = None,
    role_id: int = None,
    is_active: bool = True
) -> int:
    """Save a new user. Returns user ID."""
    conn = get_db()
    cursor = get_cursor(conn)

    try:
        cursor.execute('''
            INSERT INTO users (name, email, phone, role_id, is_active)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', (name, email, phone, role_id, is_active))

        user_id = cursor.fetchone()['id']
        conn.commit()
        return user_id

    except Exception as e:
        conn.rollback()
        if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
            raise ValueError(f"User with email '{email}' already exists")
        raise
    finally:
        release_db(conn)


def update_user(
    user_id: int,
    name: str = None,
    email: str = None,
    phone: str = None,
    role_id: int = None,
    is_active: bool = None
) -> bool:
    """Update a user. Returns True if updated."""
    conn = get_db()
    cursor = get_cursor(conn)

    updates = []
    params = []

    if name is not None:
        updates.append('name = %s')
        params.append(name)
    if email is not None:
        updates.append('email = %s')
        params.append(email)
    if phone is not None:
        updates.append('phone = %s')
        params.append(phone)
    if role_id is not None:
        updates.append('role_id = %s')
        params.append(role_id)
    if is_active is not None:
        updates.append('is_active = %s')
        params.append(is_active)

    if not updates:
        release_db(conn)
        return False

    updates.append('updated_at = CURRENT_TIMESTAMP')
    params.append(user_id)

    query = f"UPDATE users SET {', '.join(updates)} WHERE id = %s"

    try:
        cursor.execute(query, params)
        updated = cursor.rowcount > 0
        conn.commit()
        return updated
    except Exception as e:
        conn.rollback()
        if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
            raise ValueError(f"User with that email already exists")
        raise
    finally:
        release_db(conn)


def delete_user(user_id: int) -> bool:
    """Delete a user."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    release_db(conn)
    return deleted


# ============== Responsables CRUD ==============

def get_all_responsables() -> list[dict]:
    """Get all responsables (with caching)."""
    global _responsables_cache

    # Return cached data if valid
    if _is_cache_valid(_responsables_cache):
        return _responsables_cache['data']

    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT * FROM responsables
        ORDER BY name
    ''')

    results = [dict_from_row(row) for row in cursor.fetchall()]
    release_db(conn)

    # Cache the result
    _responsables_cache['data'] = results
    _responsables_cache['timestamp'] = time.time()

    return results


def get_responsable(responsable_id: int) -> Optional[dict]:
    """Get a specific responsable by ID."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('SELECT * FROM responsables WHERE id = %s', (responsable_id,))
    row = cursor.fetchone()

    release_db(conn)
    return dict_from_row(row) if row else None


def get_responsables_by_department(department: str) -> list[dict]:
    """Get responsables assigned to a specific department (exact match)."""
    conn = get_db()
    cursor = get_cursor(conn)

    # Use exact match instead of LIKE to avoid partial matches
    # e.g., "Marketing" should only match responsables with departments = "Marketing"
    # not "Marketing Aftersales" or "Director Marketing"
    cursor.execute('''
        SELECT * FROM responsables
        WHERE departments = %s AND is_active = TRUE AND notify_on_allocation = TRUE
    ''', (department,))

    results = [dict_from_row(row) for row in cursor.fetchall()]
    release_db(conn)
    return results


def save_responsable(name: str, email: str, phone: str = None, departments: str = None,
                     subdepartment: str = None, company: str = None, brand: str = None,
                     notify_on_allocation: bool = True, is_active: bool = True) -> int:
    """Create a new responsable."""
    conn = get_db()
    cursor = get_cursor(conn)

    try:
        cursor.execute('''
            INSERT INTO responsables (name, email, phone, departments, subdepartment, company, brand, notify_on_allocation, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (name, email, phone, departments, subdepartment, company, brand, notify_on_allocation, is_active))

        responsable_id = cursor.fetchone()['id']
        conn.commit()
        clear_responsables_cache()
        return responsable_id
    except Exception as e:
        conn.rollback()
        if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
            raise ValueError(f"Responsable with email '{email}' already exists")
        raise
    finally:
        release_db(conn)


def update_responsable(responsable_id: int, name: str = None, email: str = None, phone: str = None,
                       departments: str = None, subdepartment: str = None, company: str = None,
                       brand: str = None, notify_on_allocation: bool = None, is_active: bool = None) -> bool:
    """Update a responsable."""
    conn = get_db()
    cursor = get_cursor(conn)

    updates = []
    params = []

    if name is not None:
        updates.append('name = %s')
        params.append(name)
    if email is not None:
        updates.append('email = %s')
        params.append(email)
    if phone is not None:
        updates.append('phone = %s')
        params.append(phone)
    if departments is not None:
        updates.append('departments = %s')
        params.append(departments)
    if subdepartment is not None:
        updates.append('subdepartment = %s')
        params.append(subdepartment)
    if company is not None:
        updates.append('company = %s')
        params.append(company)
    if brand is not None:
        updates.append('brand = %s')
        params.append(brand)
    if notify_on_allocation is not None:
        updates.append('notify_on_allocation = %s')
        params.append(notify_on_allocation)
    if is_active is not None:
        updates.append('is_active = %s')
        params.append(is_active)

    if not updates:
        release_db(conn)
        return False

    updates.append('updated_at = CURRENT_TIMESTAMP')
    params.append(responsable_id)

    query = f"UPDATE responsables SET {', '.join(updates)} WHERE id = %s"

    try:
        cursor.execute(query, params)
        updated = cursor.rowcount > 0
        conn.commit()
        if updated:
            clear_responsables_cache()
        return updated
    except Exception as e:
        conn.rollback()
        if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
            raise ValueError(f"Responsable with that email already exists")
        raise
    finally:
        release_db(conn)


def delete_responsable(responsable_id: int) -> bool:
    """Delete a responsable."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('DELETE FROM responsables WHERE id = %s', (responsable_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    release_db(conn)
    if deleted:
        clear_responsables_cache()
    return deleted


# ============== Notification Settings CRUD ==============

def get_notification_settings() -> dict:
    """Get all notification settings as a dictionary."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('SELECT setting_key, setting_value FROM notification_settings')
    rows = cursor.fetchall()

    settings = {}
    for row in rows:
        settings[row['setting_key']] = row['setting_value']

    release_db(conn)
    return settings


def save_notification_setting(key: str, value: str) -> bool:
    """Save or update a notification setting."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        INSERT INTO notification_settings (setting_key, setting_value)
        VALUES (%s, %s)
        ON CONFLICT (setting_key)
        DO UPDATE SET setting_value = %s, updated_at = CURRENT_TIMESTAMP
    ''', (key, value, value))

    conn.commit()
    release_db(conn)
    return True


def save_notification_settings_bulk(settings: dict) -> bool:
    """Save multiple notification settings at once."""
    conn = get_db()
    cursor = get_cursor(conn)

    for key, value in settings.items():
        cursor.execute('''
            INSERT INTO notification_settings (setting_key, setting_value)
            VALUES (%s, %s)
            ON CONFLICT (setting_key)
            DO UPDATE SET setting_value = %s, updated_at = CURRENT_TIMESTAMP
        ''', (key, value, value))

    conn.commit()
    release_db(conn)
    return True


# ============== Theme Settings CRUD ==============

def get_active_theme() -> dict:
    """Get the active theme settings."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT id, theme_name, settings, is_active, created_at, updated_at
        FROM theme_settings
        WHERE is_active = TRUE
        ORDER BY id
        LIMIT 1
    ''')

    row = cursor.fetchone()
    release_db(conn)

    if row:
        return {
            'id': row['id'],
            'theme_name': row['theme_name'],
            'settings': row['settings'] if isinstance(row['settings'], dict) else json.loads(row['settings'] or '{}'),
            'is_active': row['is_active'],
            'created_at': row['created_at'].isoformat() if row['created_at'] else None,
            'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None
        }
    return None


def get_all_themes() -> list:
    """Get all themes."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT id, theme_name, settings, is_active, created_at, updated_at
        FROM theme_settings
        ORDER BY is_active DESC, theme_name
    ''')

    themes = []
    for row in cursor.fetchall():
        themes.append({
            'id': row['id'],
            'theme_name': row['theme_name'],
            'settings': row['settings'] if isinstance(row['settings'], dict) else json.loads(row['settings'] or '{}'),
            'is_active': row['is_active'],
            'created_at': row['created_at'].isoformat() if row['created_at'] else None,
            'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None
        })

    release_db(conn)
    return themes


def get_theme_by_id(theme_id: int) -> dict:
    """Get a theme by ID."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT id, theme_name, settings, is_active, created_at, updated_at
        FROM theme_settings
        WHERE id = %s
    ''', (theme_id,))

    row = cursor.fetchone()
    release_db(conn)

    if row:
        return {
            'id': row['id'],
            'theme_name': row['theme_name'],
            'settings': row['settings'] if isinstance(row['settings'], dict) else json.loads(row['settings'] or '{}'),
            'is_active': row['is_active'],
            'created_at': row['created_at'].isoformat() if row['created_at'] else None,
            'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None
        }
    return None


def save_theme(theme_id: int, theme_name: str, settings: dict, is_active: bool = None) -> dict:
    """Save or update a theme. If is_active=True, deactivate other themes."""
    conn = get_db()
    cursor = get_cursor(conn)

    settings_json = json.dumps(settings)

    if theme_id:
        # Update existing theme
        if is_active:
            # Deactivate all other themes first
            cursor.execute('UPDATE theme_settings SET is_active = FALSE WHERE id != %s', (theme_id,))

        cursor.execute('''
            UPDATE theme_settings
            SET theme_name = %s, settings = %s, is_active = COALESCE(%s, is_active), updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id
        ''', (theme_name, settings_json, is_active, theme_id))
    else:
        # Create new theme
        if is_active:
            cursor.execute('UPDATE theme_settings SET is_active = FALSE')

        cursor.execute('''
            INSERT INTO theme_settings (theme_name, settings, is_active)
            VALUES (%s, %s, %s)
            RETURNING id
        ''', (theme_name, settings_json, is_active or False))

    result = cursor.fetchone()
    conn.commit()
    release_db(conn)

    return get_theme_by_id(result['id']) if result else None


def delete_theme(theme_id: int) -> bool:
    """Delete a theme. Cannot delete if it's the only theme or if it's active."""
    conn = get_db()
    cursor = get_cursor(conn)

    # Check if this is the only theme
    cursor.execute('SELECT COUNT(*) as cnt FROM theme_settings')
    if cursor.fetchone()['cnt'] <= 1:
        release_db(conn)
        return False

    # Check if theme is active
    cursor.execute('SELECT is_active FROM theme_settings WHERE id = %s', (theme_id,))
    row = cursor.fetchone()
    if row and row['is_active']:
        release_db(conn)
        return False

    cursor.execute('DELETE FROM theme_settings WHERE id = %s', (theme_id,))
    conn.commit()
    release_db(conn)
    return True


def activate_theme(theme_id: int) -> bool:
    """Activate a theme and deactivate all others."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('UPDATE theme_settings SET is_active = FALSE')
    cursor.execute('UPDATE theme_settings SET is_active = TRUE, updated_at = CURRENT_TIMESTAMP WHERE id = %s', (theme_id,))

    conn.commit()
    release_db(conn)
    return True


# ============== Module Menu CRUD ==============

# In-memory cache for module menu items
_module_menu_cache = {
    'data': None,
    'timestamp': 0,
    'ttl': 300  # 5 minutes TTL
}


def clear_module_menu_cache():
    """Clear the module menu cache. Call this after menu updates."""
    global _module_menu_cache
    with _cache_lock:
        _module_menu_cache = {'data': None, 'timestamp': 0, 'ttl': 300}
    logger.debug('Module menu cache cleared')


def get_module_menu_items(include_hidden: bool = False) -> list:
    """Get all module menu items organized hierarchically.

    Returns a list of parent modules with their children nested.
    """
    global _module_menu_cache

    # Check cache first (only for non-admin requests)
    if not include_hidden:
        with _cache_lock:
            if _module_menu_cache['data'] is not None and \
               (time.time() - _module_menu_cache['timestamp']) < _module_menu_cache['ttl']:
                return _module_menu_cache['data']

    conn = get_db()
    cursor = get_cursor(conn)

    # Build status filter
    if include_hidden:
        status_filter = ""
    else:
        status_filter = "WHERE status != 'hidden'"

    cursor.execute(f'''
        SELECT id, parent_id, module_key, name, description, icon, url, color, status, sort_order
        FROM module_menu_items
        {status_filter}
        ORDER BY sort_order, name
    ''')

    rows = cursor.fetchall()
    release_db(conn)

    # Build hierarchical structure
    items_by_id = {}
    parent_items = []

    for row in rows:
        item = {
            'id': row['id'],
            'parent_id': row['parent_id'],
            'module_key': row['module_key'],
            'name': row['name'],
            'description': row['description'],
            'icon': row['icon'],
            'url': row['url'],
            'color': row['color'],
            'status': row['status'],
            'sort_order': row['sort_order'],
            'children': []
        }
        items_by_id[row['id']] = item

        if row['parent_id'] is None:
            parent_items.append(item)

    # Attach children to parents
    for row in rows:
        if row['parent_id'] is not None and row['parent_id'] in items_by_id:
            items_by_id[row['parent_id']]['children'].append(items_by_id[row['id']])

    # Sort children by sort_order
    for item in parent_items:
        item['children'].sort(key=lambda x: (x['sort_order'], x['name']))

    # Cache the result (only for non-admin requests)
    if not include_hidden:
        with _cache_lock:
            _module_menu_cache['data'] = parent_items
            _module_menu_cache['timestamp'] = time.time()

    return parent_items


def get_all_module_menu_items_flat() -> list:
    """Get all module menu items as a flat list (for admin UI)."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT id, parent_id, module_key, name, description, icon, url, color, status, sort_order,
               created_at, updated_at
        FROM module_menu_items
        ORDER BY parent_id NULLS FIRST, sort_order, name
    ''')

    items = []
    for row in cursor.fetchall():
        items.append({
            'id': row['id'],
            'parent_id': row['parent_id'],
            'module_key': row['module_key'],
            'name': row['name'],
            'description': row['description'],
            'icon': row['icon'],
            'url': row['url'],
            'color': row['color'],
            'status': row['status'],
            'sort_order': row['sort_order'],
            'created_at': row['created_at'].isoformat() if row['created_at'] else None,
            'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None
        })

    release_db(conn)
    return items


def get_module_menu_item_by_id(item_id: int) -> dict:
    """Get a single module menu item by ID."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT id, parent_id, module_key, name, description, icon, url, color, status, sort_order,
               created_at, updated_at
        FROM module_menu_items
        WHERE id = %s
    ''', (item_id,))

    row = cursor.fetchone()
    release_db(conn)

    if row:
        return {
            'id': row['id'],
            'parent_id': row['parent_id'],
            'module_key': row['module_key'],
            'name': row['name'],
            'description': row['description'],
            'icon': row['icon'],
            'url': row['url'],
            'color': row['color'],
            'status': row['status'],
            'sort_order': row['sort_order'],
            'created_at': row['created_at'].isoformat() if row['created_at'] else None,
            'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None
        }
    return None


def save_module_menu_item(item_id: int, data: dict) -> dict:
    """Create or update a module menu item."""
    conn = get_db()
    cursor = get_cursor(conn)

    if item_id:
        # Update existing item
        cursor.execute('''
            UPDATE module_menu_items
            SET parent_id = %s, module_key = %s, name = %s, description = %s,
                icon = %s, url = %s, color = %s, status = %s, sort_order = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id
        ''', (
            data.get('parent_id'),
            data.get('module_key'),
            data.get('name'),
            data.get('description'),
            data.get('icon', 'bi-grid'),
            data.get('url'),
            data.get('color', '#6c757d'),
            data.get('status', 'active'),
            data.get('sort_order', 0),
            item_id
        ))
    else:
        # Create new item
        cursor.execute('''
            INSERT INTO module_menu_items (parent_id, module_key, name, description, icon, url, color, status, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            data.get('parent_id'),
            data.get('module_key'),
            data.get('name'),
            data.get('description'),
            data.get('icon', 'bi-grid'),
            data.get('url'),
            data.get('color', '#6c757d'),
            data.get('status', 'active'),
            data.get('sort_order', 0)
        ))

    result = cursor.fetchone()
    conn.commit()
    release_db(conn)

    # Clear cache
    clear_module_menu_cache()

    return get_module_menu_item_by_id(result['id']) if result else None


def delete_module_menu_item(item_id: int) -> bool:
    """Delete a module menu item and all its children (cascades)."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('DELETE FROM module_menu_items WHERE id = %s', (item_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    release_db(conn)

    # Clear cache
    if deleted:
        clear_module_menu_cache()

    return deleted


def update_module_menu_order(items: list) -> bool:
    """Update the sort order of multiple menu items at once.

    Args:
        items: List of dicts with 'id' and 'sort_order' keys
    """
    conn = get_db()
    cursor = get_cursor(conn)

    for item in items:
        cursor.execute('''
            UPDATE module_menu_items
            SET sort_order = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (item['sort_order'], item['id']))

    conn.commit()
    release_db(conn)

    # Clear cache
    clear_module_menu_cache()

    return True


# ============== Notification Log CRUD ==============

def log_notification(responsable_id: int, invoice_id: int, notification_type: str,
                     subject: str, message: str, status: str = 'pending') -> int:
    """Log a notification."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        INSERT INTO notification_log (responsable_id, invoice_id, notification_type, subject, message, status)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    ''', (responsable_id, invoice_id, notification_type, subject, message, status))

    log_id = cursor.fetchone()['id']
    conn.commit()
    release_db(conn)
    return log_id


def update_notification_status(log_id: int, status: str, error_message: str = None) -> bool:
    """Update notification log status."""
    conn = get_db()
    cursor = get_cursor(conn)

    if status == 'sent':
        cursor.execute('''
            UPDATE notification_log
            SET status = %s, sent_at = CURRENT_TIMESTAMP, error_message = %s
            WHERE id = %s
        ''', (status, error_message, log_id))
    else:
        cursor.execute('''
            UPDATE notification_log
            SET status = %s, error_message = %s
            WHERE id = %s
        ''', (status, error_message, log_id))

    updated = cursor.rowcount > 0
    conn.commit()
    release_db(conn)
    return updated


def get_notification_logs(limit: int = 100) -> list[dict]:
    """Get recent notification logs."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT nl.*, r.name as responsable_name, r.email as responsable_email,
               i.invoice_number, i.supplier
        FROM notification_log nl
        LEFT JOIN responsables r ON nl.responsable_id = r.id
        LEFT JOIN invoices i ON nl.invoice_id = i.id
        ORDER BY nl.created_at DESC
        LIMIT %s
    ''', (limit,))

    results = [dict_from_row(row) for row in cursor.fetchall()]
    release_db(conn)
    return results


# ============== Companies CRUD ==============

def get_all_companies() -> list[dict]:
    """Get all companies (with caching)."""
    global _companies_vat_cache

    # Return cached data if valid
    if _is_cache_valid(_companies_vat_cache):
        return _companies_vat_cache['data']

    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT * FROM companies
        ORDER BY company
    ''')

    results = [dict_from_row(row) for row in cursor.fetchall()]
    release_db(conn)

    # Cache the result
    _companies_vat_cache['data'] = results
    _companies_vat_cache['timestamp'] = time.time()

    return results


def get_company(company_id: int) -> Optional[dict]:
    """Get a specific company by ID."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('SELECT * FROM companies WHERE id = %s', (company_id,))
    row = cursor.fetchone()

    release_db(conn)
    return dict_from_row(row) if row else None


def save_company(company: str, vat: str = None) -> int:
    """Create a new company."""
    conn = get_db()
    cursor = get_cursor(conn)

    try:
        cursor.execute('''
            INSERT INTO companies (company, vat)
            VALUES (%s, %s)
            RETURNING id
        ''', (company, vat))

        company_id = cursor.fetchone()['id']
        conn.commit()
        clear_companies_vat_cache()
        return company_id
    except Exception as e:
        conn.rollback()
        if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
            raise ValueError(f"Company '{company}' already exists")
        raise
    finally:
        release_db(conn)


def update_company(company_id: int, company: str = None, vat: str = None) -> bool:
    """Update a company."""
    conn = get_db()
    cursor = get_cursor(conn)

    updates = []
    params = []

    if company is not None:
        updates.append('company = %s')
        params.append(company)
    if vat is not None:
        updates.append('vat = %s')
        params.append(vat)

    if not updates:
        release_db(conn)
        return False

    params.append(company_id)

    try:
        cursor.execute(f'''
            UPDATE companies
            SET {', '.join(updates)}
            WHERE id = %s
        ''', params)

        updated = cursor.rowcount > 0
        conn.commit()
        if updated:
            clear_companies_vat_cache()
        return updated
    except Exception as e:
        conn.rollback()
        if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
            raise ValueError(f"Company name '{company}' already exists")
        raise
    finally:
        release_db(conn)


def delete_company(company_id: int) -> bool:
    """Delete a company."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('DELETE FROM companies WHERE id = %s', (company_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    release_db(conn)
    if deleted:
        clear_companies_vat_cache()
    return deleted


# ============== VAT Rates CRUD ==============

def get_vat_rates(active_only: bool = False) -> list[dict]:
    """Get all VAT rates, optionally filtering for active only."""
    conn = get_db()
    cursor = get_cursor(conn)

    if active_only:
        cursor.execute('''
            SELECT id, name, rate, is_default, is_active, created_at
            FROM vat_rates
            WHERE is_active = TRUE
            ORDER BY rate DESC
        ''')
    else:
        cursor.execute('''
            SELECT id, name, rate, is_default, is_active, created_at
            FROM vat_rates
            ORDER BY rate DESC
        ''')

    results = [dict_from_row(row) for row in cursor.fetchall()]
    release_db(conn)
    return results


def add_vat_rate(name: str, rate: float, is_default: bool = False, is_active: bool = True) -> int:
    """Add a new VAT rate. Returns the new rate ID."""
    conn = get_db()
    cursor = get_cursor(conn)

    try:
        # If setting as default, clear other defaults first
        if is_default:
            cursor.execute('UPDATE vat_rates SET is_default = FALSE WHERE is_default = TRUE')

        cursor.execute('''
            INSERT INTO vat_rates (name, rate, is_default, is_active)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        ''', (name, rate, is_default, is_active))

        rate_id = cursor.fetchone()[0]
        conn.commit()
        return rate_id
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_db(conn)


def update_vat_rate(rate_id: int, name: str = None, rate: float = None,
                   is_default: bool = None, is_active: bool = None) -> bool:
    """Update a VAT rate."""
    conn = get_db()
    cursor = get_cursor(conn)

    updates = []
    params = []

    if name is not None:
        updates.append('name = %s')
        params.append(name)
    if rate is not None:
        updates.append('rate = %s')
        params.append(rate)
    if is_default is not None:
        updates.append('is_default = %s')
        params.append(is_default)
    if is_active is not None:
        updates.append('is_active = %s')
        params.append(is_active)

    if not updates:
        release_db(conn)
        return False

    params.append(rate_id)

    try:
        # If setting as default, clear other defaults first
        if is_default:
            cursor.execute('UPDATE vat_rates SET is_default = FALSE WHERE is_default = TRUE')

        cursor.execute(f'''
            UPDATE vat_rates
            SET {', '.join(updates)}
            WHERE id = %s
        ''', params)

        updated = cursor.rowcount > 0
        conn.commit()
        return updated
    except Exception as e:
        conn.rollback()
        raise
    finally:
        release_db(conn)


def delete_vat_rate(rate_id: int) -> bool:
    """Delete a VAT rate."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('DELETE FROM vat_rates WHERE id = %s', (rate_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    release_db(conn)
    return deleted


# ============== Dropdown Options CRUD ==============

def get_dropdown_options(dropdown_type: str = None, active_only: bool = False) -> list[dict]:
    """Get dropdown options, optionally filtered by type and active status."""
    conn = get_db()
    cursor = get_cursor(conn)

    query = 'SELECT * FROM dropdown_options WHERE 1=1'
    params = []

    if dropdown_type:
        query += ' AND dropdown_type = %s'
        params.append(dropdown_type)

    if active_only:
        query += ' AND is_active = TRUE'

    query += ' ORDER BY dropdown_type, sort_order, label'

    cursor.execute(query, params)
    results = [dict_from_row(row) for row in cursor.fetchall()]
    release_db(conn)
    return results


def get_dropdown_option(option_id: int) -> Optional[dict]:
    """Get a specific dropdown option by ID."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('SELECT * FROM dropdown_options WHERE id = %s', (option_id,))
    result = cursor.fetchone()
    release_db(conn)
    return dict_from_row(result) if result else None


def add_dropdown_option(dropdown_type: str, value: str, label: str,
                        color: str = None, opacity: float = 0.7, sort_order: int = 0, is_active: bool = True) -> int:
    """Add a new dropdown option. Returns the new option ID."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        INSERT INTO dropdown_options (dropdown_type, value, label, color, opacity, sort_order, is_active)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    ''', (dropdown_type, value, label, color, opacity, sort_order, is_active))

    option_id = cursor.fetchone()['id']
    conn.commit()
    release_db(conn)
    return option_id


def update_dropdown_option(option_id: int, value: str = None, label: str = None,
                           color: str = None, opacity: float = None, sort_order: int = None, is_active: bool = None) -> bool:
    """Update a dropdown option. Returns True if updated."""
    conn = get_db()
    cursor = get_cursor(conn)

    updates = []
    params = []

    if value is not None:
        updates.append('value = %s')
        params.append(value)
    if label is not None:
        updates.append('label = %s')
        params.append(label)
    if color is not None:
        updates.append('color = %s')
        params.append(color)
    if opacity is not None:
        updates.append('opacity = %s')
        params.append(opacity)
    if sort_order is not None:
        updates.append('sort_order = %s')
        params.append(sort_order)
    if is_active is not None:
        updates.append('is_active = %s')
        params.append(is_active)

    if not updates:
        release_db(conn)
        return False

    params.append(option_id)
    query = f"UPDATE dropdown_options SET {', '.join(updates)} WHERE id = %s"

    cursor.execute(query, params)
    updated = cursor.rowcount > 0

    conn.commit()
    release_db(conn)
    return updated


def delete_dropdown_option(option_id: int) -> bool:
    """Delete a dropdown option."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('DELETE FROM dropdown_options WHERE id = %s', (option_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    release_db(conn)
    return deleted


# ============== Department Structure CRUD ==============

def get_all_department_structures() -> list[dict]:
    """Get all department structures with responsable info."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT ds.*, r.name as responsable_name, r.email as responsable_email
        FROM department_structure ds
        LEFT JOIN responsables r ON ds.responsable_id = r.id
        ORDER BY ds.company, ds.brand, ds.department, ds.subdepartment
    ''')

    results = [dict_from_row(row) for row in cursor.fetchall()]
    release_db(conn)
    return results


def get_department_structure(structure_id: int) -> Optional[dict]:
    """Get a specific department structure by ID."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT ds.*, r.name as responsable_name, r.email as responsable_email
        FROM department_structure ds
        LEFT JOIN responsables r ON ds.responsable_id = r.id
        WHERE ds.id = %s
    ''', (structure_id,))
    row = cursor.fetchone()

    release_db(conn)
    return dict_from_row(row) if row else None


def save_department_structure(company: str, department: str, brand: str = None,
                               subdepartment: str = None, manager: str = None,
                               marketing: str = None, responsable_id: int = None,
                               manager_ids: list = None, marketing_ids: list = None,
                               cc_email: str = None) -> int:
    """Create a new department structure entry."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        INSERT INTO department_structure (company, brand, department, subdepartment, manager, marketing, responsable_id, manager_ids, marketing_ids, cc_email)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    ''', (company, brand, department, subdepartment, manager, marketing, responsable_id, manager_ids, marketing_ids, cc_email))

    structure_id = cursor.fetchone()['id']
    conn.commit()
    release_db(conn)
    return structure_id


def update_department_structure(structure_id: int, company: str = None, department: str = None,
                                 brand: str = None, subdepartment: str = None, manager: str = None,
                                 marketing: str = None, responsable_id: int = None,
                                 manager_ids: list = None, marketing_ids: list = None,
                                 cc_email: str = None) -> bool:
    """Update a department structure entry."""
    conn = get_db()
    cursor = get_cursor(conn)

    updates = []
    params = []

    if company is not None:
        updates.append('company = %s')
        params.append(company)
    if department is not None:
        updates.append('department = %s')
        params.append(department)
    if brand is not None:
        updates.append('brand = %s')
        params.append(brand)
    if subdepartment is not None:
        updates.append('subdepartment = %s')
        params.append(subdepartment)
    if manager is not None:
        updates.append('manager = %s')
        params.append(manager)
    if marketing is not None:
        updates.append('marketing = %s')
        params.append(marketing)
    if responsable_id is not None:
        updates.append('responsable_id = %s')
        params.append(responsable_id if responsable_id != 0 else None)
    if manager_ids is not None:
        updates.append('manager_ids = %s')
        params.append(manager_ids if manager_ids else None)
    if marketing_ids is not None:
        updates.append('marketing_ids = %s')
        params.append(marketing_ids if marketing_ids else None)
    if cc_email is not None:
        updates.append('cc_email = %s')
        params.append(cc_email if cc_email else None)

    if not updates:
        release_db(conn)
        return False

    params.append(structure_id)

    cursor.execute(f'''
        UPDATE department_structure
        SET {', '.join(updates)}
        WHERE id = %s
    ''', params)

    updated = cursor.rowcount > 0
    conn.commit()
    release_db(conn)
    return updated


def delete_department_structure(structure_id: int) -> bool:
    """Delete a department structure entry."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('DELETE FROM department_structure WHERE id = %s', (structure_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    release_db(conn)
    return deleted


def get_department_cc_email(company: str, department: str) -> Optional[str]:
    """Get the CC email for a specific department in a company."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT cc_email FROM department_structure
        WHERE company = %s AND department = %s AND cc_email IS NOT NULL AND cc_email != ''
        LIMIT 1
    ''', (company, department))

    row = cursor.fetchone()
    release_db(conn)
    return row['cc_email'] if row else None


def get_unique_departments() -> list[str]:
    """Get unique department names."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT DISTINCT department FROM department_structure
        WHERE department IS NOT NULL
        ORDER BY department
    ''')

    results = [row['department'] for row in cursor.fetchall()]
    release_db(conn)
    return results


def get_unique_brands() -> list[str]:
    """Get unique brand names."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT DISTINCT brand FROM department_structure
        WHERE brand IS NOT NULL AND brand != ''
        ORDER BY brand
    ''')

    results = [row['brand'] for row in cursor.fetchall()]
    release_db(conn)
    return results


# ============== Authentication Functions ==============

def authenticate_user(email: str, password: str) -> Optional[dict]:
    """Authenticate a user by email and password.

    Returns user dict with role info if successful, None if authentication fails.
    """
    user = get_user_by_email(email)

    if not user:
        return None

    if not user.get('is_active', False):
        return None

    if not user.get('password_hash'):
        return None

    if not check_password_hash(user['password_hash'], password):
        return None

    return user


def set_user_password(user_id: int, password: str) -> bool:
    """Set password for a user."""
    conn = get_db()
    cursor = get_cursor(conn)

    password_hash = generate_password_hash(password)

    cursor.execute('''
        UPDATE users SET password_hash = %s, updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
    ''', (password_hash, user_id))

    updated = cursor.rowcount > 0
    conn.commit()
    release_db(conn)
    return updated


def update_user_last_login(user_id: int) -> bool:
    """Update the last login timestamp for a user."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        UPDATE users SET last_login = CURRENT_TIMESTAMP
        WHERE id = %s
    ''', (user_id,))

    updated = cursor.rowcount > 0
    conn.commit()
    release_db(conn)
    return updated


def update_user_last_seen(user_id: int) -> bool:
    """Update the last seen timestamp for a user (called on activity/heartbeat)."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        UPDATE users SET last_seen = CURRENT_TIMESTAMP
        WHERE id = %s
    ''', (user_id,))

    updated = cursor.rowcount > 0
    conn.commit()
    release_db(conn)
    return updated


def get_online_users_count(minutes: int = 5) -> dict:
    """Get count of users who have been active in the last N minutes.

    Returns dict with:
        - count: number of online users
        - users: list of online user names (for display)
    """
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT id, name, email, last_seen
        FROM users
        WHERE last_seen IS NOT NULL
          AND last_seen > CURRENT_TIMESTAMP - INTERVAL '%s minutes'
        ORDER BY last_seen DESC
    ''', (minutes,))

    rows = cursor.fetchall()
    release_db(conn)

    users = [{'id': row['id'], 'name': row['name'], 'email': row['email']} for row in rows]

    return {
        'count': len(users),
        'users': users
    }


def set_default_password_for_users(default_password: str = 'changeme123') -> int:
    """Set default password for all users without a password. Returns count updated."""
    conn = get_db()
    cursor = get_cursor(conn)

    password_hash = generate_password_hash(default_password)

    cursor.execute('''
        UPDATE users SET password_hash = %s, updated_at = CURRENT_TIMESTAMP
        WHERE password_hash IS NULL OR password_hash = ''
    ''', (password_hash,))

    updated_count = cursor.rowcount
    conn.commit()
    release_db(conn)
    return updated_count


# ============== User Event/Audit Log Functions ==============

def log_user_event(
    event_type: str,
    event_description: str = None,
    user_id: int = None,
    user_email: str = None,
    entity_type: str = None,
    entity_id: int = None,
    ip_address: str = None,
    user_agent: str = None,
    details: dict = None
) -> int:
    """Log a user event/action for audit purposes. Returns event ID."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        INSERT INTO user_events
        (user_id, user_email, event_type, event_description, entity_type, entity_id,
         ip_address, user_agent, details)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    ''', (
        user_id,
        user_email,
        event_type,
        event_description,
        entity_type,
        entity_id,
        ip_address,
        user_agent,
        json.dumps(details or {})
    ))

    event_id = cursor.fetchone()['id']
    conn.commit()
    release_db(conn)
    return event_id


def get_user_events(
    limit: int = 100,
    offset: int = 0,
    user_id: int = None,
    event_type: str = None,
    entity_type: str = None,
    start_date: str = None,
    end_date: str = None
) -> list[dict]:
    """Get user events with optional filtering."""
    conn = get_db()
    cursor = get_cursor(conn)

    query = '''
        SELECT ue.*, u.name as user_name
        FROM user_events ue
        LEFT JOIN users u ON ue.user_id = u.id
    '''
    params = []
    conditions = []

    if user_id:
        conditions.append('ue.user_id = %s')
        params.append(user_id)
    if event_type:
        conditions.append('ue.event_type = %s')
        params.append(event_type)
    if entity_type:
        conditions.append('ue.entity_type = %s')
        params.append(entity_type)
    if start_date:
        conditions.append('ue.created_at >= %s')
        params.append(start_date)
    if end_date:
        conditions.append('ue.created_at <= %s')
        params.append(end_date)

    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)

    query += ' ORDER BY ue.created_at DESC LIMIT %s OFFSET %s'
    params.extend([limit, offset])

    cursor.execute(query, params)
    results = [dict_from_row(row) for row in cursor.fetchall()]
    release_db(conn)
    return results


def get_event_types() -> list[str]:
    """Get distinct event types for filtering."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT DISTINCT event_type FROM user_events
        ORDER BY event_type
    ''')

    results = [row['event_type'] for row in cursor.fetchall()]
    release_db(conn)
    return results


# ============== Permission Management ==============

def get_all_permissions() -> list[dict]:
    """Get all permissions grouped by module."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT id, module_key, permission_key, label, description, icon, sort_order, parent_id
        FROM permissions
        ORDER BY module_key, sort_order, id
    ''')

    permissions = [dict_from_row(row) for row in cursor.fetchall()]
    release_db(conn)

    # Group by module
    modules = {}
    for perm in permissions:
        module_key = perm['module_key']
        if module_key not in modules:
            modules[module_key] = {
                'key': module_key,
                'label': module_key.replace('_', ' ').title(),
                'permissions': []
            }
        modules[module_key]['permissions'].append(perm)

    # Set module labels
    module_labels = {
        'system': 'System',
        'invoices': 'Invoices',
        'accounting': 'Accounting',
        'hr': 'HR Module'
    }
    for key, label in module_labels.items():
        if key in modules:
            modules[key]['label'] = label

    return list(modules.values())


def get_permissions_flat() -> list[dict]:
    """Get all permissions as flat list."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT id, module_key, permission_key, label, description, icon, sort_order, parent_id
        FROM permissions
        ORDER BY module_key, sort_order, id
    ''')

    permissions = [dict_from_row(row) for row in cursor.fetchall()]
    release_db(conn)
    return permissions


def get_role_permissions(role_id: int) -> dict:
    """Get permissions for a role as dict: {module_key: {permission_key: bool}}."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT p.module_key, p.permission_key, rp.granted
        FROM role_permissions rp
        JOIN permissions p ON p.id = rp.permission_id
        WHERE rp.role_id = %s AND rp.granted = TRUE
    ''', (role_id,))

    result = {}
    for row in cursor.fetchall():
        module = row['module_key']
        perm = row['permission_key']
        if module not in result:
            result[module] = {}
        result[module][perm] = True

    release_db(conn)
    return result


def get_role_permissions_list(role_id: int) -> list[str]:
    """Get permissions for a role as list of 'module.permission' strings."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT p.module_key, p.permission_key, p.label
        FROM role_permissions rp
        JOIN permissions p ON p.id = rp.permission_id
        WHERE rp.role_id = %s AND rp.granted = TRUE
        ORDER BY p.module_key, p.sort_order
    ''', (role_id,))

    result = []
    for row in cursor.fetchall():
        result.append({
            'key': f"{row['module_key']}.{row['permission_key']}",
            'module': row['module_key'],
            'permission': row['permission_key'],
            'label': row['label']
        })

    release_db(conn)
    return result


def set_role_permissions(role_id: int, permissions: list[str]) -> bool:
    """
    Set permissions for a role.
    permissions: list of 'module.permission' strings (e.g., ['invoices.view', 'hr.access'])
    Also syncs to old boolean columns for backward compatibility.
    """
    conn = get_db()
    cursor = get_cursor(conn)

    try:
        # Clear existing permissions for role
        cursor.execute('DELETE FROM role_permissions WHERE role_id = %s', (role_id,))

        # Insert new permissions
        for perm_str in permissions:
            parts = perm_str.split('.')
            if len(parts) != 2:
                continue
            module_key, perm_key = parts

            cursor.execute('''
                INSERT INTO role_permissions (role_id, permission_id, granted)
                SELECT %s, id, TRUE FROM permissions
                WHERE module_key = %s AND permission_key = %s
                ON CONFLICT (role_id, permission_id) DO UPDATE SET granted = TRUE
            ''', (role_id, module_key, perm_key))

        # Sync to old boolean columns for backward compatibility
        _sync_permissions_to_role_booleans(cursor, role_id, permissions)

        conn.commit()
        return True

    except Exception:
        conn.rollback()
        raise
    finally:
        release_db(conn)


def _sync_permissions_to_role_booleans(cursor, role_id: int, permissions: list[str]):
    """Sync new permission format to old boolean columns."""
    perm_set = set(permissions)

    # Map new permissions to old columns
    bool_updates = {
        'can_access_settings': 'system.settings' in perm_set,
        'can_view_invoices': 'invoices.view' in perm_set,
        'can_add_invoices': 'invoices.add' in perm_set,
        'can_edit_invoices': 'invoices.edit' in perm_set,
        'can_delete_invoices': 'invoices.delete' in perm_set,
        'can_access_accounting': 'accounting.dashboard' in perm_set,
        'can_access_templates': 'accounting.templates' in perm_set,
        'can_access_connectors': 'accounting.connectors' in perm_set,
        'can_access_hr': 'hr.access' in perm_set,
        'is_hr_manager': 'hr.manager' in perm_set,
    }

    updates = ', '.join([f"{col} = %s" for col in bool_updates.keys()])
    values = list(bool_updates.values()) + [role_id]

    cursor.execute(f'UPDATE roles SET {updates} WHERE id = %s', values)


def sync_role_from_booleans(role_id: int) -> bool:
    """Sync old boolean columns to new permissions table (for migration)."""
    conn = get_db()
    cursor = get_cursor(conn)

    try:
        cursor.execute('SELECT * FROM roles WHERE id = %s', (role_id,))
        role = cursor.fetchone()
        if not role:
            return False

        # Map old columns to new permission keys
        permission_map = {
            ('system', 'settings'): role.get('can_access_settings', False),
            ('invoices', 'view'): role.get('can_view_invoices', False),
            ('invoices', 'add'): role.get('can_add_invoices', False),
            ('invoices', 'edit'): role.get('can_edit_invoices', False),
            ('invoices', 'delete'): role.get('can_delete_invoices', False),
            ('accounting', 'dashboard'): role.get('can_access_accounting', False),
            ('accounting', 'templates'): role.get('can_access_templates', False),
            ('accounting', 'connectors'): role.get('can_access_connectors', False),
            ('hr', 'access'): role.get('can_access_hr', False),
            ('hr', 'manager'): role.get('is_hr_manager', False),
        }

        # Clear and re-insert
        cursor.execute('DELETE FROM role_permissions WHERE role_id = %s', (role_id,))

        for (module_key, perm_key), granted in permission_map.items():
            if granted:
                cursor.execute('''
                    INSERT INTO role_permissions (role_id, permission_id, granted)
                    SELECT %s, id, TRUE FROM permissions
                    WHERE module_key = %s AND permission_key = %s
                    ON CONFLICT (role_id, permission_id) DO NOTHING
                ''', (role_id, module_key, perm_key))

        conn.commit()
        return True

    except Exception:
        conn.rollback()
        raise
    finally:
        release_db(conn)


# ============== Enhanced Permission System (v2) CRUD ==============

def get_permission_matrix() -> dict:
    """
    Get all permissions organized for matrix display.
    Returns: {
        'modules': [
            {
                'key': 'system',
                'label': 'System',
                'icon': 'bi-gear-fill',
                'entities': [
                    {
                        'key': 'settings',
                        'label': 'Settings',
                        'actions': [
                            {'key': 'access', 'label': 'Access', 'id': 1, 'is_scope_based': False},
                            {'key': 'edit', 'label': 'Edit', 'id': 2, 'is_scope_based': False}
                        ]
                    }
                ]
            }
        ],
        'roles': [{'id': 1, 'name': 'Admin', ...}]
    }
    """
    conn = get_db()
    cursor = get_cursor(conn)

    # Get all permissions ordered by module, entity, sort_order
    cursor.execute('''
        SELECT id, module_key, module_label, module_icon, entity_key, entity_label,
               action_key, action_label, description, is_scope_based, sort_order
        FROM permissions_v2
        ORDER BY module_key, entity_key, sort_order
    ''')
    perms = cursor.fetchall()

    # Get all roles
    cursor.execute('SELECT id, name, description FROM roles ORDER BY id')
    roles = [dict(row) for row in cursor.fetchall()]

    release_db(conn)

    # Organize permissions into hierarchy
    modules = {}
    for p in perms:
        mod_key = p['module_key']
        ent_key = p['entity_key']

        if mod_key not in modules:
            modules[mod_key] = {
                'key': mod_key,
                'label': p['module_label'],
                'icon': p['module_icon'],
                'entities': {}
            }

        if ent_key not in modules[mod_key]['entities']:
            modules[mod_key]['entities'][ent_key] = {
                'key': ent_key,
                'label': p['entity_label'],
                'actions': []
            }

        modules[mod_key]['entities'][ent_key]['actions'].append({
            'id': p['id'],
            'key': p['action_key'],
            'label': p['action_label'],
            'description': p['description'],
            'is_scope_based': p['is_scope_based']
        })

    # Convert entities dict to list
    modules_list = []
    for mod in modules.values():
        mod['entities'] = list(mod['entities'].values())
        modules_list.append(mod)

    return {
        'modules': modules_list,
        'roles': roles
    }


def get_role_permissions_v2(role_id: int) -> dict:
    """
    Get all permissions for a role with their scope/granted values.
    Returns: {permission_id: {'scope': 'all', 'granted': True}, ...}
    """
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT permission_id, scope, granted
        FROM role_permissions_v2
        WHERE role_id = %s
    ''', (role_id,))

    result = {}
    for row in cursor.fetchall():
        result[row['permission_id']] = {
            'scope': row['scope'],
            'granted': row['granted']
        }

    release_db(conn)
    return result


def get_all_role_permissions_v2() -> dict:
    """
    Get permissions for all roles.
    Returns: {role_id: {permission_id: {'scope': 'all', 'granted': True}}}
    """
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT role_id, permission_id, scope, granted
        FROM role_permissions_v2
    ''')

    result = {}
    for row in cursor.fetchall():
        role_id = row['role_id']
        if role_id not in result:
            result[role_id] = {}
        result[role_id][row['permission_id']] = {
            'scope': row['scope'],
            'granted': row['granted']
        }

    release_db(conn)
    return result


def set_role_permission_v2(role_id: int, permission_id: int, scope: str = None, granted: bool = None) -> bool:
    """
    Set a single permission for a role.
    scope: 'deny', 'own', 'department', 'all' (for scope-based permissions)
    granted: True/False (for toggle permissions)
    """
    conn = get_db()
    cursor = get_cursor(conn)

    try:
        # Determine if permission is scope-based
        cursor.execute('SELECT is_scope_based FROM permissions_v2 WHERE id = %s', (permission_id,))
        perm = cursor.fetchone()
        if not perm:
            return False

        is_scope_based = perm['is_scope_based']

        if is_scope_based:
            # Use scope value
            actual_scope = scope if scope else 'deny'
            actual_granted = actual_scope != 'deny'
        else:
            # Use granted value
            actual_granted = granted if granted is not None else False
            actual_scope = 'all' if actual_granted else 'deny'

        cursor.execute('''
            INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted, updated_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (role_id, permission_id)
            DO UPDATE SET scope = %s, granted = %s, updated_at = CURRENT_TIMESTAMP
        ''', (role_id, permission_id, actual_scope, actual_granted, actual_scope, actual_granted))

        conn.commit()
        return True

    except Exception:
        conn.rollback()
        raise
    finally:
        release_db(conn)


def set_role_permissions_v2_bulk(role_id: int, permissions: dict) -> bool:
    """
    Set multiple permissions for a role at once.
    permissions: {permission_id: {'scope': 'all'} or {'granted': True}}
    """
    conn = get_db()
    cursor = get_cursor(conn)

    try:
        for perm_id, values in permissions.items():
            perm_id = int(perm_id)

            # Get permission type
            cursor.execute('SELECT is_scope_based FROM permissions_v2 WHERE id = %s', (perm_id,))
            perm = cursor.fetchone()
            if not perm:
                continue

            is_scope_based = perm['is_scope_based']

            if is_scope_based:
                scope = values.get('scope', 'deny')
                granted = scope != 'deny'
            else:
                granted = values.get('granted', False)
                scope = 'all' if granted else 'deny'

            cursor.execute('''
                INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted, updated_at)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (role_id, permission_id)
                DO UPDATE SET scope = %s, granted = %s, updated_at = CURRENT_TIMESTAMP
            ''', (role_id, perm_id, scope, granted, scope, granted))

        conn.commit()

        # Sync to old boolean columns for backward compatibility
        _sync_v2_permissions_to_booleans(cursor, role_id)
        conn.commit()

        return True

    except Exception:
        conn.rollback()
        raise
    finally:
        release_db(conn)


def _sync_v2_permissions_to_booleans(cursor, role_id: int):
    """Sync v2 permissions to old boolean columns for backward compatibility."""
    # Get current v2 permissions for this role
    cursor.execute('''
        SELECT p.module_key, p.entity_key, p.action_key, rp.scope, rp.granted
        FROM role_permissions_v2 rp
        JOIN permissions_v2 p ON p.id = rp.permission_id
        WHERE rp.role_id = %s
    ''', (role_id,))

    perms = {}
    for row in cursor.fetchall():
        key = f"{row['module_key']}.{row['entity_key']}.{row['action_key']}"
        perms[key] = row['scope'] != 'deny' or row['granted']

    # Map v2 permissions to old columns
    bool_updates = {
        'can_access_settings': perms.get('system.settings.access', False) or perms.get('system.settings.edit', False),
        'can_view_invoices': perms.get('invoices.records.view', False),
        'can_add_invoices': perms.get('invoices.records.add', False),
        'can_edit_invoices': perms.get('invoices.records.edit', False),
        'can_delete_invoices': perms.get('invoices.records.delete', False),
        'can_access_accounting': perms.get('accounting.dashboard.access', False),
        'can_access_templates': perms.get('invoices.templates.edit', False),
        'can_access_connectors': perms.get('accounting.connectors.access', False),
        'can_access_hr': perms.get('hr.employees.view', False) or perms.get('hr.bonuses.view', False),
        'is_hr_manager': perms.get('hr.bonuses.view_amounts', False),
    }

    updates = ', '.join([f"{col} = %s" for col in bool_updates.keys()])
    values = list(bool_updates.values()) + [role_id]

    cursor.execute(f'UPDATE roles SET {updates} WHERE id = %s', values)


def check_permission_v2(role_id: int, module: str, entity: str, action: str) -> dict:
    """
    Check if a role has a specific permission.
    Returns: {'has_permission': True, 'scope': 'all'} or {'has_permission': False, 'scope': 'deny'}
    """
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT rp.scope, rp.granted
        FROM role_permissions_v2 rp
        JOIN permissions_v2 p ON p.id = rp.permission_id
        WHERE rp.role_id = %s
          AND p.module_key = %s
          AND p.entity_key = %s
          AND p.action_key = %s
    ''', (role_id, module, entity, action))

    row = cursor.fetchone()
    release_db(conn)

    if row:
        has_perm = row['scope'] != 'deny' or row['granted']
        return {'has_permission': has_perm, 'scope': row['scope']}

    return {'has_permission': False, 'scope': 'deny'}


# ============== Profile Page Functions ==============

def get_responsable_by_email(email: str) -> Optional[dict]:
    """
    Find a responsable record by email address.
    Returns the responsable with their department/brand info.
    """
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT r.id, r.name, r.email, r.phone,
               ds.company, ds.brand, ds.department, ds.subdepartment
        FROM responsables r
        LEFT JOIN department_structure ds ON r.org_unit_id = ds.id
        WHERE LOWER(r.email) = LOWER(%s)
        LIMIT 1
    ''', (email,))

    row = cursor.fetchone()
    release_db(conn)

    if row:
        return {
            'id': row['id'],
            'name': row['name'],
            'email': row['email'],
            'phone': row['phone'],
            'company': row['company'],
            'brand': row['brand'],
            'department': row['department'],
            'subdepartment': row['subdepartment'],
            'departments': row['department'],  # Alias for profile page
        }
    return None


def get_user_invoices_by_responsible_name(
    responsible_name: str,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """
    Get invoices where the user is listed as responsible in allocations.
    """
    conn = get_db()
    cursor = get_cursor(conn)

    # Build query with proper joins
    query = '''
        SELECT DISTINCT
            i.id, i.invoice_number, i.invoice_date, i.invoice_value,
            i.currency, i.supplier, i.supplier_vat, i.dedicated_to,
            i.status, i.payment_status, i.drive_link, i.notes,
            i.created_at, i.updated_at
        FROM invoices i
        INNER JOIN allocations a ON i.id = a.invoice_id
        WHERE LOWER(a.responsible) = LOWER(%s)
    '''
    params = [responsible_name]

    if status:
        query += ' AND i.status = %s'
        params.append(status)

    if start_date:
        query += ' AND i.invoice_date >= %s'
        params.append(start_date)

    if end_date:
        query += ' AND i.invoice_date <= %s'
        params.append(end_date)

    if search:
        query += ''' AND (
            i.invoice_number ILIKE %s
            OR i.supplier ILIKE %s
            OR i.dedicated_to ILIKE %s
        )'''
        search_pattern = f'%{search}%'
        params.extend([search_pattern, search_pattern, search_pattern])

    query += ' ORDER BY i.invoice_date DESC LIMIT %s OFFSET %s'
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    release_db(conn)

    return [dict_from_row(dict(row)) for row in rows]


def get_user_invoices_count(
    responsible_name: str,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    search: Optional[str] = None,
) -> int:
    """
    Count invoices where the user is listed as responsible.
    """
    conn = get_db()
    cursor = get_cursor(conn)

    query = '''
        SELECT COUNT(DISTINCT i.id) as count
        FROM invoices i
        INNER JOIN allocations a ON i.id = a.invoice_id
        WHERE LOWER(a.responsible) = LOWER(%s)
    '''
    params = [responsible_name]

    if status:
        query += ' AND i.status = %s'
        params.append(status)

    if start_date:
        query += ' AND i.invoice_date >= %s'
        params.append(start_date)

    if end_date:
        query += ' AND i.invoice_date <= %s'
        params.append(end_date)

    if search:
        query += ''' AND (
            i.invoice_number ILIKE %s
            OR i.supplier ILIKE %s
            OR i.dedicated_to ILIKE %s
        )'''
        search_pattern = f'%{search}%'
        params.extend([search_pattern, search_pattern, search_pattern])

    cursor.execute(query, params)
    row = cursor.fetchone()
    release_db(conn)

    return row['count'] if row else 0


def get_user_invoices_summary(responsible_name: str) -> dict:
    """
    Get invoice summary stats for a responsible person.
    """
    conn = get_db()
    cursor = get_cursor(conn)

    # Get status breakdown
    cursor.execute('''
        SELECT i.status, COUNT(DISTINCT i.id) as count
        FROM invoices i
        INNER JOIN allocations a ON i.id = a.invoice_id
        WHERE LOWER(a.responsible) = LOWER(%s)
        GROUP BY i.status
    ''', (responsible_name,))

    by_status = {}
    for row in cursor.fetchall():
        by_status[row['status'] or 'unknown'] = row['count']

    # Get total value
    cursor.execute('''
        SELECT COUNT(DISTINCT i.id) as total, COALESCE(SUM(DISTINCT i.invoice_value), 0) as total_value
        FROM invoices i
        INNER JOIN allocations a ON i.id = a.invoice_id
        WHERE LOWER(a.responsible) = LOWER(%s)
    ''', (responsible_name,))

    totals = cursor.fetchone()
    release_db(conn)

    return {
        'total': totals['total'] if totals else 0,
        'total_value': float(totals['total_value']) if totals else 0,
        'by_status': by_status,
    }


def get_user_event_bonuses(
    responsable_id: int,
    year: Optional[int] = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """
    Get HR event bonuses for a responsable.
    """
    conn = get_db()
    cursor = get_cursor(conn)

    # Find employee by responsable_id (via email match or user_id)
    cursor.execute('''
        SELECT e.id as employee_id
        FROM hr.employees e
        INNER JOIN responsables r ON (
            LOWER(r.email) = (SELECT LOWER(email) FROM users WHERE id = e.user_id)
            OR LOWER(r.name) = LOWER(e.name)
        )
        WHERE r.id = %s
        LIMIT 1
    ''', (responsable_id,))

    emp_row = cursor.fetchone()
    if not emp_row:
        release_db(conn)
        return []

    employee_id = emp_row['employee_id']

    query = '''
        SELECT
            eb.id, eb.year, eb.month, eb.bonus_days, eb.hours_free,
            eb.bonus_net, eb.details, eb.allocation_month,
            eb.created_at, eb.updated_at,
            e.name as event_name, e.start_date, e.end_date,
            e.company, e.brand
        FROM hr.event_bonuses eb
        INNER JOIN hr.events e ON eb.event_id = e.id
        WHERE eb.employee_id = %s
    '''
    params = [employee_id]

    if year:
        query += ' AND eb.year = %s'
        params.append(year)

    query += ' ORDER BY eb.year DESC, eb.month DESC LIMIT %s OFFSET %s'
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    release_db(conn)

    return [dict_from_row(dict(row)) for row in rows]


def get_user_event_bonuses_summary(responsable_id: int) -> dict:
    """
    Get summary of HR event bonuses for a responsable.
    """
    conn = get_db()
    cursor = get_cursor(conn)

    # Find employee by responsable
    cursor.execute('''
        SELECT e.id as employee_id
        FROM hr.employees e
        INNER JOIN responsables r ON (
            LOWER(r.email) = (SELECT LOWER(email) FROM users WHERE id = e.user_id)
            OR LOWER(r.name) = LOWER(e.name)
        )
        WHERE r.id = %s
        LIMIT 1
    ''', (responsable_id,))

    emp_row = cursor.fetchone()
    if not emp_row:
        release_db(conn)
        return {'total_bonuses': 0, 'total_amount': 0, 'events_count': 0}

    employee_id = emp_row['employee_id']

    cursor.execute('''
        SELECT
            COUNT(*) as total_bonuses,
            COALESCE(SUM(bonus_net), 0) as total_amount,
            COUNT(DISTINCT event_id) as events_count
        FROM hr.event_bonuses
        WHERE employee_id = %s
    ''', (employee_id,))

    row = cursor.fetchone()
    release_db(conn)

    if row:
        return {
            'total_bonuses': row['total_bonuses'],
            'total_amount': float(row['total_amount']),
            'events_count': row['events_count'],
        }
    return {'total_bonuses': 0, 'total_amount': 0, 'events_count': 0}


def get_user_notifications(
    responsable_id: int,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """
    Get notifications sent to a responsable.
    """
    conn = get_db()
    cursor = get_cursor(conn)

    # Get responsable email
    cursor.execute('SELECT email FROM responsables WHERE id = %s', (responsable_id,))
    resp_row = cursor.fetchone()

    if not resp_row or not resp_row['email']:
        release_db(conn)
        return []

    cursor.execute('''
        SELECT id, event_type, invoice_id, recipient_email, status,
               error_message, created_at
        FROM notification_logs
        WHERE LOWER(recipient_email) = LOWER(%s)
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    ''', (resp_row['email'], limit, offset))

    rows = cursor.fetchall()
    release_db(conn)

    return [dict_from_row(dict(row)) for row in rows]


def get_user_notifications_summary(responsable_id: int) -> dict:
    """
    Get notification summary for a responsable.
    """
    conn = get_db()
    cursor = get_cursor(conn)

    # Get responsable email
    cursor.execute('SELECT email FROM responsables WHERE id = %s', (responsable_id,))
    resp_row = cursor.fetchone()

    if not resp_row or not resp_row['email']:
        release_db(conn)
        return {'total': 0, 'sent': 0, 'failed': 0}

    cursor.execute('''
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE status = 'sent') as sent,
            COUNT(*) FILTER (WHERE status = 'failed') as failed
        FROM notification_logs
        WHERE LOWER(recipient_email) = LOWER(%s)
    ''', (resp_row['email'],))

    row = cursor.fetchone()
    release_db(conn)

    if row:
        return {
            'total': row['total'],
            'sent': row['sent'],
            'failed': row['failed'],
        }
    return {'total': 0, 'sent': 0, 'failed': 0}


def get_user_activity(
    user_id: int,
    event_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """
    Get activity log for a user.
    """
    conn = get_db()
    cursor = get_cursor(conn)

    query = '''
        SELECT id, event_type, details, ip_address, user_agent, created_at
        FROM user_events
        WHERE user_id = %s
    '''
    params = [user_id]

    if event_type:
        query += ' AND event_type = %s'
        params.append(event_type)

    query += ' ORDER BY created_at DESC LIMIT %s OFFSET %s'
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    release_db(conn)

    return [dict_from_row(dict(row)) for row in rows]


def get_user_activity_count(user_id: int) -> int:
    """
    Count activity events for a user.
    """
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT COUNT(*) as count
        FROM user_events
        WHERE user_id = %s
    ''', (user_id,))

    row = cursor.fetchone()
    release_db(conn)

    return row['count'] if row else 0


# Initialize database on import
init_db()
