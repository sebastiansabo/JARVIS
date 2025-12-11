import os
import json
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash

# PostgreSQL connection - DATABASE_URL is required
DATABASE_URL = os.environ.get('DATABASE_URL')

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required. Set it to your PostgreSQL connection string.")

# Connection pool configuration
# minconn: minimum connections kept open
# maxconn: maximum connections allowed (DigitalOcean managed DB allows ~25)
_connection_pool = None


def _get_pool():
    """Get or create the connection pool (lazy initialization)."""
    global _connection_pool
    if _connection_pool is None:
        # Add keepalive options to prevent connections from being dropped
        # by the server after idle timeout
        _connection_pool = pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=50,
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
    """
    conn = _get_pool().getconn()

    # Check if connection is still alive
    try:
        # Use a lightweight query to test connection
        conn.cursor().execute('SELECT 1')
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        # Connection is dead - close it and get a fresh one
        try:
            _get_pool().putconn(conn, close=True)
        except Exception:
            pass
        conn = _get_pool().getconn()

    return conn


def release_db(conn):
    """Return connection to pool."""
    if conn and _connection_pool:
        _connection_pool.putconn(conn)


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
            deleted_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
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

    # Add manager_ids and marketing_ids columns if they don't exist
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

    # Roles table - defines permission sets
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS roles (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            can_add_invoices BOOLEAN DEFAULT FALSE,
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

    # Add password_hash and last_login columns if they don't exist (migration)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'password_hash') THEN
                ALTER TABLE users ADD COLUMN password_hash TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'last_login') THEN
                ALTER TABLE users ADD COLUMN last_login TIMESTAMP;
            END IF;
        END $$;
    ''')

    # Insert default roles if they don't exist
    cursor.execute('''
        INSERT INTO roles (name, description, can_add_invoices, can_delete_invoices, can_view_invoices,
                          can_access_accounting, can_access_settings, can_access_connectors, can_access_templates)
        VALUES
            ('Admin', 'Full access to all features', TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE),
            ('Manager', 'Can manage invoices and view reports', TRUE, TRUE, TRUE, TRUE, FALSE, TRUE, TRUE),
            ('User', 'Can add and view invoices', TRUE, FALSE, TRUE, TRUE, FALSE, FALSE, FALSE),
            ('Viewer', 'Read-only access to invoices', FALSE, FALSE, TRUE, TRUE, FALSE, FALSE, FALSE)
        ON CONFLICT (name) DO NOTHING
    ''')

    # Responsables table - people responsible for departments who receive notifications
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS responsables (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT,
            departments TEXT,
            notify_on_allocation BOOLEAN DEFAULT TRUE,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
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

    # Create indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(invoice_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_allocations_company ON allocations(company)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_allocations_department ON allocations(department)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_events_user_id ON user_events(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_events_event_type ON user_events(event_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_events_created_at ON user_events(created_at DESC)')

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
    exchange_rate: float = None
) -> int:
    """
    Save invoice and its allocations to database.
    Returns the invoice ID.
    """
    conn = get_db()
    cursor = get_cursor(conn)

    try:
        cursor.execute('''
            INSERT INTO invoices (supplier, invoice_template, invoice_number, invoice_date, invoice_value, currency, drive_link, value_ron, value_eur, exchange_rate)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (supplier, invoice_template, invoice_number, invoice_date, invoice_value, currency, drive_link, value_ron, value_eur, exchange_rate))
        invoice_id = cursor.fetchone()['id']

        # Insert allocations
        for dist in distributions:
            allocation_value = invoice_value * dist['allocation']
            cursor.execute('''
                INSERT INTO allocations (invoice_id, company, brand, department, subdepartment, allocation_percent, allocation_value, responsible, reinvoice_to, reinvoice_brand, reinvoice_department, reinvoice_subdepartment, locked)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                invoice_id,
                dist['company'],
                dist.get('brand'),
                dist['department'],
                dist.get('subdepartment'),
                dist['allocation'] * 100,
                allocation_value,
                dist.get('responsible', ''),
                dist.get('reinvoice_to'),
                dist.get('reinvoice_brand'),
                dist.get('reinvoice_department'),
                dist.get('reinvoice_subdepartment'),
                dist.get('locked', False)
            ))

        conn.commit()
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
                     brand: Optional[str] = None, include_deleted: bool = False) -> list[dict]:
    """Get all invoices with pagination and optional filtering by allocation fields.

    By default, deleted invoices (with deleted_at set) are excluded.
    Set include_deleted=True to get only deleted invoices (for the bin view).
    """
    conn = get_db()
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

    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)

    query += ' ORDER BY i.created_at DESC LIMIT %s OFFSET %s'
    params.extend([limit, offset])

    cursor.execute(query, params)
    invoices = [dict_from_row(row) for row in cursor.fetchall()]
    release_db(conn)
    return invoices


def get_invoice_with_allocations(invoice_id: int) -> Optional[dict]:
    """Get invoice with all its allocations."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('SELECT * FROM invoices WHERE id = %s', (invoice_id,))
    invoice = cursor.fetchone()

    if not invoice:
        release_db(conn)
        return None

    invoice = dict_from_row(invoice)

    cursor.execute('SELECT * FROM allocations WHERE invoice_id = %s', (invoice_id,))
    invoice['allocations'] = [dict_from_row(row) for row in cursor.fetchall()]

    release_db(conn)
    return invoice


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
    """Get total allocation values grouped by company."""
    conn = get_db()
    cursor = get_cursor(conn)

    query = '''
        SELECT a.company, SUM(a.allocation_value) as total_value, COUNT(DISTINCT a.invoice_id) as invoice_count
        FROM allocations a
        JOIN invoices i ON a.invoice_id = i.id
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
        query += ' WHERE ' + ' AND '.join(conditions)

    query += ' GROUP BY a.company ORDER BY total_value DESC'

    cursor.execute(query, params)
    results = [dict_from_row(row) for row in cursor.fetchall()]
    release_db(conn)
    return results


def get_summary_by_department(company: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None,
                              department: Optional[str] = None, subdepartment: Optional[str] = None,
                              brand: Optional[str] = None) -> list[dict]:
    """Get total allocation values grouped by department."""
    conn = get_db()
    cursor = get_cursor(conn)

    query = '''
        SELECT a.company, a.department, a.subdepartment, SUM(a.allocation_value) as total_value, COUNT(DISTINCT a.invoice_id) as invoice_count
        FROM allocations a
        JOIN invoices i ON a.invoice_id = i.id
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
        query += ' WHERE ' + ' AND '.join(conditions)

    query += ' GROUP BY a.company, a.department, a.subdepartment ORDER BY total_value DESC'

    cursor.execute(query, params)
    results = [dict_from_row(row) for row in cursor.fetchall()]
    release_db(conn)
    return results


