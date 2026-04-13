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
# 3 Gunicorn workers × 15 max = 45 connections (leaves 2 for admin/health)
# Frontend fires 11+ concurrent requests at page load — pool must handle that burst
_connection_pool = None
_pool_lock = threading.Lock()

POOL_MIN_CONN = int(os.environ.get('DB_POOL_MIN_CONN', '2'))
POOL_MAX_CONN = int(os.environ.get('DB_POOL_MAX_CONN', '15'))
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



def _recompute_bilant_formula_values(cursor):
    """Recompute all formula_rd values in bilant_results.

    After OMF→B numbering migration, row numbers shifted but stored values
    were stale. This recomputes formula_rd sums in dependency order and
    updates verification strings with detailed row amounts.
    """
    cursor.execute("SELECT DISTINCT generation_id FROM bilant_results WHERE formula_rd IS NOT NULL")
    gen_ids = [r['generation_id'] for r in cursor.fetchall()]
    if not gen_ids:
        return

    updated = 0
    for gen_id in gen_ids:
        cursor.execute("""
            SELECT id, nr_rd, value, formula_rd
            FROM bilant_results WHERE generation_id = %s
            ORDER BY CASE
                WHEN nr_rd = '35a' THEN 35.5
                WHEN nr_rd ~ '^[0-9]+$' THEN CAST(nr_rd AS FLOAT)
                ELSE 999 END
        """, (gen_id,))
        all_rows = cursor.fetchall()
        values = {r['nr_rd']: float(r['value'] or 0) for r in all_rows if r['nr_rd']}

        # Evaluate formula_rd rows in order (dependencies have lower nr_rd)
        for row in all_rows:
            if not row['formula_rd']:
                continue
            expr = row['formula_rd']
            # Parse and evaluate: tokens like "31+32+33-34+35a"
            total = 0.0
            sign = 1
            token = ''
            parts = []
            for ch in expr + '+':
                if ch.isdigit() or ch.isalpha():
                    token += ch
                elif ch in '+-':
                    if token:
                        # Strip leading zeros but keep alphanumeric like '35a'
                        row_num = token.lstrip('0') or '0'
                        val = values.get(row_num, 0)
                        total += sign * val
                        pfx = '+' if sign == 1 else '-'
                        parts.append(f"{pfx} rd.{row_num} ({val:,.2f})")
                        token = ''
                    sign = 1 if ch == '+' else -1
            # Update value in dict for dependent formulas
            if row['nr_rd']:
                values[row['nr_rd']] = total
            # Build verification string
            if parts and parts[0].startswith('+ '):
                parts[0] = parts[0][2:]
            verification = ' '.join(parts) + f" = {total:,.2f}"
            # Update DB if value changed
            old_val = float(row['value'] or 0)
            if abs(total - old_val) > 0.001:
                cursor.execute(
                    "UPDATE bilant_results SET value = %s, verification = %s WHERE id = %s",
                    (total, verification, row['id'])
                )
                updated += 1
            else:
                # Still update verification string for detailed display
                cursor.execute(
                    "UPDATE bilant_results SET verification = %s WHERE id = %s",
                    (verification, row['id'])
                )
    if updated:
        logger.info(f'Recomputed {updated} stale formula_rd values across {len(gen_ids)} generation(s)')


