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
                WHERE table_schema = 'public' AND table_name = 'smart_notification_state'
            )
        """)
        if cursor.fetchone()['exists']:
            # Run pending column migrations on existing schema
            cursor.execute('''
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name = 'auto_tag_rules' AND column_name = 'match_mode') THEN
                        ALTER TABLE auto_tag_rules ADD COLUMN match_mode VARCHAR(10) NOT NULL DEFAULT 'all';
                    END IF;
                END $$;
            ''')
            cursor.execute('''
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name = 'mkt_projects' AND column_name = 'company_ids') THEN
                        ALTER TABLE mkt_projects ADD COLUMN company_ids INTEGER[] DEFAULT '{}';
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name = 'mkt_projects' AND column_name = 'brand_ids') THEN
                        ALTER TABLE mkt_projects ADD COLUMN brand_ids INTEGER[] DEFAULT '{}';
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name = 'mkt_projects' AND column_name = 'department_ids') THEN
                        ALTER TABLE mkt_projects ADD COLUMN department_ids INTEGER[] DEFAULT '{}';
                    END IF;
                END $$;
            ''')
            # Ensure 'approved' invoice status exists
            cursor.execute('''
                INSERT INTO dropdown_options (dropdown_type, value, label, color, sort_order, is_active, min_role)
                SELECT 'invoice_status', 'approved', 'Approved', '#22c55e', 5, TRUE, 'Viewer'
                WHERE NOT EXISTS (
                    SELECT 1 FROM dropdown_options WHERE dropdown_type = 'invoice_status' AND value = 'approved'
                )
            ''')
            # Create mkt_project_events if not exists
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS mkt_project_events (
                    id SERIAL PRIMARY KEY,
                    project_id INTEGER NOT NULL REFERENCES mkt_projects(id) ON DELETE CASCADE,
                    event_id INTEGER NOT NULL REFERENCES hr.events(id) ON DELETE CASCADE,
                    notes TEXT,
                    linked_by INTEGER NOT NULL REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT mkt_project_events_unique UNIQUE (project_id, event_id)
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_project_events_project ON mkt_project_events(project_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_project_events_event ON mkt_project_events(event_id)')
            # KPI linking tables
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS mkt_kpi_budget_lines (
                    id SERIAL PRIMARY KEY,
                    project_kpi_id INTEGER NOT NULL REFERENCES mkt_project_kpis(id) ON DELETE CASCADE,
                    budget_line_id INTEGER NOT NULL REFERENCES mkt_budget_lines(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT mkt_kpi_budget_lines_unique UNIQUE (project_kpi_id, budget_line_id)
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_kpi_bl_kpi ON mkt_kpi_budget_lines(project_kpi_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_kpi_bl_line ON mkt_kpi_budget_lines(budget_line_id)')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS mkt_kpi_dependencies (
                    id SERIAL PRIMARY KEY,
                    project_kpi_id INTEGER NOT NULL REFERENCES mkt_project_kpis(id) ON DELETE CASCADE,
                    depends_on_kpi_id INTEGER NOT NULL REFERENCES mkt_project_kpis(id) ON DELETE CASCADE,
                    role TEXT NOT NULL DEFAULT 'input',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT mkt_kpi_deps_unique UNIQUE (project_kpi_id, depends_on_kpi_id),
                    CONSTRAINT mkt_kpi_deps_no_self CHECK (project_kpi_id != depends_on_kpi_id)
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_kpi_deps_kpi ON mkt_kpi_dependencies(project_kpi_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_kpi_deps_dep ON mkt_kpi_dependencies(depends_on_kpi_id)')
            # Seed default mkt_project approval flow if missing
            cursor.execute('''
                INSERT INTO approval_flows (name, slug, entity_type, is_active, created_by)
                SELECT 'Marketing Project Approval', 'mkt-project-approval', 'mkt_project', TRUE, 1
                WHERE NOT EXISTS (
                    SELECT 1 FROM approval_flows WHERE slug = 'mkt-project-approval'
                )
            ''')
            cursor.execute('''
                INSERT INTO approval_steps (flow_id, name, step_order, approver_type, notify_on_pending, notify_on_decision)
                SELECT f.id, 'Selected Approver', 1, 'context_approver', TRUE, TRUE
                FROM approval_flows f
                WHERE f.slug = 'mkt-project-approval'
                AND NOT EXISTS (
                    SELECT 1 FROM approval_steps s WHERE s.flow_id = f.id
                )
            ''')
            # Smart notification state table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS smart_notification_state (
                    id SERIAL PRIMARY KEY,
                    alert_type TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id INTEGER NOT NULL,
                    last_alerted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_value NUMERIC(15,4),
                    CONSTRAINT smart_notif_state_unique UNIQUE (alert_type, entity_type, entity_id)
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_smart_notif_state_type ON smart_notification_state(alert_type)')
            # AI6: line_items + invoice_type columns on invoices
            cursor.execute('''
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name = 'invoices' AND column_name = 'line_items') THEN
                        ALTER TABLE invoices ADD COLUMN line_items JSONB;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name = 'invoices' AND column_name = 'invoice_type') THEN
                        ALTER TABLE invoices ADD COLUMN invoice_type TEXT DEFAULT 'standard';
                    END IF;
                END $$;
            ''')
            cursor.execute('''
                INSERT INTO notification_settings (setting_key, setting_value) VALUES
                    ('smart_alerts_enabled', 'true'),
                    ('smart_kpi_alerts_enabled', 'true'),
                    ('smart_budget_alerts_enabled', 'true'),
                    ('smart_invoice_anomaly_enabled', 'true'),
                    ('smart_efactura_backlog_enabled', 'true'),
                    ('smart_efactura_backlog_threshold', '50'),
                    ('smart_alert_cooldown_hours', '24'),
                    ('smart_invoice_anomaly_sigma', '2')
                ON CONFLICT (setting_key) DO NOTHING
            ''')
            # M-KPI: role column on mkt_kpi_budget_lines
            cursor.execute('''
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name = 'mkt_kpi_budget_lines' AND column_name = 'role') THEN
                        ALTER TABLE mkt_kpi_budget_lines ADD COLUMN role TEXT NOT NULL DEFAULT 'input';
                    END IF;
                END $$;
            ''')
            # M-KPI: currency column on mkt_project_kpis
            cursor.execute('''
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name = 'mkt_project_kpis' AND column_name = 'currency') THEN
                        ALTER TABLE mkt_project_kpis ADD COLUMN currency TEXT DEFAULT 'RON';
                    END IF;
                END $$;
            ''')
            # M-KPI: migrate abstract roles to formula variable names
            cursor.execute('''
                UPDATE mkt_kpi_budget_lines kb
                SET role = COALESCE(
                    (SELECT split_part(kd.formula, ' ', 1)
                     FROM mkt_project_kpis pk
                     JOIN mkt_kpi_definitions kd ON kd.id = pk.kpi_definition_id
                     WHERE pk.id = kb.project_kpi_id AND kd.formula IS NOT NULL),
                    'input')
                WHERE kb.role IN ('numerator', 'denominator', 'input')
                AND EXISTS (
                    SELECT 1 FROM mkt_project_kpis pk
                    JOIN mkt_kpi_definitions kd ON kd.id = pk.kpi_definition_id
                    WHERE pk.id = kb.project_kpi_id AND kd.formula IS NOT NULL)
            ''')
            cursor.execute('''
                UPDATE mkt_kpi_dependencies kd_link
                SET role = COALESCE(
                    (SELECT dep_def.slug
                     FROM mkt_project_kpis dep_pk
                     JOIN mkt_kpi_definitions dep_def ON dep_def.id = dep_pk.kpi_definition_id
                     WHERE dep_pk.id = kd_link.depends_on_kpi_id),
                    'input')
                WHERE kd_link.role IN ('numerator', 'denominator', 'input')
                AND EXISTS (
                    SELECT 1 FROM mkt_project_kpis pk
                    JOIN mkt_kpi_definitions kd ON kd.id = pk.kpi_definition_id
                    WHERE pk.id = kd_link.project_kpi_id AND kd.formula IS NOT NULL)
            ''')
            conn.commit()
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
