from dataclasses import dataclass
from typing import Optional
from database import get_db, get_cursor, get_placeholder


@dataclass
class DepartmentUnit:
    """Represents a single department unit from the Structure sheet."""
    company: str
    brand: Optional[str]
    department: str
    subdepartment: Optional[str]
    manager: str
    marketing: str

    @property
    def display_name(self) -> str:
        """Human-readable name for display in UI."""
        parts = [self.company]
        if self.brand:
            parts.append(self.brand)
        parts.append(self.department)
        if self.subdepartment:
            parts.append(self.subdepartment)
        return ' > '.join(parts)

    @property
    def unique_key(self) -> str:
        """Unique identifier for this department unit."""
        return f"{self.company}|{self.brand or ''}|{self.department}|{self.subdepartment or ''}"


@dataclass
class InvoiceAllocation:
    """Represents a single allocation line for an invoice."""
    submission_date: str
    company: str
    supplier: str
    invoice_template: str
    invoice_number: str
    invoice_date: str
    invoice_value: float
    allocation: float  # Percentage as decimal (0.5 = 50%)
    department: str
    subdepartment: Optional[str]
    brand: Optional[str]
    responsible: str
    drive_link: str
    reinvoice_to: Optional[str] = None  # Company to reinvoice this cost to


def load_structure() -> list[DepartmentUnit]:
    """Load the organizational structure from database."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT company, brand, department, subdepartment, manager, marketing
        FROM department_structure
        ORDER BY company, department, subdepartment
    ''')

    units = []
    for row in cursor.fetchall():
        unit = DepartmentUnit(
            company=row['company'] or '',
            brand=row['brand'],
            department=row['department'] or '',
            subdepartment=row['subdepartment'],
            manager=row['manager'] or '',
            marketing=row['marketing'] or ''
        )
        units.append(unit)

    conn.close()
    return units


def get_companies() -> list[str]:
    """Get unique list of companies."""
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT DISTINCT company FROM department_structure
        WHERE company IS NOT NULL AND company != ''
        ORDER BY company
    ''')

    companies = [row['company'] for row in cursor.fetchall()]
    conn.close()
    return companies


def get_brands_for_company(company: str) -> list[str]:
    """Get brands available for a specific company."""
    conn = get_db()
    cursor = get_cursor(conn)
    ph = get_placeholder()

    cursor.execute(f'''
        SELECT DISTINCT brand FROM department_structure
        WHERE company = {ph} AND brand IS NOT NULL AND brand != ''
        ORDER BY brand
    ''', (company,))

    brands = [row['brand'] for row in cursor.fetchall()]
    conn.close()
    return brands


def get_departments_for_company(company: str) -> list[str]:
    """Get departments available for a specific company."""
    conn = get_db()
    cursor = get_cursor(conn)
    ph = get_placeholder()

    cursor.execute(f'''
        SELECT DISTINCT department FROM department_structure
        WHERE company = {ph} AND department IS NOT NULL AND department != ''
        ORDER BY department
    ''', (company,))

    departments = [row['department'] for row in cursor.fetchall()]
    conn.close()
    return departments


def get_subdepartments(company: str, department: str) -> list[str]:
    """Get subdepartments for a specific company and department."""
    conn = get_db()
    cursor = get_cursor(conn)
    ph = get_placeholder()

    cursor.execute(f'''
        SELECT DISTINCT subdepartment FROM department_structure
        WHERE company = {ph} AND department = {ph} AND subdepartment IS NOT NULL AND subdepartment != ''
        ORDER BY subdepartment
    ''', (company, department))

    subdepts = [row['subdepartment'] for row in cursor.fetchall()]
    conn.close()
    return subdepts


def get_manager(company: str, department: str, subdepartment: Optional[str] = None) -> str:
    """Get the manager for a specific department."""
    conn = get_db()
    cursor = get_cursor(conn)
    ph = get_placeholder()

    if subdepartment:
        cursor.execute(f'''
            SELECT manager FROM department_structure
            WHERE company = {ph} AND department = {ph} AND subdepartment = {ph}
            LIMIT 1
        ''', (company, department, subdepartment))
    else:
        cursor.execute(f'''
            SELECT manager FROM department_structure
            WHERE company = {ph} AND department = {ph}
            LIMIT 1
        ''', (company, department))

    row = cursor.fetchone()
    conn.close()
    return row['manager'] if row else ''