def init_db():
    """Initialize database tables, indexes, and seed data.

    Delegates to migrations.init_schema.create_schema() which contains
    all CREATE TABLE, ALTER TABLE, CREATE INDEX, and INSERT statements.

    Skips if schema already exists (checks for newest table) to avoid
    running ~100 SQL statements on every worker startup.
    """
    conn = get_db()
    cursor = get_cursor(conn)
    try:
        # Quick check: if newest table exists, full schema is already initialized
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'crm_import_batches'
            )
        """)
        if cursor.fetchone()['exists']:
            # Run incremental column/index/table migrations
            from migrations.domains.schema_incremental import create_schema_incremental
            create_schema_incremental(conn, cursor)
            logger.info('Database schema already initialized — skipping init_db()')
            return


        # Check if base schema exists but newer tables are missing (incremental migration)
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'auto_tag_rules'
            )
        """)
        if cursor.fetchone()['exists']:
            logger.info('Base schema exists but newer tables missing — running incremental migration')
            from migrations.init_schema import create_schema
            create_schema(conn, cursor)
            # Chart of Accounts (Plan de Conturi)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chart_of_accounts (
                    id SERIAL PRIMARY KEY,
                    code TEXT NOT NULL,
                    name TEXT NOT NULL,
                    account_class SMALLINT NOT NULL,
                    account_type TEXT NOT NULL DEFAULT 'synthetic',
                    parent_code TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT chart_of_accounts_unique UNIQUE (code, company_id)
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_coa_class ON chart_of_accounts(account_class)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_coa_parent ON chart_of_accounts(parent_code)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_coa_company ON chart_of_accounts(company_id)')
            cursor.execute("SELECT COUNT(*) as cnt FROM chart_of_accounts WHERE company_id IS NULL")
            if cursor.fetchone()['cnt'] == 0:
                from migrations.init_schema import _seed_chart_of_accounts
                _seed_chart_of_accounts(cursor)
            # Dynamic metrics columns
            cursor.execute('''
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name = 'bilant_metric_configs' AND column_name = 'formula_expr') THEN
                        ALTER TABLE bilant_metric_configs ADD COLUMN formula_expr TEXT;
                        ALTER TABLE bilant_metric_configs ADD COLUMN display_format TEXT DEFAULT 'currency';
                        ALTER TABLE bilant_metric_configs ADD COLUMN interpretation TEXT;
                        ALTER TABLE bilant_metric_configs ADD COLUMN threshold_good NUMERIC(12,4);
                        ALTER TABLE bilant_metric_configs ADD COLUMN threshold_warning NUMERIC(12,4);
                        ALTER TABLE bilant_metric_configs ADD COLUMN structure_side TEXT;
                        ALTER TABLE bilant_metric_configs ALTER COLUMN nr_rd DROP NOT NULL;
                    END IF;
                END $$;
            ''')
            # Fix corrupted seed data from original export
            cursor.execute("""
                UPDATE bilant_template_rows SET formula_rd = NULL
                WHERE formula_rd ~ '^[a-z]'
            """)
            cursor.execute("""
                UPDATE bilant_template_rows SET row_type = 'data', is_bold = FALSE, indent_level = 1
                WHERE nr_rd IN ('19', '21', '95') AND row_type = 'total'
            """)
            # Add has_team flag to structure_nodes
            cursor.execute('''
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name = 'structure_nodes' AND column_name = 'has_team') THEN
                        ALTER TABLE structure_nodes ADD COLUMN has_team BOOLEAN NOT NULL DEFAULT FALSE;
                    END IF;
                END $$;
            ''')
            # Structure node members (responsables + team per organigram node)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS structure_node_members (
                    id SERIAL PRIMARY KEY,
                    node_id INTEGER NOT NULL REFERENCES structure_nodes(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    role TEXT NOT NULL DEFAULT 'team' CHECK (role IN ('responsable', 'team')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT structure_node_members_unique UNIQUE (node_id, user_id)
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_snm_node ON structure_node_members(node_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_snm_user ON structure_node_members(user_id)')
            # BioStar employee blacklist column
            cursor.execute('''
                DO $$ BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name = 'biostar_employees' AND column_name = 'is_blacklisted') THEN
                        ALTER TABLE biostar_employees ADD COLUMN is_blacklisted BOOLEAN NOT NULL DEFAULT FALSE;
                    END IF;
                END $$;
            ''')
            # GPS Check-in Locations
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS checkin_locations (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    latitude NUMERIC(10,7) NOT NULL,
                    longitude NUMERIC(10,7) NOT NULL,
                    allowed_radius_meters INTEGER NOT NULL DEFAULT 50,
                    allowed_ips JSONB NOT NULL DEFAULT '[]'::JSONB,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    auto_checkout_radius_meters INTEGER NOT NULL DEFAULT 200
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_checkin_locations_active ON checkin_locations(is_active)')

            # BioStar tables (needed for GPS check-in + pontaje)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS biostar_employees (
                    id SERIAL PRIMARY KEY,
                    biostar_user_id VARCHAR(50) NOT NULL UNIQUE,
                    name VARCHAR(255) NOT NULL,
                    email VARCHAR(255),
                    phone VARCHAR(50),
                    user_group_id VARCHAR(50),
                    user_group_name VARCHAR(255),
                    department VARCHAR(255),
                    title VARCHAR(255),
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    mapped_jarvis_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    photo_url TEXT,
                    schedule_start VARCHAR(10),
                    schedule_end VARCHAR(10),
                    lunch_break_minutes INTEGER DEFAULT 60,
                    working_hours INTEGER DEFAULT 8,
                    is_blacklisted BOOLEAN NOT NULL DEFAULT FALSE,
                    last_synced_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_biostar_employees_mapped ON biostar_employees(mapped_jarvis_user_id)')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS biostar_punch_logs (
                    id SERIAL PRIMARY KEY,
                    biostar_event_id VARCHAR(100) NOT NULL,
                    biostar_user_id VARCHAR(50) NOT NULL,
                    event_datetime TIMESTAMP NOT NULL,
                    event_type VARCHAR(50) DEFAULT 'DEVICE_PUNCH',
                    direction VARCHAR(10),
                    device_id VARCHAR(50),
                    device_name VARCHAR(255),
                    door_id VARCHAR(50),
                    door_name VARCHAR(255),
                    temperature NUMERIC(4,1),
                    raw_data JSONB,
                    synced_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            ''')
            cursor.execute('''CREATE UNIQUE INDEX IF NOT EXISTS idx_biostar_punch_dedup
                ON biostar_punch_logs(biostar_event_id, (event_datetime::date))''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_biostar_punch_user ON biostar_punch_logs(biostar_user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_biostar_punch_datetime ON biostar_punch_logs(event_datetime)')

            conn.commit()
            logger.info('Incremental migration complete')
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
    from decimal import Decimal
    result = dict(row)
    for key, value in result.items():
        if hasattr(value, 'isoformat'):
            result[key] = value.isoformat()
        elif isinstance(value, Decimal):
            result[key] = float(value)
    return result


# Initialize database on import
init_db()
