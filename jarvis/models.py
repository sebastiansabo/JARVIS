from dataclasses import dataclass
from typing import Optional
import time
from database import get_db, get_cursor, get_placeholder, release_db

# In-memory cache for organizational structure
# This data rarely changes, so caching significantly improves performance
_structure_cache = {
    'data': None,
    'timestamp': 0,
    'ttl': 300  # 5 minutes TTL
}

_companies_cache = {
    'data': None,
    'timestamp': 0,
    'ttl': 300
}

_brands_cache = {}  # keyed by company
_departments_cache = {}  # keyed by company
_subdepartments_cache = {}  # keyed by (company, department)


def _is_cache_valid(cache_entry: dict) -> bool:
    """Check if a cache entry is still valid."""
    if cache_entry.get('data') is None:
        return False
    return (time.time() - cache_entry.get('timestamp', 0)) < cache_entry.get('ttl', 300)


def clear_structure_cache():
    """Clear all structure-related caches. Call this after structure updates."""
    global _structure_cache, _companies_cache, _brands_cache, _departments_cache, _subdepartments_cache
    _structure_cache = {'data': None, 'timestamp': 0, 'ttl': 300}
    _companies_cache = {'data': None, 'timestamp': 0, 'ttl': 300}
    _brands_cache = {}
    _departments_cache = {}
    _subdepartments_cache = {}


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
    """Load the organizational structure from database (with caching)."""
    global _structure_cache

    # Return cached data if valid
    if _is_cache_valid(_structure_cache):
        return _structure_cache['data']

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

    release_db(conn)

    # Cache the result
    _structure_cache['data'] = units
    _structure_cache['timestamp'] = time.time()

    return units


def get_companies() -> list[str]:
    """Get unique list of companies (with caching)."""
    global _companies_cache

    # Return cached data if valid
    if _is_cache_valid(_companies_cache):
        return _companies_cache['data']

    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute('''
        SELECT DISTINCT company FROM department_structure
        WHERE company IS NOT NULL AND company != ''
        ORDER BY company
    ''')

    companies = [row['company'] for row in cursor.fetchall()]
    release_db(conn)

    # Cache the result
    _companies_cache['data'] = companies
    _companies_cache['timestamp'] = time.time()

    return companies


def get_brands_for_company(company: str) -> list[str]:
    """Get brands available for a specific company (with caching)."""
    global _brands_cache

    # Check cache
    cache_key = company
    if cache_key in _brands_cache:
        entry = _brands_cache[cache_key]
        if _is_cache_valid(entry):
            return entry['data']

    conn = get_db()
    cursor = get_cursor(conn)
    ph = get_placeholder()

    cursor.execute(f'''
        SELECT DISTINCT brand FROM department_structure
        WHERE company = {ph} AND brand IS NOT NULL AND brand != ''
        ORDER BY brand
    ''', (company,))

    brands = [row['brand'] for row in cursor.fetchall()]
    release_db(conn)

    # Cache the result
    _brands_cache[cache_key] = {'data': brands, 'timestamp': time.time(), 'ttl': 300}

    return brands


def get_departments_for_company(company: str) -> list[str]:
    """Get departments available for a specific company (with caching)."""
    global _departments_cache

    # Check cache
    cache_key = company
    if cache_key in _departments_cache:
        entry = _departments_cache[cache_key]
        if _is_cache_valid(entry):
            return entry['data']

    conn = get_db()
    cursor = get_cursor(conn)
    ph = get_placeholder()

    cursor.execute(f'''
        SELECT DISTINCT department FROM department_structure
        WHERE company = {ph} AND department IS NOT NULL AND department != ''
        ORDER BY department
    ''', (company,))

    departments = [row['department'] for row in cursor.fetchall()]
    release_db(conn)

    # Cache the result
    _departments_cache[cache_key] = {'data': departments, 'timestamp': time.time(), 'ttl': 300}

    return departments


def get_subdepartments(company: str, department: str) -> list[str]:
    """Get subdepartments for a specific company and department (with caching)."""
    global _subdepartments_cache

    # Check cache
    cache_key = (company, department)
    if cache_key in _subdepartments_cache:
        entry = _subdepartments_cache[cache_key]
        if _is_cache_valid(entry):
            return entry['data']

    conn = get_db()
    cursor = get_cursor(conn)
    ph = get_placeholder()

    cursor.execute(f'''
        SELECT DISTINCT subdepartment FROM department_structure
        WHERE company = {ph} AND department = {ph} AND subdepartment IS NOT NULL AND subdepartment != ''
        ORDER BY subdepartment
    ''', (company, department))

    subdepts = [row['subdepartment'] for row in cursor.fetchall()]
    release_db(conn)

    # Cache the result
    _subdepartments_cache[cache_key] = {'data': subdepts, 'timestamp': time.time(), 'ttl': 300}

    return subdepts


def get_manager(company: str, department: str, subdepartment: Optional[str] = None, brand: Optional[str] = None) -> str:
    """Get the manager for a specific department, optionally filtered by brand.

    Uses manager_ids array joined with responsables table to get manager names.
    """
    conn = get_db()
    cursor = get_cursor(conn)

    # Build query with optional brand and subdepartment filters
    conditions = ["ds.company = %s", "ds.department = %s"]
    params = [company, department]

    if brand:
        conditions.append("ds.brand = %s")
        params.append(brand)

    if subdepartment:
        conditions.append("ds.subdepartment = %s")
        params.append(subdepartment)

    # Query manager_ids and join with responsables to get names
    query = f'''
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
    '''
    cursor.execute(query, tuple(params))

    row = cursor.fetchone()
    release_db(conn)
    return row['manager_name'] if row and row['manager_name'] else ''
