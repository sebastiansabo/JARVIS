import re
from typing import Optional
from database import get_db, get_placeholder, get_cursor, release_db


def normalize_vat(vat: str) -> str:
    """
    Normalize VAT number for comparison.
    Handles various formats: 'RO 225615', 'RO225615', 'CUI 225615', '225615', etc.
    Returns just the numeric part for comparison, plus stores the country code.
    """
    if not vat:
        return ''

    # Convert to uppercase and strip
    vat = str(vat).upper().strip()

    # Remove common prefixes like 'CUI', 'CIF', 'VAT', 'TAX ID', etc.
    prefixes_to_remove = ['CUI:', 'CUI', 'CIF:', 'CIF', 'VAT:', 'VAT', 'TAX ID:', 'TAX ID', 'NR.', 'NR', 'NO.', 'NO']
    for prefix in prefixes_to_remove:
        if vat.startswith(prefix):
            vat = vat[len(prefix):].strip()

    # Remove all spaces, dashes, dots, and other separators
    vat = re.sub(r'[\s\-\./:]+', '', vat)

    return vat


def extract_vat_numbers(vat: str) -> str:
    """Extract just the numeric portion of a VAT number for matching."""
    if not vat:
        return ''
    return re.sub(r'[^0-9]', '', str(vat))


def get_companies_with_vat() -> list[dict]:
    """Load companies with VAT numbers and brands from database."""
    conn = get_db()
    cursor = get_cursor(conn)

    # Get companies with id
    cursor.execute('SELECT id, company, vat FROM companies ORDER BY company')
    companies = [dict(row) for row in cursor.fetchall()]

    # Get brands from company_brands table (join with brands to get brand name)
    cursor.execute('''
        SELECT cb.company_id, b.id as brand_id, b.name as brand
        FROM company_brands cb
        JOIN brands b ON cb.brand_id = b.id
        WHERE cb.is_active = TRUE AND b.is_active = TRUE
        ORDER BY b.name
    ''')
    brands_rows = cursor.fetchall()

    # Group brands by company_id
    brands_by_company = {}
    for row in brands_rows:
        cid = row['company_id']
        if cid not in brands_by_company:
            brands_by_company[cid] = []
        brands_by_company[cid].append({'id': row['brand_id'], 'brand': row['brand']})

    # Add brands to companies
    for company in companies:
        company_brands = brands_by_company.get(company['id'], [])
        company['brands_list'] = company_brands
        company['brands'] = ', '.join(b['brand'] for b in company_brands) if company_brands else ''

    release_db(conn)
    return companies


def match_company_by_vat(invoice_vat: str) -> Optional[dict]:
    """
    Find company matching the given VAT number.
    Uses multiple matching strategies:
    1. Exact match after normalization (removes spaces, prefixes)
    2. Numeric-only match (compares just the numbers)
    """
    if not invoice_vat:
        return None

    normalized_invoice_vat = normalize_vat(invoice_vat)
    invoice_numbers_only = extract_vat_numbers(invoice_vat)

    companies = get_companies_with_vat()

    # First pass: exact normalized match
    for company in companies:
        company_vat = company.get('vat', '')
        if normalize_vat(company_vat) == normalized_invoice_vat:
            return company

    # Second pass: numeric-only match (handles cases like 'RO225615' matching '225615')
    if invoice_numbers_only:
        for company in companies:
            company_vat = company.get('vat', '')
            company_numbers = extract_vat_numbers(company_vat)
            if company_numbers and company_numbers == invoice_numbers_only:
                return company

    return None


def add_company_with_vat(company: str, vat: str) -> bool:
    """Add a new company with VAT to the database."""
    conn = get_db()
    cursor = conn.cursor()
    ph = get_placeholder()

    try:
        cursor.execute(f'''
            INSERT INTO companies (company, vat)
            VALUES ({ph}, {ph})
        ''', (company, vat))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        release_db(conn)


def update_company_vat(company: str, vat: str) -> bool:
    """Update VAT for an existing company."""
    conn = get_db()
    cursor = conn.cursor()
    ph = get_placeholder()

    cursor.execute(f'''
        UPDATE companies SET vat = {ph}
        WHERE company = {ph}
    ''', (vat, company))

    updated = cursor.rowcount > 0
    conn.commit()
    release_db(conn)
    return updated


def delete_company(company: str) -> bool:
    """Delete a company from the database."""
    conn = get_db()
    cursor = conn.cursor()
    ph = get_placeholder()

    cursor.execute(f'DELETE FROM companies WHERE company = {ph}', (company,))
    deleted = cursor.rowcount > 0

    conn.commit()
    release_db(conn)
    return deleted
