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
            # Add can_access_crm permission to roles (if not exists)
            cursor.execute("""
                DO $$ BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name = 'roles' AND column_name = 'can_access_crm') THEN
                        ALTER TABLE roles ADD COLUMN can_access_crm BOOLEAN DEFAULT FALSE;
                        UPDATE roles SET can_access_crm = TRUE WHERE name = 'Admin';
                    END IF;
                END $$;
            """)
            # CRM CRUD + export permissions
            cursor.execute("""
                DO $$ BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name = 'roles' AND column_name = 'can_edit_crm') THEN
                        ALTER TABLE roles ADD COLUMN can_edit_crm BOOLEAN DEFAULT FALSE;
                        ALTER TABLE roles ADD COLUMN can_delete_crm BOOLEAN DEFAULT FALSE;
                        ALTER TABLE roles ADD COLUMN can_export_crm BOOLEAN DEFAULT FALSE;
                        UPDATE roles SET can_edit_crm = TRUE, can_delete_crm = TRUE, can_export_crm = TRUE WHERE name = 'Admin';
                    END IF;
                END $$;
            """)
            # Ensure 'approved' invoice status exists
            cursor.execute('''
                INSERT INTO dropdown_options (dropdown_type, value, label, color, sort_order, is_active, min_role)
                SELECT 'invoice_status', 'approved', 'Approved', '#22c55e', 5, TRUE, 'Viewer'
                WHERE NOT EXISTS (
                    SELECT 1 FROM dropdown_options WHERE dropdown_type = 'invoice_status' AND value = 'approved'
                )
            ''')
            # Create mkt_project_files if not exists
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS mkt_project_files (
                    id SERIAL PRIMARY KEY,
                    project_id INTEGER NOT NULL REFERENCES mkt_projects(id) ON DELETE CASCADE,
                    file_name TEXT NOT NULL,
                    file_type TEXT,
                    mime_type TEXT,
                    file_size INTEGER,
                    storage_uri TEXT NOT NULL,
                    uploaded_by INTEGER NOT NULL REFERENCES users(id),
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_files_project ON mkt_project_files(project_id)')
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
            # Drop hardcoded member role CHECK — roles now from global roles table
            cursor.execute('''
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM information_schema.constraint_column_usage
                               WHERE table_name = 'mkt_project_members' AND constraint_name = 'mkt_members_role_check') THEN
                        ALTER TABLE mkt_project_members DROP CONSTRAINT mkt_members_role_check;
                    END IF;
                END $$;
            ''')
            # Seed marketing permissions_v2 if not present
            cursor.execute("SELECT COUNT(*) as cnt FROM permissions_v2 WHERE module_key = 'marketing'")
            if cursor.fetchone()['cnt'] == 0:
                cursor.execute('''
                    INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order) VALUES
                    ('marketing', 'Marketing', 'bi-megaphone', 'project', 'Projects', 'view', 'View', 'View marketing projects', TRUE, 1),
                    ('marketing', 'Marketing', 'bi-megaphone', 'project', 'Projects', 'create', 'Create', 'Create marketing projects', TRUE, 2),
                    ('marketing', 'Marketing', 'bi-megaphone', 'project', 'Projects', 'edit', 'Edit', 'Edit marketing projects', TRUE, 3),
                    ('marketing', 'Marketing', 'bi-megaphone', 'project', 'Projects', 'delete', 'Delete', 'Delete marketing projects', TRUE, 4),
                    ('marketing', 'Marketing', 'bi-megaphone', 'project', 'Projects', 'approve', 'Submit for Approval', 'Submit projects for approval', TRUE, 5),
                    ('marketing', 'Marketing', 'bi-megaphone', 'budget', 'Budgets', 'view', 'View', 'View budget allocations', TRUE, 6),
                    ('marketing', 'Marketing', 'bi-megaphone', 'budget', 'Budgets', 'edit', 'Edit', 'Edit budgets and record spend', TRUE, 7),
                    ('marketing', 'Marketing', 'bi-megaphone', 'kpi', 'KPIs', 'view', 'View', 'View KPI targets and actuals', TRUE, 8),
                    ('marketing', 'Marketing', 'bi-megaphone', 'kpi', 'KPIs', 'edit', 'Edit', 'Set KPI targets and record values', TRUE, 9),
                    ('marketing', 'Marketing', 'bi-megaphone', 'report', 'Reports', 'view', 'View', 'View marketing reports', TRUE, 10)
                ''')
                cursor.execute('SELECT id, name FROM roles')
                for role in cursor.fetchall():
                    rn = role['name']
                    cursor.execute("SELECT id, action_key FROM permissions_v2 WHERE module_key = 'marketing'")
                    for p in cursor.fetchall():
                        scope = 'deny'
                        if rn == 'Admin':
                            scope = 'all'
                        elif rn == 'Manager':
                            scope = 'department' if p['action_key'] != 'delete' else 'deny'
                        elif p['action_key'] in ('view', 'create'):
                            scope = 'own'
                        if scope != 'deny':
                            cursor.execute('''
                                INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
                                VALUES (%s, %s, %s, TRUE)
                                ON CONFLICT (role_id, permission_id) DO NOTHING
                            ''', (role['id'], p['id'], scope))
            # M-KPI: benchmarks column on definitions
            cursor.execute('''
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name = 'mkt_kpi_definitions' AND column_name = 'benchmarks') THEN
                        ALTER TABLE mkt_kpi_definitions ADD COLUMN benchmarks JSONB;
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
            # KPI show_on_overview flag
            cursor.execute('''
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name = 'mkt_project_kpis' AND column_name = 'show_on_overview') THEN
                        ALTER TABLE mkt_project_kpis ADD COLUMN show_on_overview BOOLEAN DEFAULT FALSE;
                    END IF;
                END $$;
            ''')
            # Campaign Simulator benchmarks table + seed
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS mkt_sim_benchmarks (
                    id SERIAL PRIMARY KEY,
                    channel_key TEXT NOT NULL,
                    channel_label TEXT NOT NULL,
                    funnel_stage TEXT NOT NULL,
                    month_index INTEGER NOT NULL,
                    cpc NUMERIC(10,4) NOT NULL,
                    cvr_lead NUMERIC(8,6) NOT NULL,
                    cvr_car NUMERIC(8,6) NOT NULL DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT mkt_sim_bench_stage CHECK (funnel_stage IN ('awareness','consideration','conversion')),
                    CONSTRAINT mkt_sim_bench_month CHECK (month_index BETWEEN 1 AND 3),
                    CONSTRAINT mkt_sim_bench_unique UNIQUE (channel_key, funnel_stage, month_index)
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_sim_bench_stage ON mkt_sim_benchmarks(funnel_stage)')
            cursor.execute("SELECT COUNT(*) as cnt FROM mkt_sim_benchmarks")
            if cursor.fetchone()['cnt'] == 0:
                from migrations.init_schema import _seed_sim_benchmarks
                _seed_sim_benchmarks(cursor)
            # OKR tables for marketing projects
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS mkt_objectives (
                    id SERIAL PRIMARY KEY,
                    project_id INTEGER NOT NULL REFERENCES mkt_projects(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    description TEXT,
                    sort_order INTEGER DEFAULT 0,
                    created_by INTEGER NOT NULL REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_objectives_project ON mkt_objectives(project_id)')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS mkt_key_results (
                    id SERIAL PRIMARY KEY,
                    objective_id INTEGER NOT NULL REFERENCES mkt_objectives(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    target_value NUMERIC(15,4) NOT NULL DEFAULT 100,
                    current_value NUMERIC(15,4) NOT NULL DEFAULT 0,
                    unit TEXT NOT NULL DEFAULT 'number',
                    linked_kpi_id INTEGER REFERENCES mkt_project_kpis(id) ON DELETE SET NULL,
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_key_results_objective ON mkt_key_results(objective_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_mkt_key_results_kpi ON mkt_key_results(linked_kpi_id)')
            # OKR permissions
            cursor.execute("SELECT COUNT(*) as cnt FROM permissions_v2 WHERE module_key = 'marketing' AND entity_key = 'okr'")
            if cursor.fetchone()['cnt'] == 0:
                cursor.execute('''
                    INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order) VALUES
                    ('marketing', 'Marketing', 'bi-megaphone', 'okr', 'OKR', 'view', 'View', 'View objectives & key results', TRUE, 11),
                    ('marketing', 'Marketing', 'bi-megaphone', 'okr', 'OKR', 'edit', 'Edit', 'Edit objectives & key results', TRUE, 12)
                ''')
                cursor.execute('SELECT id, name FROM roles')
                for role in cursor.fetchall():
                    rn = role['name']
                    cursor.execute("SELECT id, action_key FROM permissions_v2 WHERE module_key = 'marketing' AND entity_key = 'okr'")
                    for p in cursor.fetchall():
                        scope = 'deny'
                        if rn == 'Admin':
                            scope = 'all'
                        elif rn == 'Manager':
                            scope = 'department'
                        elif p['action_key'] == 'view':
                            scope = 'own'
                        elif p['action_key'] == 'edit':
                            scope = 'own'
                        if scope != 'deny':
                            cursor.execute('''
                                INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
                                VALUES (%s, %s, %s, TRUE)
                                ON CONFLICT (role_id, permission_id) DO NOTHING
                            ''', (role['id'], p['id'], scope))
            # Document signatures table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS document_signatures (
                    id SERIAL PRIMARY KEY,
                    document_type VARCHAR(50) NOT NULL,
                    document_id INTEGER NOT NULL,
                    signed_by INTEGER NOT NULL REFERENCES users(id),
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    signed_at TIMESTAMP,
                    ip_address VARCHAR(45),
                    signature_image TEXT,
                    document_hash VARCHAR(64),
                    original_pdf_path TEXT,
                    signed_pdf_path TEXT,
                    callback_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT chk_sig_status CHECK (status IN ('pending','signed','rejected','expired'))
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_doc_sig_doc ON document_signatures(document_type, document_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_doc_sig_signer ON document_signatures(signed_by, status)')
            # requires_signature flag on approval_flows
            cursor.execute('''
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name = 'approval_flows' AND column_name = 'requires_signature') THEN
                        ALTER TABLE approval_flows ADD COLUMN requires_signature BOOLEAN DEFAULT FALSE;
                    END IF;
                END $$;
            ''')
            # Stakeholder approval: approval_mode column on mkt_projects
            cursor.execute('''
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name = 'mkt_projects' AND column_name = 'approval_mode') THEN
                        ALTER TABLE mkt_projects ADD COLUMN approval_mode TEXT NOT NULL DEFAULT 'any';
                    END IF;
                END $$;
            ''')
            # AI: context_window column on ai_agent.model_configs
            cursor.execute('''
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'ai_agent')
                       AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                                       WHERE table_schema = 'ai_agent'
                                       AND table_name = 'model_configs'
                                       AND column_name = 'context_window') THEN
                        ALTER TABLE ai_agent.model_configs ADD COLUMN context_window INTEGER DEFAULT 200000;
                        UPDATE ai_agent.model_configs SET context_window = 200000 WHERE model_name LIKE 'claude-%';
                        UPDATE ai_agent.model_configs SET context_window = 128000 WHERE model_name = 'gpt-4-turbo';
                        UPDATE ai_agent.model_configs SET context_window = 16385 WHERE model_name = 'gpt-3.5-turbo';
                        UPDATE ai_agent.model_configs SET context_window = 32768 WHERE model_name IN ('mixtral-8x7b-32768', 'gemini-pro');
                        UPDATE ai_agent.model_configs SET context_window = 128000 WHERE model_name = 'llama-3.3-70b-versatile';
                    END IF;
                END $$;
            ''')
            # ── Bilant (Balance Sheet) Generator tables ──
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bilant_templates (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
                    is_default BOOLEAN DEFAULT FALSE,
                    version INTEGER DEFAULT 1,
                    created_by INTEGER NOT NULL REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TIMESTAMP
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_templates_company ON bilant_templates(company_id)')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bilant_template_rows (
                    id SERIAL PRIMARY KEY,
                    template_id INTEGER NOT NULL REFERENCES bilant_templates(id) ON DELETE CASCADE,
                    description TEXT NOT NULL,
                    nr_rd TEXT,
                    formula_ct TEXT,
                    formula_rd TEXT,
                    row_type TEXT DEFAULT 'data',
                    is_bold BOOLEAN DEFAULT FALSE,
                    indent_level INTEGER DEFAULT 0,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_tpl_rows_template ON bilant_template_rows(template_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_tpl_rows_order ON bilant_template_rows(template_id, sort_order)')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bilant_metric_configs (
                    id SERIAL PRIMARY KEY,
                    template_id INTEGER NOT NULL REFERENCES bilant_templates(id) ON DELETE CASCADE,
                    metric_key TEXT NOT NULL,
                    metric_label TEXT NOT NULL,
                    nr_rd TEXT NOT NULL,
                    metric_group TEXT DEFAULT 'summary',
                    sort_order INTEGER DEFAULT 0,
                    CONSTRAINT bilant_metric_unique UNIQUE (template_id, metric_key)
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_metric_cfg_template ON bilant_metric_configs(template_id)')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bilant_generations (
                    id SERIAL PRIMARY KEY,
                    template_id INTEGER NOT NULL REFERENCES bilant_templates(id),
                    company_id INTEGER NOT NULL REFERENCES companies(id),
                    period_label TEXT,
                    period_date DATE,
                    status TEXT DEFAULT 'completed',
                    error_message TEXT,
                    original_filename TEXT,
                    generated_by INTEGER NOT NULL REFERENCES users(id),
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_gen_company ON bilant_generations(company_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_gen_date ON bilant_generations(period_date)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_gen_template ON bilant_generations(template_id)')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bilant_results (
                    id SERIAL PRIMARY KEY,
                    generation_id INTEGER NOT NULL REFERENCES bilant_generations(id) ON DELETE CASCADE,
                    template_row_id INTEGER REFERENCES bilant_template_rows(id) ON DELETE SET NULL,
                    nr_rd TEXT,
                    description TEXT,
                    formula_ct TEXT,
                    formula_rd TEXT,
                    value NUMERIC(15,2) DEFAULT 0,
                    verification TEXT,
                    sort_order INTEGER DEFAULT 0
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_results_gen ON bilant_results(generation_id)')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bilant_metrics (
                    id SERIAL PRIMARY KEY,
                    generation_id INTEGER NOT NULL REFERENCES bilant_generations(id) ON DELETE CASCADE,
                    metric_key TEXT NOT NULL,
                    metric_label TEXT NOT NULL,
                    metric_group TEXT NOT NULL,
                    value NUMERIC(15,4),
                    interpretation TEXT,
                    percent NUMERIC(7,2),
                    CONSTRAINT bilant_metric_gen_unique UNIQUE (generation_id, metric_key)
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_bilant_metrics_gen ON bilant_metrics(generation_id)')
            # ── Chart of Accounts (Plan de Conturi) ──
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
            # Seed standard Romanian chart of accounts (global, no company)
            cursor.execute("SELECT COUNT(*) as cnt FROM chart_of_accounts WHERE company_id IS NULL")
            if cursor.fetchone()['cnt'] == 0:
                from migrations.init_schema import _seed_chart_of_accounts
                _seed_chart_of_accounts(cursor)
            # Seed default Bilant template
            cursor.execute("SELECT COUNT(*) as cnt FROM bilant_templates")
            if cursor.fetchone()['cnt'] == 0:
                from migrations.init_schema import _seed_bilant_default_template
                _seed_bilant_default_template(cursor)
            # Dynamic metrics: add new columns to bilant_metric_configs
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
            # Seed ratio/derived/structure configs for default template if missing
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM bilant_metric_configs mc
                JOIN bilant_templates t ON t.id = mc.template_id
                WHERE t.is_default = TRUE AND mc.metric_group = 'ratio'
            """)
            if cursor.fetchone()['cnt'] == 0:
                from migrations.init_schema import _seed_bilant_dynamic_metrics
                _seed_bilant_dynamic_metrics(cursor)
            # Fix corrupted seed data from original export
            cursor.execute("""
                UPDATE bilant_template_rows SET formula_rd = NULL
                WHERE formula_rd ~ '^[a-z]'
            """)
            cursor.execute("""
                UPDATE bilant_template_rows SET row_type = 'data', is_bold = FALSE, indent_level = 1
                WHERE nr_rd IN ('19', '21', '95') AND row_type = 'total'
            """)
            # ── Migrate default bilant template from OMF to column B numbering ──
            # Check if migration needed: dividende row still has OMF nr_rd='36'
            cursor.execute("""
                SELECT tr.id FROM bilant_template_rows tr
                JOIN bilant_templates t ON t.id = tr.template_id
                WHERE t.is_default = TRUE AND tr.nr_rd = '36'
                  AND tr.description LIKE '%%dividende%%'
                LIMIT 1
            """)
            if cursor.fetchone():
                logger.info('Migrating default bilant template from OMF to column B numbering')
                cursor.execute("SELECT id FROM bilant_templates WHERE is_default = TRUE LIMIT 1")
                tpl = cursor.fetchone()
                if tpl:
                    tid = tpl['id']
                    # 1. Dividende row: OMF 36 → B '35a'
                    cursor.execute("""
                        UPDATE bilant_template_rows SET nr_rd = '35a'
                        WHERE template_id = %s AND nr_rd = '36'
                          AND description LIKE '%%dividende%%'
                    """, (tid,))
                    # 2. All rows with integer nr_rd >= 37: decrement by 1
                    cursor.execute(r"""
                        UPDATE bilant_template_rows
                        SET nr_rd = CAST(CAST(nr_rd AS INTEGER) - 1 AS TEXT)
                        WHERE template_id = %s
                          AND nr_rd ~ '^\d+$' AND CAST(nr_rd AS INTEGER) >= 37
                    """, (tid,))
                    # 3. Update formula_rd values (explicit by sort_order for reliability)
                    _formula_rd_b = {
                        43: '31+32+33+34+35+35a', 47: '37+38', 49: '30+36+39+40',
                        50: '43+44', 63: '45+46+47+48+49+50+51+52',
                        64: '41+43-53-70-73-76', 65: '25+44+54',
                        75: '56+57+58+59+60+61+62+63', 80: '65+66+67',
                        82: '70+71', 85: '73+74', 88: '76+77',
                        92: '69+72+75+78', 101: '80+81+82+83+84',
                        108: '88+89+90',
                        118: '85+86+87+91-92+93-94+95-96+97-98-99',
                        121: '100+101+102',
                    }
                    for so, frd in _formula_rd_b.items():
                        cursor.execute("""
                            UPDATE bilant_template_rows SET formula_rd = %s
                            WHERE template_id = %s AND sort_order = %s AND formula_rd IS NOT NULL
                        """, (frd, tid, so))
                    # 4. Update metric_configs nr_rd to correct B values
                    _metric_b = {
                        'active_imobilizate': '25', 'active_circulante': '41',
                        'stocuri': '30', 'creante': '36', 'disponibilitati': '40',
                        'datorii_termen_scurt': '53', 'datorii_termen_lung': '64',
                        'capitaluri_proprii': '100', 'capital_social': '80',
                        'struct_active_imobilizate': '25', 'struct_stocuri': '30',
                        'struct_creante': '36', 'struct_disponibilitati': '40',
                        'struct_capitaluri_proprii': '100', 'struct_datorii_scurt': '53',
                        'struct_datorii_lung': '64',
                    }
                    for mkey, b_nr in _metric_b.items():
                        cursor.execute("""
                            UPDATE bilant_metric_configs SET nr_rd = %s
                            WHERE template_id = %s AND metric_key = %s
                        """, (b_nr, tid, mkey))
                    # 5. Update existing bilant_results from OMF to B numbering
                    #    Dividende results: nr_rd '36' with dividende description → '35a'
                    cursor.execute("""
                        UPDATE bilant_results SET nr_rd = '35a'
                        WHERE nr_rd = '36' AND description LIKE '%%dividende%%'
                    """)
                    #    All results with integer nr_rd >= 37: decrement by 1
                    cursor.execute(r"""
                        UPDATE bilant_results
                        SET nr_rd = CAST(CAST(nr_rd AS INTEGER) - 1 AS TEXT)
                        WHERE nr_rd ~ '^\d+$' AND CAST(nr_rd AS INTEGER) >= 37
                    """)
                    #    Update formula_rd in results too
                    cursor.execute("""
                        UPDATE bilant_results br
                        SET formula_rd = tr.formula_rd
                        FROM bilant_template_rows tr
                        WHERE br.template_row_id = tr.id AND tr.formula_rd IS NOT NULL
                    """)
                    # 6. Recompute formula_rd values (they're stale after nr_rd shift)
                    _recompute_bilant_formula_values(cursor)
                    logger.info('Bilant template migrated to column B numbering')

            # ── Repair stale formula_rd values (runs if OMF→B migration already applied) ──
            cursor.execute("""
                SELECT DISTINCT br.generation_id
                FROM bilant_results br
                WHERE br.nr_rd = '35a'
                  AND EXISTS (
                      SELECT 1 FROM bilant_results br2
                      WHERE br2.generation_id = br.generation_id
                        AND br2.formula_rd IS NOT NULL
                  )
            """)
            repair_gens = [r['generation_id'] for r in cursor.fetchall()]
            if repair_gens:
                _recompute_bilant_formula_values(cursor)

            # ── AI Agent learning tables (message_feedback + learned_knowledge) ──
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'ai_agent' AND table_name = 'message_feedback'
                )
            """)
            if not cursor.fetchone()['exists']:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ai_agent.message_feedback (
                        id SERIAL PRIMARY KEY,
                        message_id INTEGER NOT NULL REFERENCES ai_agent.messages(id) ON DELETE CASCADE,
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        feedback_type VARCHAR(10) NOT NULL CHECK (feedback_type IN ('positive', 'negative')),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(message_id, user_id)
                    )
                """)
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_feedback_message ON ai_agent.message_feedback(message_id)')
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_positive ON ai_agent.message_feedback(feedback_type) WHERE feedback_type = 'positive'")
                # learned_knowledge with optional vector column
                cursor.execute("""
                    DO $$
                    BEGIN
                        CREATE TABLE IF NOT EXISTS ai_agent.learned_knowledge (
                            id SERIAL PRIMARY KEY,
                            pattern TEXT NOT NULL,
                            category VARCHAR(50) NOT NULL,
                            source_count INTEGER DEFAULT 1,
                            confidence FLOAT DEFAULT 0.5,
                            embedding vector(1536),
                            is_active BOOLEAN DEFAULT TRUE,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    EXCEPTION WHEN undefined_object THEN
                        CREATE TABLE IF NOT EXISTS ai_agent.learned_knowledge (
                            id SERIAL PRIMARY KEY,
                            pattern TEXT NOT NULL,
                            category VARCHAR(50) NOT NULL,
                            source_count INTEGER DEFAULT 1,
                            confidence FLOAT DEFAULT 0.5,
                            is_active BOOLEAN DEFAULT TRUE,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    END $$;
                """)
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_knowledge_active ON ai_agent.learned_knowledge(is_active, confidence DESC)')
                logger.info('Created AI agent learning tables (message_feedback, learned_knowledge)')

            # ── CRM / Car Sales Database tables ──
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'crm_import_batches'
                )
            """)
            if not cursor.fetchone()['exists']:
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS crm_import_batches (
                        id SERIAL PRIMARY KEY,
                        source_type VARCHAR(20) NOT NULL,
                        filename TEXT NOT NULL,
                        uploaded_by INTEGER REFERENCES users(id),
                        total_rows INTEGER DEFAULT 0,
                        new_rows INTEGER DEFAULT 0,
                        updated_rows INTEGER DEFAULT 0,
                        skipped_rows INTEGER DEFAULT 0,
                        new_clients INTEGER DEFAULT 0,
                        matched_clients INTEGER DEFAULT 0,
                        status VARCHAR(20) DEFAULT 'processing',
                        error_log JSONB DEFAULT '[]',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_import_source ON crm_import_batches(source_type)')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS crm_clients (
                        id SERIAL PRIMARY KEY,
                        display_name TEXT NOT NULL,
                        name_normalized TEXT NOT NULL,
                        client_type VARCHAR(20) DEFAULT 'person',
                        phone TEXT,
                        phone_raw TEXT,
                        email TEXT,
                        street TEXT,
                        city TEXT,
                        region TEXT,
                        country TEXT DEFAULT 'Romania',
                        company_name TEXT,
                        responsible TEXT,
                        source_flags JSONB DEFAULT '{}',
                        merged_into_id INTEGER REFERENCES crm_clients(id),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_clients_phone ON crm_clients(phone)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_clients_email ON crm_clients(email)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_clients_merged ON crm_clients(merged_into_id)')
                cursor.execute("""
                    DO $$ BEGIN
                        CREATE EXTENSION IF NOT EXISTS pg_trgm;
                    EXCEPTION WHEN OTHERS THEN NULL;
                    END $$;
                """)
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_clients_name ON crm_clients USING gin (name_normalized gin_trgm_ops)')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS crm_deals (
                        id SERIAL PRIMARY KEY,
                        client_id INTEGER REFERENCES crm_clients(id) ON DELETE SET NULL,
                        source VARCHAR(5) NOT NULL,
                        dealer_code TEXT, dealer_name TEXT, branch TEXT,
                        dossier_number TEXT, order_number TEXT,
                        contract_date DATE, order_date DATE, delivery_date DATE,
                        invoice_date DATE, registration_date DATE, entry_date DATE,
                        brand TEXT, model_name TEXT, model_code TEXT, model_year INTEGER, order_year INTEGER,
                        body_code TEXT, vin TEXT, engine_code TEXT, fuel_type TEXT,
                        color TEXT, color_code TEXT, door_count INTEGER, vehicle_type TEXT,
                        list_price NUMERIC(12,2), purchase_price_net NUMERIC(12,2),
                        sale_price_net NUMERIC(12,2), gross_profit NUMERIC(12,2),
                        discount_value NUMERIC(12,2), other_costs NUMERIC(12,2),
                        gw_gross_value NUMERIC(12,2),
                        dossier_status TEXT, order_status TEXT, contract_status TEXT,
                        sales_person TEXT, buyer_name TEXT, buyer_address TEXT,
                        owner_name TEXT, owner_address TEXT, customer_group TEXT,
                        registration_number TEXT,
                        vehicle_specs JSONB DEFAULT '{}',
                        import_batch_id INTEGER REFERENCES crm_import_batches(id),
                        source_row_hash TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_deals_client ON crm_deals(client_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_deals_source ON crm_deals(source)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_deals_vin ON crm_deals(vin)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_deals_brand ON crm_deals(brand)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_deals_dossier ON crm_deals(source, dossier_number)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_deals_contract ON crm_deals(contract_date DESC)')
                # Add can_access_crm permission to roles
                cursor.execute("""
                    DO $$ BEGIN
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                       WHERE table_name = 'roles' AND column_name = 'can_access_crm') THEN
                            ALTER TABLE roles ADD COLUMN can_access_crm BOOLEAN DEFAULT FALSE;
                            UPDATE roles SET can_access_crm = TRUE WHERE name = 'Admin';
                        END IF;
                    END $$;
                """)
                logger.info('Created CRM tables (crm_import_batches, crm_clients, crm_deals)')

            # CRM: nr_reg column on crm_clients
            cursor.execute('''
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name = 'crm_clients' AND column_name = 'nr_reg') THEN
                        ALTER TABLE crm_clients ADD COLUMN nr_reg TEXT;
                    END IF;
                END $$;
            ''')
            # CRM: is_blacklisted column on crm_clients
            cursor.execute('''
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                   WHERE table_name = 'crm_clients' AND column_name = 'is_blacklisted') THEN
                        ALTER TABLE crm_clients ADD COLUMN is_blacklisted BOOLEAN DEFAULT FALSE;
                    END IF;
                END $$;
            ''')
            # ── DMS (Document Management System) tables ──
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS dms_categories (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    icon TEXT DEFAULT 'bi-folder',
                    color TEXT DEFAULT '#6c757d',
                    description TEXT,
                    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
                    sort_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_by INTEGER REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'dms_categories_slug_company'
                    ) THEN
                        ALTER TABLE dms_categories ADD CONSTRAINT dms_categories_slug_company
                            UNIQUE (slug, company_id);
                    END IF;
                EXCEPTION WHEN others THEN NULL;
                END $$;
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_dms_categories_company ON dms_categories(company_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_dms_categories_active ON dms_categories(is_active, sort_order)')

            # Category permissions (NULL = all roles can see)
            cursor.execute('''
                DO $$ BEGIN
                    ALTER TABLE dms_categories ADD COLUMN allowed_role_ids INTEGER[] DEFAULT NULL;
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$;
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS dms_documents (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    category_id INTEGER REFERENCES dms_categories(id) ON DELETE SET NULL,
                    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                    status TEXT NOT NULL DEFAULT 'draft',
                    parent_id INTEGER REFERENCES dms_documents(id) ON DELETE CASCADE,
                    relationship_type TEXT,
                    metadata JSONB DEFAULT '{}'::jsonb,
                    doc_number TEXT,
                    doc_date DATE,
                    expiry_date DATE,
                    notify_user_id INTEGER REFERENCES users(id),
                    created_by INTEGER NOT NULL REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TIMESTAMP,
                    CONSTRAINT dms_doc_status CHECK (status IN ('draft','active','archived')),
                    CONSTRAINT dms_doc_parent_child CHECK (
                        (parent_id IS NULL AND relationship_type IS NULL) OR
                        (parent_id IS NOT NULL AND relationship_type IS NOT NULL)
                    )
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_dms_documents_category ON dms_documents(category_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_dms_documents_company ON dms_documents(company_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_dms_documents_parent ON dms_documents(parent_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_dms_documents_status ON dms_documents(status) WHERE deleted_at IS NULL')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_dms_documents_created ON dms_documents(created_at DESC)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_dms_documents_expiry ON dms_documents(expiry_date) WHERE expiry_date IS NOT NULL')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_dms_documents_doc_number ON dms_documents(doc_number) WHERE doc_number IS NOT NULL')

            # Add columns if upgrading from earlier schema
            for col, coldef in [
                ('doc_number', 'TEXT'),
                ('doc_date', 'DATE'),
                ('expiry_date', 'DATE'),
                ('notify_user_id', 'INTEGER REFERENCES users(id)'),
                ('visibility', "TEXT DEFAULT 'all'"),
                ('allowed_role_ids', 'INTEGER[] DEFAULT NULL'),
                ('allowed_user_ids', 'INTEGER[] DEFAULT NULL'),
            ]:
                cursor.execute(f'''
                    DO $$ BEGIN
                        ALTER TABLE dms_documents ADD COLUMN {col} {coldef};
                    EXCEPTION WHEN duplicate_column THEN NULL;
                    END $$;
                ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS dms_files (
                    id SERIAL PRIMARY KEY,
                    document_id INTEGER NOT NULL REFERENCES dms_documents(id) ON DELETE CASCADE,
                    file_name TEXT NOT NULL,
                    file_type TEXT,
                    mime_type TEXT,
                    file_size INTEGER,
                    storage_type TEXT NOT NULL DEFAULT 'drive',
                    storage_uri TEXT NOT NULL,
                    drive_file_id TEXT,
                    uploaded_by INTEGER NOT NULL REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT dms_file_storage CHECK (storage_type IN ('drive','local'))
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_dms_files_document ON dms_files(document_id)')

            # ── dms_relationship_types ──
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS dms_relationship_types (
                    id SERIAL PRIMARY KEY,
                    slug TEXT NOT NULL UNIQUE,
                    label TEXT NOT NULL,
                    icon TEXT DEFAULT 'bi-file-earmark',
                    color TEXT DEFAULT '#6c757d',
                    sort_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Drop old hardcoded CHECK on relationship_type (now dynamic via table)
            cursor.execute('''
                ALTER TABLE dms_documents DROP CONSTRAINT IF EXISTS dms_doc_rel_type
            ''')

            # ── Signature columns on dms_documents (Phase A) ──
            for col, coldef in [
                ('signature_status', 'TEXT'),
                ('signature_request_id', 'TEXT'),
                ('signature_requested_at', 'TIMESTAMP'),
                ('signature_completed_at', 'TIMESTAMP'),
                ('signature_provider', 'TEXT'),
            ]:
                cursor.execute(f'''
                    DO $$ BEGIN
                        ALTER TABLE dms_documents ADD COLUMN {col} {coldef};
                    EXCEPTION WHEN duplicate_column THEN NULL;
                    END $$;
                ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_dms_documents_sig_status
                ON dms_documents(signature_status)
                WHERE signature_status IS NOT NULL
            ''')

            # ── document_parties (Phase B) ──
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS document_parties (
                    id SERIAL PRIMARY KEY,
                    document_id INTEGER NOT NULL REFERENCES dms_documents(id) ON DELETE CASCADE,
                    party_role TEXT NOT NULL,
                    entity_type TEXT NOT NULL DEFAULT 'company',
                    entity_id INTEGER,
                    entity_name TEXT NOT NULL,
                    entity_details JSONB DEFAULT '{}'::jsonb,
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_document_parties_doc ON document_parties(document_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_document_parties_entity ON document_parties(entity_type, entity_id)')

            # ── suppliers (master table) ──
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS suppliers (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    supplier_type TEXT NOT NULL DEFAULT 'company',
                    cui TEXT,
                    j_number TEXT,
                    address TEXT,
                    city TEXT,
                    bank_account TEXT,
                    iban TEXT,
                    bank_name TEXT,
                    phone TEXT,
                    email TEXT,
                    company_id INTEGER REFERENCES companies(id),
                    created_by INTEGER REFERENCES users(id),
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_suppliers_company ON suppliers(company_id)')
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_suppliers_name ON suppliers USING gin (name gin_trgm_ops)")
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_suppliers_active ON suppliers(is_active)')

            # ── document_wml + chunks (Phase D) ──
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS document_wml (
                    id SERIAL PRIMARY KEY,
                    document_id INTEGER NOT NULL REFERENCES dms_documents(id) ON DELETE CASCADE,
                    file_id INTEGER NOT NULL REFERENCES dms_files(id) ON DELETE CASCADE,
                    raw_text TEXT,
                    structured_json JSONB,
                    extraction_method TEXT DEFAULT 'mammoth',
                    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(file_id)
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_wml_document ON document_wml(document_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_wml_file ON document_wml(file_id)')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS document_wml_chunks (
                    id SERIAL PRIMARY KEY,
                    wml_id INTEGER NOT NULL REFERENCES document_wml(id) ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL,
                    heading TEXT,
                    content TEXT NOT NULL,
                    token_count INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_wml_chunks_wml ON document_wml_chunks(wml_id)')
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_wml_chunks_fts ON document_wml_chunks USING GIN (to_tsvector('simple', content))")

            # ── DMS Drive Sync ──
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS dms_drive_sync (
                    id SERIAL PRIMARY KEY,
                    document_id INTEGER NOT NULL REFERENCES dms_documents(id) ON DELETE CASCADE,
                    drive_folder_id TEXT NOT NULL,
                    drive_folder_url TEXT,
                    last_synced_at TIMESTAMP,
                    sync_status TEXT DEFAULT 'pending',
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(document_id)
                )
            ''')

            # Seed default relationship types
            cursor.execute('SELECT COUNT(*) as cnt FROM dms_relationship_types')
            if cursor.fetchone()['cnt'] == 0:
                cursor.execute('''
                    INSERT INTO dms_relationship_types (slug, label, icon, color, sort_order) VALUES
                    ('annex', 'Anexe', 'bi-paperclip', '#0d6efd', 1),
                    ('deviz', 'Devize', 'bi-calculator', '#fd7e14', 2),
                    ('proof', 'Dovezi / Foto', 'bi-camera', '#198754', 3),
                    ('other', 'Altele', 'bi-file-earmark', '#6c757d', 4)
                ''')

            # Seed default DMS categories (global — company_id NULL)
            cursor.execute('SELECT COUNT(*) as cnt FROM dms_categories')
            if cursor.fetchone()['cnt'] == 0:
                cursor.execute('''
                    INSERT INTO dms_categories (name, slug, icon, color, description, company_id, sort_order, is_active) VALUES
                    ('Contracte', 'contracte', 'bi-file-earmark-text', '#0d6efd', 'Contracte si acorduri', NULL, 1, TRUE),
                    ('Facturi', 'facturi', 'bi-receipt', '#198754', 'Facturi furnizori si clienti', NULL, 2, TRUE),
                    ('Autorizatii', 'autorizatii', 'bi-shield-check', '#6f42c1', 'Autorizatii si licente', NULL, 3, TRUE),
                    ('Devize', 'devize', 'bi-calculator', '#fd7e14', 'Devize si estimari de cost', NULL, 4, TRUE),
                    ('Documente HR', 'documente-hr', 'bi-person-badge', '#d63384', 'Documente resurse umane', NULL, 5, TRUE),
                    ('Altele', 'altele', 'bi-folder2-open', '#6c757d', 'Alte documente', NULL, 6, TRUE)
                ''')

            # Seed DMS permissions
            cursor.execute("SELECT COUNT(*) as cnt FROM permissions_v2 WHERE module_key = 'dms'")
            if cursor.fetchone()['cnt'] == 0:
                cursor.execute('''
                    INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order) VALUES
                    ('dms', 'Documents', 'bi-folder', 'document', 'Documents', 'view', 'View', 'View documents', TRUE, 1),
                    ('dms', 'Documents', 'bi-folder', 'document', 'Documents', 'create', 'Create', 'Upload and create documents', TRUE, 2),
                    ('dms', 'Documents', 'bi-folder', 'document', 'Documents', 'edit', 'Edit', 'Edit documents and metadata', TRUE, 3),
                    ('dms', 'Documents', 'bi-folder', 'document', 'Documents', 'delete', 'Delete', 'Delete documents', TRUE, 4),
                    ('dms', 'Documents', 'bi-folder', 'category', 'Categories', 'view', 'View', 'View document categories', FALSE, 5),
                    ('dms', 'Documents', 'bi-folder', 'category', 'Categories', 'manage', 'Manage', 'Create and edit categories', FALSE, 6)
                ''')
                # Grant DMS permissions to existing roles
                cursor.execute('SELECT id, name FROM roles')
                roles_for_dms = cursor.fetchall()
                cursor.execute("SELECT id, is_scope_based, action_key FROM permissions_v2 WHERE module_key = 'dms'")
                dms_perms = cursor.fetchall()
                for role in roles_for_dms:
                    for perm in dms_perms:
                        if role['name'] == 'Admin':
                            scope, granted = 'all', True
                        elif role['name'] == 'Manager':
                            scope, granted = ('all' if perm['is_scope_based'] else 'all'), True
                        elif role['name'] == 'User':
                            if perm['action_key'] in ('view', 'create', 'edit'):
                                scope = 'own' if perm['is_scope_based'] else 'own'
                                granted = True
                            else:
                                scope, granted = 'deny', False
                        else:
                            if perm['action_key'] == 'view':
                                scope, granted = ('own' if perm['is_scope_based'] else 'own'), True
                            else:
                                scope, granted = 'deny', False
                        cursor.execute('''
                            INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (role_id, permission_id) DO NOTHING
                        ''', (role['id'], perm['id'], scope, granted))

            # Seed supplier permissions (incremental — safe to re-run)
            cursor.execute("SELECT COUNT(*) as cnt FROM permissions_v2 WHERE module_key = 'dms' AND entity_key = 'supplier'")
            if cursor.fetchone()['cnt'] == 0:
                cursor.execute('''
                    INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order) VALUES
                    ('dms', 'Documents', 'bi-folder', 'supplier', 'Suppliers', 'view', 'View', 'View supplier list', FALSE, 7),
                    ('dms', 'Documents', 'bi-folder', 'supplier', 'Suppliers', 'manage', 'Manage', 'Manage supplier list', FALSE, 8)
                ''')
                # Grant supplier permissions to Admin + Manager
                cursor.execute('SELECT id, name FROM roles')
                roles_for_sup = cursor.fetchall()
                cursor.execute("SELECT id, action_key FROM permissions_v2 WHERE module_key = 'dms' AND entity_key = 'supplier'")
                sup_perms = cursor.fetchall()
                for role in roles_for_sup:
                    for perm in sup_perms:
                        if role['name'] in ('Admin', 'Manager'):
                            scope, granted = 'all', True
                        else:
                            scope = 'all' if perm['action_key'] == 'view' else 'deny'
                            granted = perm['action_key'] == 'view'
                        cursor.execute('''
                            INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (role_id, permission_id) DO NOTHING
                        ''', (role['id'], perm['id'], scope, granted))

            # ── Menu items: add 'archived' status + sync from registry ──
            cursor.execute("""
                DO $$ BEGIN
                    ALTER TABLE module_menu_items DROP CONSTRAINT IF EXISTS module_menu_items_status_check;
                    ALTER TABLE module_menu_items ADD CONSTRAINT module_menu_items_status_check
                        CHECK (status IN ('active', 'coming_soon', 'hidden', 'archived'));
                EXCEPTION WHEN others THEN NULL;
                END $$;
            """)
            # Sync menu items from registry (single source of truth)
            from core.settings.menus.registry import sync_menu_items
            sync_menu_items(cursor)

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