def get_summary_by_brand(company: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None,
                         department: Optional[str] = None, subdepartment: Optional[str] = None,
                         brand: Optional[str] = None) -> list[dict]:
    """Get total allocation values grouped by brand (Linie de business) with invoice details."""
    conn = get_db()
    cursor = get_cursor(conn)

    query = '''
        SELECT a.brand,
               SUM(a.allocation_value) as total_value,
               COUNT(DISTINCT a.invoice_id) as invoice_count,
               STRING_AGG(DISTINCT i.invoice_number, ', ') as invoice_numbers,
               JSON_AGG(JSON_BUILD_OBJECT(
                   'department', a.department,
                   'subdepartment', a.subdepartment,
                   'brand', a.brand,
                   'value', a.allocation_value,
                   'percent', ROUND(a.allocation_percent),
                   'reinvoice_to', a.reinvoice_to,
                   'reinvoice_brand', a.reinvoice_brand,
                   'reinvoice_department', a.reinvoice_department,
                   'reinvoice_subdepartment', a.reinvoice_subdepartment
               )) as split_values
        FROM allocations a
        JOIN invoices i ON a.invoice_id = i.id
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
        query += ' WHERE ' + ' AND '.join(conditions)

    query += ' GROUP BY a.brand ORDER BY total_value DESC'

    cursor.execute(query, params)
    results = [dict_from_row(row) for row in cursor.fetchall()]
    release_db(conn)
    return results


def delete_invoice(invoice_id: int) -> bool:
    """Soft delete an invoice (move to bin)."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('UPDATE invoices SET deleted_at = CURRENT_TIMESTAMP WHERE id = %s AND deleted_at IS NULL', (invoice_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    release_db(conn)
    return deleted


def restore_invoice(invoice_id: int) -> bool:
    """Restore a soft-deleted invoice from the bin."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('UPDATE invoices SET deleted_at = NULL WHERE id = %s AND deleted_at IS NOT NULL', (invoice_id,))
    restored = cursor.rowcount > 0

    conn.commit()
    release_db(conn)
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
    comment: str = None
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


def search_invoices(query: str) -> list[dict]:
    """Search invoices by supplier or invoice number."""
    conn = get_db()
    cursor = get_cursor(conn)

    search_term = f'%{query}%'
    cursor.execute('''
        SELECT * FROM invoices
        WHERE supplier LIKE %s OR invoice_number LIKE %s
        ORDER BY created_at DESC
        LIMIT 50
    ''', (search_term, search_term))

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
    reinvoice_subdepartment: str = None
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
        cursor.execute('SELECT invoice_value FROM invoices WHERE id = %s', (invoice_id,))
        result = cursor.fetchone()
        if not result:
            raise ValueError(f"Invoice {invoice_id} not found")
        invoice_value = result['invoice_value']

        # Delete existing allocations
        cursor.execute('DELETE FROM allocations WHERE invoice_id = %s', (invoice_id,))

        # Insert new allocations
        for alloc in allocations:
            allocation_percent = alloc['allocation_percent']
            # Calculate value from percent if not provided
            allocation_value = alloc.get('allocation_value') or (invoice_value * allocation_percent / 100)

            cursor.execute('''
                INSERT INTO allocations (invoice_id, company, brand, department, subdepartment,
                    allocation_percent, allocation_value, responsible, reinvoice_to, reinvoice_brand, reinvoice_department, reinvoice_subdepartment, locked)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                alloc.get('locked', False)
            ))

        conn.commit()
        return True
    except Exception as e:
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
    return updated


