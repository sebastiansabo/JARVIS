import sqlite3
import os
from datetime import datetime
from typing import Optional
from config import BASE_DIR

# Use DATA_DIR env var for persistent storage (DigitalOcean), fallback to BASE_DIR
DATA_DIR = os.environ.get('DATA_DIR', BASE_DIR)
DATABASE_PATH = os.path.join(DATA_DIR, 'invoices.db')


def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables."""
    conn = get_db()
    cursor = conn.cursor()

    # Invoices table - main invoice record
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier TEXT NOT NULL,
            invoice_template TEXT,
            invoice_number TEXT NOT NULL,
            invoice_date DATE NOT NULL,
            invoice_value REAL NOT NULL,
            currency TEXT DEFAULT 'RON',
            drive_link TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(invoice_number)
        )
    ''')

    # Allocations table - distribution of invoice costs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS allocations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            company TEXT NOT NULL,
            brand TEXT,
            department TEXT NOT NULL,
            subdepartment TEXT,
            allocation_percent REAL NOT NULL,
            allocation_value REAL NOT NULL,
            responsible TEXT,
            reinvoice_to TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
        )
    ''')

    # Add reinvoice_to column if it doesn't exist (for existing databases)
    try:
        cursor.execute('ALTER TABLE allocations ADD COLUMN reinvoice_to TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Index for faster queries
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(invoice_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_allocations_company ON allocations(company)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_allocations_department ON allocations(department)')

    # Invoice templates table - for bypassing AI parsing
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invoice_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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

    # Add new columns to invoice_templates if they don't exist (for existing databases)
    new_columns = [
        ('template_type', 'TEXT DEFAULT \'fixed\''),
        ('supplier_regex', 'TEXT'),
        ('supplier_vat_regex', 'TEXT'),
        ('customer_vat_regex', 'TEXT'),
        ('currency_regex', 'TEXT')
    ]
    for col_name, col_type in new_columns:
        try:
            cursor.execute(f'ALTER TABLE invoice_templates ADD COLUMN {col_name} {col_type}')
        except sqlite3.OperationalError:
            pass  # Column already exists

    conn.commit()
    conn.close()


def save_invoice(
    supplier: str,
    invoice_template: str,
    invoice_number: str,
    invoice_date: str,
    invoice_value: float,
    currency: str,
    drive_link: str,
    distributions: list[dict]
) -> int:
    """
    Save invoice and its allocations to database.
    Returns the invoice ID.
    """
    conn = get_db()
    cursor = conn.cursor()

    try:
        # Insert invoice
        cursor.execute('''
            INSERT INTO invoices (supplier, invoice_template, invoice_number, invoice_date, invoice_value, currency, drive_link)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (supplier, invoice_template, invoice_number, invoice_date, invoice_value, currency, drive_link))

        invoice_id = cursor.lastrowid

        # Insert allocations
        for dist in distributions:
            allocation_value = invoice_value * dist['allocation']
            cursor.execute('''
                INSERT INTO allocations (invoice_id, company, brand, department, subdepartment, allocation_percent, allocation_value, responsible, reinvoice_to)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                invoice_id,
                dist['company'],
                dist.get('brand'),
                dist['department'],
                dist.get('subdepartment'),
                dist['allocation'] * 100,
                allocation_value,
                dist.get('responsible', ''),
                dist.get('reinvoice_to')
            ))

        conn.commit()
        return invoice_id

    except sqlite3.IntegrityError as e:
        conn.rollback()
        raise ValueError(f"Invoice {invoice_number} already exists in database")
    finally:
        conn.close()


def get_all_invoices(limit: int = 100, offset: int = 0) -> list[dict]:
    """Get all invoices with pagination."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM invoices
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    ''', (limit, offset))

    invoices = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return invoices


def get_invoice_with_allocations(invoice_id: int) -> Optional[dict]:
    """Get invoice with all its allocations."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM invoices WHERE id = ?', (invoice_id,))
    invoice = cursor.fetchone()

    if not invoice:
        conn.close()
        return None

    invoice = dict(invoice)

    cursor.execute('SELECT * FROM allocations WHERE invoice_id = ?', (invoice_id,))
    invoice['allocations'] = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return invoice


def get_allocations_by_company(company: str) -> list[dict]:
    """Get all allocations for a specific company."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT a.*, i.supplier, i.invoice_number, i.invoice_date
        FROM allocations a
        JOIN invoices i ON a.invoice_id = i.id
        WHERE a.company = ?
        ORDER BY i.invoice_date DESC
    ''', (company,))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def get_allocations_by_department(company: str, department: str) -> list[dict]:
    """Get all allocations for a specific department."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT a.*, i.supplier, i.invoice_number, i.invoice_date
        FROM allocations a
        JOIN invoices i ON a.invoice_id = i.id
        WHERE a.company = ? AND a.department = ?
        ORDER BY i.invoice_date DESC
    ''', (company, department))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def get_summary_by_company(start_date: Optional[str] = None, end_date: Optional[str] = None) -> list[dict]:
    """Get total allocation values grouped by company."""
    conn = get_db()
    cursor = conn.cursor()

    query = '''
        SELECT a.company, SUM(a.allocation_value) as total_value, COUNT(DISTINCT a.invoice_id) as invoice_count
        FROM allocations a
        JOIN invoices i ON a.invoice_id = i.id
    '''
    params = []

    if start_date or end_date:
        conditions = []
        if start_date:
            conditions.append('i.invoice_date >= ?')
            params.append(start_date)
        if end_date:
            conditions.append('i.invoice_date <= ?')
            params.append(end_date)
        query += ' WHERE ' + ' AND '.join(conditions)

    query += ' GROUP BY a.company ORDER BY total_value DESC'

    cursor.execute(query, params)
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def get_summary_by_department(company: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> list[dict]:
    """Get total allocation values grouped by department."""
    conn = get_db()
    cursor = conn.cursor()

    query = '''
        SELECT a.company, a.department, a.subdepartment, SUM(a.allocation_value) as total_value, COUNT(DISTINCT a.invoice_id) as invoice_count
        FROM allocations a
        JOIN invoices i ON a.invoice_id = i.id
    '''
    params = []
    conditions = []

    if company:
        conditions.append('a.company = ?')
        params.append(company)
    if start_date:
        conditions.append('i.invoice_date >= ?')
        params.append(start_date)
    if end_date:
        conditions.append('i.invoice_date <= ?')
        params.append(end_date)

    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)

    query += ' GROUP BY a.company, a.department, a.subdepartment ORDER BY total_value DESC'

    cursor.execute(query, params)
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def delete_invoice(invoice_id: int) -> bool:
    """Delete an invoice and its allocations."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('DELETE FROM invoices WHERE id = ?', (invoice_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    conn.close()
    return deleted


