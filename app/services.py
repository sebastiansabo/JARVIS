import re
from datetime import datetime
from typing import Optional
from models import InvoiceAllocation, load_structure
from database import get_db, get_placeholder, save_invoice as db_save_invoice


def create_allocations(
    supplier: str,
    invoice_template: str,
    invoice_number: str,
    invoice_date: str,
    invoice_value: float,
    drive_link: str,
    distributions: list[dict]  # [{company, brand, department, subdepartment, allocation}]
) -> list[InvoiceAllocation]:
    """
    Create allocation records for an invoice distributed across departments.

    distributions: list of dicts with keys:
        - company: str
        - brand: str (optional)
        - department: str
        - subdepartment: str (optional)
        - allocation: float (percentage as decimal, e.g., 0.5 for 50%)
    """
    # Validate allocations sum to 1 (100%)
    total_allocation = sum(d['allocation'] for d in distributions)
    if abs(total_allocation - 1.0) > 0.001:
        raise ValueError(f"Allocations must sum to 100%, got {total_allocation * 100}%")

    structure = load_structure()
    allocations = []
    submission_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for dist in distributions:
        # Find the responsible person from structure
        responsible = ''
        for unit in structure:
            if (unit.company == dist['company'] and
                unit.department == dist['department'] and
                (dist.get('subdepartment') is None or unit.subdepartment == dist.get('subdepartment'))):
                responsible = unit.manager
                break

        allocation = InvoiceAllocation(
            submission_date=submission_date,
            company=dist['company'],
            supplier=supplier,
            invoice_template=invoice_template,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            invoice_value=invoice_value,
            allocation=dist['allocation'],
            department=dist['department'],
            subdepartment=dist.get('subdepartment'),
            brand=dist.get('brand'),
            responsible=responsible,
            drive_link=drive_link,
            reinvoice_to=dist.get('reinvoice_to')
        )
        allocations.append(allocation)

    return allocations


def save_invoice_to_db(
    supplier: str,
    invoice_template: str,
    invoice_number: str,
    invoice_date: str,
    invoice_value: float,
    currency: str,
    drive_link: str,
    distributions: list[dict]
) -> int:
    """Save invoice and allocations to database. Returns invoice ID."""
    # Validate allocations sum to 1 (100%)
    total_allocation = sum(d['allocation'] for d in distributions)
    if abs(total_allocation - 1.0) > 0.001:
        raise ValueError(f"Allocations must sum to 100%, got {total_allocation * 100}%")

    # Add responsible person to each distribution
    structure = load_structure()
    for dist in distributions:
        for unit in structure:
            if (unit.company == dist['company'] and
                unit.department == dist['department'] and
                (dist.get('subdepartment') is None or unit.subdepartment == dist.get('subdepartment'))):
                dist['responsible'] = unit.manager
                break

    return db_save_invoice(
        supplier=supplier,
        invoice_template=invoice_template,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        invoice_value=invoice_value,
        currency=currency,
        drive_link=drive_link,
        distributions=distributions
    )


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
    """Load companies with VAT numbers from SQLite database."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT company, brands, vat FROM companies ORDER BY company')
    companies = [dict(row) for row in cursor.fetchall()]

    conn.close()
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


def add_company_with_vat(company: str, vat: str, brands: str = '') -> bool:
    """Add a new company with VAT to the database."""
    conn = get_db()
    cursor = conn.cursor()
    ph = get_placeholder()

    try:
        cursor.execute(f'''
            INSERT INTO companies (company, brands, vat)
            VALUES ({ph}, {ph}, {ph})
        ''', (company, brands, vat))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def update_company_vat(company: str, vat: str, brands: str = None) -> bool:
    """Update VAT for an existing company."""
    conn = get_db()
    cursor = conn.cursor()
    ph = get_placeholder()

    if brands is not None:
        cursor.execute(f'''
            UPDATE companies SET vat = {ph}, brands = {ph}
            WHERE company = {ph}
        ''', (vat, brands, company))
    else:
        cursor.execute(f'''
            UPDATE companies SET vat = {ph}
            WHERE company = {ph}
        ''', (vat, company))

    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def delete_company(company: str) -> bool:
    """Delete a company from the database."""
    conn = get_db()
    cursor = conn.cursor()
    ph = get_placeholder()

    cursor.execute(f'DELETE FROM companies WHERE company = {ph}', (company,))
    deleted = cursor.rowcount > 0

    conn.commit()
    conn.close()
    return deleted