def delete_invoice_template(template_id: int) -> bool:
    """Delete an invoice template."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('DELETE FROM invoice_templates WHERE id = %s', (template_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    release_db(conn)
    return deleted


def get_all_invoice_templates() -> list[dict]:
    """Get all invoice templates."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('SELECT * FROM invoice_templates ORDER BY name')
    templates = [dict_from_row(row) for row in cursor.fetchall()]

    release_db(conn)
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
    can_delete_invoices: bool = False,
    can_view_invoices: bool = False,
    can_access_accounting: bool = False,
    can_access_settings: bool = False,
    can_access_connectors: bool = False,
    can_access_templates: bool = False
) -> int:
    """Save a new role. Returns role ID."""
    conn = get_db()
    cursor = get_cursor(conn)

    try:
        cursor.execute('''
            INSERT INTO roles (name, description, can_add_invoices, can_delete_invoices,
                can_view_invoices, can_access_accounting, can_access_settings,
                can_access_connectors, can_access_templates)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            name, description, can_add_invoices, can_delete_invoices,
            can_view_invoices, can_access_accounting, can_access_settings,
            can_access_connectors, can_access_templates
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
    can_delete_invoices: bool = None,
    can_view_invoices: bool = None,
    can_access_accounting: bool = None,
    can_access_settings: bool = None,
    can_access_connectors: bool = None,
    can_access_templates: bool = None
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
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT u.*, r.name as role_name, r.description as role_description,
               r.can_add_invoices, r.can_delete_invoices, r.can_view_invoices,
               r.can_access_accounting, r.can_access_settings, r.can_access_connectors,
               r.can_access_templates
        FROM users u
        LEFT JOIN roles r ON u.role_id = r.id
        WHERE u.id = %s
    ''', (user_id,))
    user = cursor.fetchone()

    release_db(conn)
    return dict_from_row(user) if user else None