def search_invoices(query: str) -> list[dict]:
    """Search invoices by supplier or invoice number."""
    conn = get_db()
    cursor = conn.cursor()

    search_term = f'%{query}%'
    cursor.execute('''
        SELECT * FROM invoices
        WHERE supplier LIKE ? OR invoice_number LIKE ?
        ORDER BY created_at DESC
        LIMIT 50
    ''', (search_term, search_term))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


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
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO invoice_templates (
                name, template_type, supplier, supplier_vat, customer_vat, currency, description,
                invoice_number_regex, invoice_date_regex, invoice_value_regex,
                date_format, sample_invoice_path,
                supplier_regex, supplier_vat_regex, customer_vat_regex, currency_regex
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            name, template_type, supplier, supplier_vat, customer_vat, currency, description,
            invoice_number_regex, invoice_date_regex, invoice_value_regex,
            date_format, sample_invoice_path,
            supplier_regex, supplier_vat_regex, customer_vat_regex, currency_regex
        ))

        template_id = cursor.lastrowid
        conn.commit()
        return template_id

    except sqlite3.IntegrityError:
        conn.rollback()
        raise ValueError(f"Template '{name}' already exists")
    finally:
        conn.close()


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
    cursor = conn.cursor()

    # Build dynamic update query
    updates = []
    params = []

    if name is not None:
        updates.append('name = ?')
        params.append(name)
    if template_type is not None:
        updates.append('template_type = ?')
        params.append(template_type)
    if supplier is not None:
        updates.append('supplier = ?')
        params.append(supplier)
    if supplier_vat is not None:
        updates.append('supplier_vat = ?')
        params.append(supplier_vat)
    if customer_vat is not None:
        updates.append('customer_vat = ?')
        params.append(customer_vat)
    if currency is not None:
        updates.append('currency = ?')
        params.append(currency)
    if description is not None:
        updates.append('description = ?')
        params.append(description)
    if invoice_number_regex is not None:
        updates.append('invoice_number_regex = ?')
        params.append(invoice_number_regex)
    if invoice_date_regex is not None:
        updates.append('invoice_date_regex = ?')
        params.append(invoice_date_regex)
    if invoice_value_regex is not None:
        updates.append('invoice_value_regex = ?')
        params.append(invoice_value_regex)
    if date_format is not None:
        updates.append('date_format = ?')
        params.append(date_format)
    if sample_invoice_path is not None:
        updates.append('sample_invoice_path = ?')
        params.append(sample_invoice_path)
    if supplier_regex is not None:
        updates.append('supplier_regex = ?')
        params.append(supplier_regex)
    if supplier_vat_regex is not None:
        updates.append('supplier_vat_regex = ?')
        params.append(supplier_vat_regex)
    if customer_vat_regex is not None:
        updates.append('customer_vat_regex = ?')
        params.append(customer_vat_regex)
    if currency_regex is not None:
        updates.append('currency_regex = ?')
        params.append(currency_regex)

    if not updates:
        conn.close()
        return False

    updates.append('updated_at = CURRENT_TIMESTAMP')
    params.append(template_id)

    query = f"UPDATE invoice_templates SET {', '.join(updates)} WHERE id = ?"
    cursor.execute(query, params)
    updated = cursor.rowcount > 0

    conn.commit()
    conn.close()
    return updated


def delete_invoice_template(template_id: int) -> bool:
    """Delete an invoice template."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('DELETE FROM invoice_templates WHERE id = ?', (template_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    conn.close()
    return deleted


def get_all_invoice_templates() -> list[dict]:
    """Get all invoice templates."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM invoice_templates ORDER BY name')
    templates = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return templates


def get_invoice_template(template_id: int) -> Optional[dict]:
    """Get a specific invoice template by ID."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM invoice_templates WHERE id = ?', (template_id,))
    template = cursor.fetchone()

    conn.close()
    return dict(template) if template else None


def get_invoice_template_by_name(name: str) -> Optional[dict]:
    """Get a specific invoice template by name."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM invoice_templates WHERE name = ?', (name,))
    template = cursor.fetchone()

    conn.close()
    return dict(template) if template else None


# Initialize database on import
init_db()
