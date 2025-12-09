import os
from datetime import datetime
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor

# PostgreSQL connection - DATABASE_URL is required
DATABASE_URL = os.environ.get('DATABASE_URL')

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required. Set it to your PostgreSQL connection string.")


def get_db():
    """Get PostgreSQL database connection."""
    return psycopg2.connect(DATABASE_URL)


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
            drive_link TEXT,
            comment TEXT,
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
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

    # Create indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(invoice_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_allocations_company ON allocations(company)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_allocations_department ON allocations(department)')

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
    conn.close()


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
    """Convert a database row to a dictionary."""
    if row is None:
        return None
    return dict(row)


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
    cursor = get_cursor(conn)

    try:
        cursor.execute('''
            INSERT INTO invoices (supplier, invoice_template, invoice_number, invoice_date, invoice_value, currency, drive_link)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (supplier, invoice_template, invoice_number, invoice_date, invoice_value, currency, drive_link))
        invoice_id = cursor.fetchone()['id']

        # Insert allocations
        for dist in distributions:
            allocation_value = invoice_value * dist['allocation']
            cursor.execute('''
                INSERT INTO allocations (invoice_id, company, brand, department, subdepartment, allocation_percent, allocation_value, responsible, reinvoice_to)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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

    except Exception as e:
        conn.rollback()
        if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
            raise ValueError(f"Invoice {invoice_number} already exists in database")
        raise
    finally:
        conn.close()


def get_all_invoices(limit: int = 100, offset: int = 0) -> list[dict]:
    """Get all invoices with pagination."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT * FROM invoices
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    ''', (limit, offset))

    invoices = [dict_from_row(row) for row in cursor.fetchall()]
    conn.close()
    return invoices


def get_invoice_with_allocations(invoice_id: int) -> Optional[dict]:
    """Get invoice with all its allocations."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('SELECT * FROM invoices WHERE id = %s', (invoice_id,))
    invoice = cursor.fetchone()

    if not invoice:
        conn.close()
        return None

    invoice = dict_from_row(invoice)

    cursor.execute('SELECT * FROM allocations WHERE invoice_id = %s', (invoice_id,))
    invoice['allocations'] = [dict_from_row(row) for row in cursor.fetchall()]

    conn.close()
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
    conn.close()
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
    conn.close()
    return results


def get_summary_by_company(start_date: Optional[str] = None, end_date: Optional[str] = None) -> list[dict]:
    """Get total allocation values grouped by company."""
    conn = get_db()
    cursor = get_cursor(conn)

    query = '''
        SELECT a.company, SUM(a.allocation_value) as total_value, COUNT(DISTINCT a.invoice_id) as invoice_count
        FROM allocations a
        JOIN invoices i ON a.invoice_id = i.id
    '''
    params = []

    if start_date or end_date:
        conditions = []
        if start_date:
            conditions.append('i.invoice_date >= %s')
            params.append(start_date)
        if end_date:
            conditions.append('i.invoice_date <= %s')
            params.append(end_date)
        query += ' WHERE ' + ' AND '.join(conditions)

    query += ' GROUP BY a.company ORDER BY total_value DESC'

    cursor.execute(query, params)
    results = [dict_from_row(row) for row in cursor.fetchall()]
    conn.close()
    return results


def get_summary_by_department(company: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None) -> list[dict]:
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

    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)

    query += ' GROUP BY a.company, a.department, a.subdepartment ORDER BY total_value DESC'

    cursor.execute(query, params)
    results = [dict_from_row(row) for row in cursor.fetchall()]
    conn.close()
    return results


def delete_invoice(invoice_id: int) -> bool:
    """Delete an invoice and its allocations."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('DELETE FROM invoices WHERE id = %s', (invoice_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    conn.close()
    return deleted


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
        conn.close()
        return False

    updates.append('updated_at = CURRENT_TIMESTAMP')
    params.append(invoice_id)

    query = f"UPDATE invoices SET {', '.join(updates)} WHERE id = %s"
    cursor.execute(query, params)
    updated = cursor.rowcount > 0

    conn.commit()
    conn.close()
    return updated


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
    conn.close()
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
    reinvoice_to: str = None
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

    if not updates:
        conn.close()
        return False

    params.append(allocation_id)
    query = f"UPDATE allocations SET {', '.join(updates)} WHERE id = %s"
    cursor.execute(query, params)
    updated = cursor.rowcount > 0

    conn.commit()
    conn.close()
    return updated


def delete_allocation(allocation_id: int) -> bool:
    """Delete an allocation."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('DELETE FROM allocations WHERE id = %s', (allocation_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    conn.close()
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
    reinvoice_to: str = None
) -> int:
    """Add a new allocation to an invoice. Returns allocation ID."""
    conn = get_db()
    cursor = get_cursor(conn)

    try:
        cursor.execute('''
            INSERT INTO allocations (invoice_id, company, brand, department, subdepartment,
                allocation_percent, allocation_value, responsible, reinvoice_to)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (invoice_id, company, brand, department, subdepartment,
              allocation_percent, allocation_value, responsible, reinvoice_to))
        allocation_id = cursor.fetchone()['id']

        conn.commit()
        return allocation_id
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()


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
                    allocation_percent, allocation_value, responsible, reinvoice_to)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                invoice_id,
                alloc['company'],
                alloc.get('brand'),
                alloc['department'],
                alloc.get('subdepartment'),
                allocation_percent,
                allocation_value,
                alloc.get('responsible'),
                alloc.get('reinvoice_to')
            ))

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()


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
        conn.close()
        return False

    updates.append('updated_at = CURRENT_TIMESTAMP')
    params.append(template_id)

    query = f"UPDATE invoice_templates SET {', '.join(updates)} WHERE id = %s"
    cursor.execute(query, params)
    updated = cursor.rowcount > 0

    conn.commit()
    conn.close()
    return updated


def delete_invoice_template(template_id: int) -> bool:
    """Delete an invoice template."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('DELETE FROM invoice_templates WHERE id = %s', (template_id,))
    deleted = cursor.rowcount > 0

    conn.commit()
    conn.close()
    return deleted


def get_all_invoice_templates() -> list[dict]:
    """Get all invoice templates."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('SELECT * FROM invoice_templates ORDER BY name')
    templates = [dict_from_row(row) for row in cursor.fetchall()]

    conn.close()
    return templates


def get_invoice_template(template_id: int) -> Optional[dict]:
    """Get a specific invoice template by ID."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('SELECT * FROM invoice_templates WHERE id = %s', (template_id,))
    template = cursor.fetchone()

    conn.close()
    return dict_from_row(template) if template else None


def get_invoice_template_by_name(name: str) -> Optional[dict]:
    """Get a specific invoice template by name."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('SELECT * FROM invoice_templates WHERE name = %s', (name,))
    template = cursor.fetchone()

    conn.close()
    return dict_from_row(template) if template else None


# Initialize database on import
init_db()