def get_user_by_email(email: str) -> Optional[dict]:
    """Get a user by email address with role information."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT u.*, r.name as role_name, r.description as role_description,
               r.can_add_invoices, r.can_delete_invoices, r.can_view_invoices,
               r.can_access_accounting, r.can_access_settings, r.can_access_connectors,
               r.can_access_templates
        FROM users u
        LEFT JOIN roles r ON u.role_id = r.id
        WHERE u.email = %s
    ''', (email,))
    user = cursor.fetchone()

    release_db(conn)
    return dict_from_row(user) if user else None


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
    """Get all responsables."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT * FROM responsables
        ORDER BY name
    ''')

    results = [dict_from_row(row) for row in cursor.fetchall()]
    release_db(conn)
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
    """Get responsables assigned to a specific department."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT * FROM responsables
        WHERE departments LIKE %s AND is_active = TRUE AND notify_on_allocation = TRUE
    ''', (f'%{department}%',))

    results = [dict_from_row(row) for row in cursor.fetchall()]
    release_db(conn)
    return results


def save_responsable(name: str, email: str, phone: str = None, departments: str = None,
                     notify_on_allocation: bool = True, is_active: bool = True) -> int:
    """Create a new responsable."""
    conn = get_db()
    cursor = get_cursor(conn)

    try:
        cursor.execute('''
            INSERT INTO responsables (name, email, phone, departments, notify_on_allocation, is_active)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (name, email, phone, departments, notify_on_allocation, is_active))

        responsable_id = cursor.fetchone()['id']
        conn.commit()
        return responsable_id
    except Exception as e:
        conn.rollback()
        if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
            raise ValueError(f"Responsable with email '{email}' already exists")
        raise
    finally:
        release_db(conn)


def update_responsable(responsable_id: int, name: str = None, email: str = None, phone: str = None,
                       departments: str = None, notify_on_allocation: bool = None, is_active: bool = None) -> bool:
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
    """Get all companies."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT * FROM companies
        ORDER BY company
    ''')

    results = [dict_from_row(row) for row in cursor.fetchall()]
    release_db(conn)
    return results


def get_company(company_id: int) -> Optional[dict]:
    """Get a specific company by ID."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('SELECT * FROM companies WHERE id = %s', (company_id,))
    row = cursor.fetchone()

    release_db(conn)
    return dict_from_row(row) if row else None


def save_company(company: str, brands: str = None, vat: str = None) -> int:
    """Create a new company."""
    conn = get_db()
    cursor = get_cursor(conn)

    try:
        cursor.execute('''
            INSERT INTO companies (company, brands, vat)
            VALUES (%s, %s, %s)
            RETURNING id
        ''', (company, brands, vat))

        company_id = cursor.fetchone()['id']
        conn.commit()
        return company_id
    except Exception as e:
        conn.rollback()
        if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
            raise ValueError(f"Company '{company}' already exists")
        raise
    finally:
        release_db(conn)


def update_company(company_id: int, company: str = None, brands: str = None, vat: str = None) -> bool:
    """Update a company."""
    conn = get_db()
    cursor = get_cursor(conn)

    updates = []
    params = []

    if company is not None:
        updates.append('company = %s')
        params.append(company)
    if brands is not None:
        updates.append('brands = %s')
        params.append(brands)
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
                               manager_ids: list = None, marketing_ids: list = None) -> int:
    """Create a new department structure entry."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        INSERT INTO department_structure (company, brand, department, subdepartment, manager, marketing, responsable_id, manager_ids, marketing_ids)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    ''', (company, brand, department, subdepartment, manager, marketing, responsable_id, manager_ids, marketing_ids))

    structure_id = cursor.fetchone()['id']
    conn.commit()
    release_db(conn)
    return structure_id


def update_department_structure(structure_id: int, company: str = None, department: str = None,
                                 brand: str = None, subdepartment: str = None, manager: str = None,
                                 marketing: str = None, responsable_id: int = None,
                                 manager_ids: list = None, marketing_ids: list = None) -> bool:
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


# Initialize database on import
init_db()
