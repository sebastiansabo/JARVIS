"""HR Module Database Operations."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db, get_cursor, release_db, dict_from_row


# ============== HR Employees (now using users table) ==============

def get_all_hr_employees(active_only=True, scope='all', user_context=None):
    """Get all HR employees from users table with scope-based filtering.

    Args:
        active_only: If True, only return active employees
        scope: Permission scope ('own', 'department', 'all')
        user_context: Dict with user_id, company, department for scope filtering
    """
    conn = get_db()
    cursor = get_cursor(conn)

    query = '''
        SELECT id, name, email, phone, department AS departments, subdepartment, company, brand,
               notify_on_allocation, is_active, created_at, updated_at
        FROM users
        WHERE 1=1
    '''
    params = []

    if active_only:
        query += ' AND is_active = TRUE'

    # Apply scope-based filtering
    if scope == 'own' and user_context:
        # User can only see themselves
        query += ' AND id = %s'
        params.append(user_context.get('user_id'))
    elif scope == 'department' and user_context:
        # User can see employees in same company + department
        if user_context.get('department') and user_context.get('company'):
            query += ' AND department = %s AND company = %s'
            params.append(user_context['department'])
            params.append(user_context['company'])
    # 'all' scope = no additional filtering

    query += ' ORDER BY name'

    cursor.execute(query, params)
    rows = cursor.fetchall()
    release_db(conn)
    return [dict_from_row(row) for row in rows]


def get_hr_employee(employee_id):
    """Get a single HR employee by ID from users table."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('''
        SELECT id, name, email, phone, department AS departments, subdepartment, company, brand,
               notify_on_allocation, is_active, created_at, updated_at
        FROM users WHERE id = %s
    ''', (employee_id,))
    row = cursor.fetchone()
    release_db(conn)
    return dict_from_row(row) if row else None


def save_hr_employee(name, department=None, subdepartment=None, brand=None, company=None,
                     email=None, phone=None, notify_on_allocation=True):
    """Create a new HR employee in users table."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('''
        INSERT INTO users (name, department, subdepartment, brand, company, email, phone, notify_on_allocation)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    ''', (name, department, subdepartment, brand, company, email, phone, notify_on_allocation))
    employee_id = cursor.fetchone()['id']
    conn.commit()
    release_db(conn)
    return employee_id


def update_hr_employee(employee_id, name, department=None, subdepartment=None, brand=None, company=None,
                       email=None, phone=None, notify_on_allocation=True, is_active=True):
    """Update an HR employee in users table."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('''
        UPDATE users
        SET name = %s, department = %s, subdepartment = %s, brand = %s, company = %s,
            email = %s, phone = %s, notify_on_allocation = %s,
            is_active = %s, updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
    ''', (name, department, subdepartment, brand, company, email, phone, notify_on_allocation, is_active, employee_id))
    conn.commit()
    release_db(conn)


def delete_hr_employee(employee_id):
    """Soft delete an HR employee (set is_active = FALSE)."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('''
        UPDATE users SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP WHERE id = %s
    ''', (employee_id,))
    conn.commit()
    release_db(conn)


def search_hr_employees(query):
    """Search HR employees by name from users table."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('''
        SELECT id, name, email, phone, department AS departments, subdepartment, company, brand,
               notify_on_allocation, is_active, created_at, updated_at
        FROM users
        WHERE is_active = TRUE AND name ILIKE %s
        ORDER BY name
        LIMIT 20
    ''', (f'%{query}%',))
    rows = cursor.fetchall()
    release_db(conn)
    return [dict_from_row(row) for row in rows]


# ============== HR Events ==============

def get_all_hr_events():
    """Get all HR events ordered by date."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('''
        SELECT e.*, u.name as created_by_name
        FROM hr.events e
        LEFT JOIN public.users u ON e.created_by = u.id
        ORDER BY e.start_date DESC
    ''')
    rows = cursor.fetchall()
    release_db(conn)
    return [dict_from_row(row) for row in rows]


def get_hr_event(event_id):
    """Get a single HR event by ID."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('''
        SELECT e.*, u.name as created_by_name
        FROM hr.events e
        LEFT JOIN public.users u ON e.created_by = u.id
        WHERE e.id = %s
    ''', (event_id,))
    row = cursor.fetchone()
    release_db(conn)
    return dict_from_row(row)


def save_hr_event(name, start_date, end_date, company=None, brand=None, description=None, created_by=None):
    """Create a new HR event."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('''
        INSERT INTO hr.events (name, start_date, end_date, company, brand, description, created_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    ''', (name, start_date, end_date, company, brand, description, created_by))
    event_id = cursor.fetchone()['id']
    conn.commit()
    release_db(conn)
    return event_id


def update_hr_event(event_id, name, start_date, end_date, company=None, brand=None, description=None):
    """Update an HR event."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('''
        UPDATE hr.events
        SET name = %s, start_date = %s, end_date = %s, company = %s, brand = %s, description = %s
        WHERE id = %s
    ''', (name, start_date, end_date, company, brand, description, event_id))
    conn.commit()
    release_db(conn)


def delete_hr_event(event_id):
    """Delete an HR event (cascades to bonuses)."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('DELETE FROM hr.events WHERE id = %s', (event_id,))
    conn.commit()
    release_db(conn)


def delete_hr_events_bulk(event_ids):
    """Delete multiple HR events (cascades to bonuses).

    Args:
        event_ids: List of event IDs to delete

    Returns:
        Number of deleted records
    """
    if not event_ids:
        return 0

    conn = get_db()
    cursor = get_cursor(conn)
    placeholders = ','.join(['%s'] * len(event_ids))
    cursor.execute(f'DELETE FROM hr.events WHERE id IN ({placeholders})', tuple(event_ids))
    deleted_count = cursor.rowcount
    conn.commit()
    release_db(conn)
    return deleted_count


# ============== HR Events ==============

def get_all_event_bonuses(year=None, month=None, employee_id=None, event_id=None,
                          scope='all', user_context=None):
    """Get event bonuses with optional filters and scope-based access control.

    Args:
        year: Filter by year
        month: Filter by month
        employee_id: Filter by employee
        event_id: Filter by event
        scope: Permission scope ('own', 'department', 'all')
        user_context: Dict with user_id, company, department for scope filtering
    """
    conn = get_db()
    cursor = get_cursor(conn)

    # user_id references users.id directly
    query = '''
        SELECT b.*, u.name as employee_name, u.department, u.brand, u.company,
               ev.name as event_name, ev.start_date as event_start, ev.end_date as event_end,
               creator.name as created_by_name,
               b.user_id as effective_employee_id
        FROM hr.event_bonuses b
        LEFT JOIN public.users u ON u.id = b.user_id
        JOIN hr.events ev ON b.event_id = ev.id
        LEFT JOIN public.users creator ON b.created_by = creator.id
        WHERE 1=1
    '''
    params = []

    if year:
        query += ' AND b.year = %s'
        params.append(year)
    if month:
        query += ' AND b.month = %s'
        params.append(month)
    if employee_id:
        query += ' AND b.user_id = %s'
        params.append(employee_id)
    if event_id:
        query += ' AND b.event_id = %s'
        params.append(event_id)

    # Apply scope-based filtering
    if scope == 'own' and user_context:
        # User can only see bonuses for themselves
        query += ' AND b.user_id = %s'
        params.append(user_context.get('user_id'))
    elif scope == 'department' and user_context:
        # User can see bonuses for users in same company + department
        if user_context.get('department') and user_context.get('company'):
            query += ' AND u.department = %s AND u.company = %s'
            params.append(user_context['department'])
            params.append(user_context['company'])
    # 'all' scope = no additional filtering

    query += ' ORDER BY b.year DESC, b.month DESC, u.name'

    cursor.execute(query, params)
    rows = cursor.fetchall()
    release_db(conn)
    return [dict_from_row(row) for row in rows]


def get_event_bonus(bonus_id):
    """Get a single event bonus by ID."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('''
        SELECT b.*, u.name as employee_name, u.department, u.brand, u.company,
               ev.name as event_name, ev.start_date as event_start, ev.end_date as event_end,
               b.user_id as effective_employee_id
        FROM hr.event_bonuses b
        LEFT JOIN public.users u ON u.id = b.user_id
        JOIN hr.events ev ON b.event_id = ev.id
        WHERE b.id = %s
    ''', (bonus_id,))
    row = cursor.fetchone()
    release_db(conn)
    return dict_from_row(row) if row else None


def can_access_bonus(bonus_id, scope, user_context):
    """Check if user can access a bonus based on their scope.

    Args:
        bonus_id: The bonus ID to check
        scope: Permission scope ('own', 'department', 'all')
        user_context: Dict with user_id, company, department

    Returns:
        True if user can access, False otherwise
    """
    if scope == 'all':
        return True

    bonus = get_event_bonus(bonus_id)
    if not bonus:
        return False

    if scope == 'own':
        # User can only access their own bonuses
        return bonus.get('user_id') == user_context.get('user_id')

    if scope == 'department':
        # User can access bonuses in their company + department
        return (bonus.get('company') == user_context.get('company') and
                bonus.get('department') == user_context.get('department'))

    return False


def can_access_employee(employee_id, scope, user_context):
    """Check if user can access an employee based on their scope.

    Args:
        employee_id: The employee ID to check
        scope: Permission scope ('own', 'department', 'all')
        user_context: Dict with user_id, company, department

    Returns:
        True if user can access, False otherwise
    """
    if scope == 'all':
        return True

    employee = get_hr_employee(employee_id)
    if not employee:
        return False

    if scope == 'own':
        # User can only access their own record
        return employee.get('id') == user_context.get('user_id')

    if scope == 'department':
        # User can access employees in their company + department
        return (employee.get('company') == user_context.get('company') and
                employee.get('departments') == user_context.get('department'))

    return False


def save_event_bonus(employee_id, event_id, year, month, participation_start=None,
                     participation_end=None, bonus_days=None, hours_free=None,
                     bonus_net=None, details=None, allocation_month=None, created_by=None):
    """Create a new event bonus record using user_id (references users.id)."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('''
        INSERT INTO hr.event_bonuses
        (user_id, event_id, year, month, participation_start, participation_end,
         bonus_days, hours_free, bonus_net, details, allocation_month, created_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    ''', (employee_id, event_id, year, month, participation_start, participation_end,
          bonus_days, hours_free, bonus_net, details, allocation_month, created_by))
    bonus_id = cursor.fetchone()['id']
    conn.commit()
    release_db(conn)
    return bonus_id


def save_event_bonuses_bulk(bonuses, created_by=None):
    """Bulk create event bonus records using user_id (references users.id)."""
    conn = get_db()
    cursor = get_cursor(conn)

    created_ids = []
    for b in bonuses:
        cursor.execute('''
            INSERT INTO hr.event_bonuses
            (user_id, event_id, year, month, participation_start, participation_end,
             bonus_days, hours_free, bonus_net, details, allocation_month, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (b['employee_id'], b['event_id'], b['year'], b['month'],
              b.get('participation_start'), b.get('participation_end'),
              b.get('bonus_days'), b.get('hours_free'), b.get('bonus_net'),
              b.get('details'), b.get('allocation_month'), created_by))
        created_ids.append(cursor.fetchone()['id'])

    conn.commit()
    release_db(conn)
    return created_ids


def update_event_bonus(bonus_id, employee_id, event_id, year, month, participation_start=None,
                       participation_end=None, bonus_days=None, hours_free=None,
                       bonus_net=None, details=None, allocation_month=None):
    """Update an event bonus record using user_id (references users.id)."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('''
        UPDATE hr.event_bonuses
        SET user_id = %s, event_id = %s, year = %s, month = %s,
            participation_start = %s, participation_end = %s, bonus_days = %s,
            hours_free = %s, bonus_net = %s, details = %s, allocation_month = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
    ''', (employee_id, event_id, year, month, participation_start, participation_end,
          bonus_days, hours_free, bonus_net, details, allocation_month, bonus_id))
    conn.commit()
    release_db(conn)


def delete_event_bonus(bonus_id):
    """Delete an event bonus record."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('DELETE FROM hr.event_bonuses WHERE id = %s', (bonus_id,))
    conn.commit()
    release_db(conn)


def delete_event_bonuses_bulk(bonus_ids):
    """Delete multiple event bonus records.

    Args:
        bonus_ids: List of bonus IDs to delete

    Returns:
        Number of deleted records
    """
    if not bonus_ids:
        return 0

    conn = get_db()
    cursor = get_cursor(conn)
    # Use parameterized query with tuple expansion
    placeholders = ','.join(['%s'] * len(bonus_ids))
    cursor.execute(f'DELETE FROM hr.event_bonuses WHERE id IN ({placeholders})', tuple(bonus_ids))
    deleted_count = cursor.rowcount
    conn.commit()
    release_db(conn)
    return deleted_count


def delete_event_bonuses_by_employee(employee_ids):
    """Delete all bonuses for the given employee (user) IDs.

    Args:
        employee_ids: List of user IDs whose bonuses to delete

    Returns:
        Number of deleted records
    """
    if not employee_ids:
        return 0

    conn = get_db()
    cursor = get_cursor(conn)
    placeholders = ','.join(['%s'] * len(employee_ids))
    cursor.execute(f'DELETE FROM hr.event_bonuses WHERE user_id IN ({placeholders})', tuple(employee_ids))
    deleted_count = cursor.rowcount
    conn.commit()
    release_db(conn)
    return deleted_count


def delete_event_bonuses_by_event(selections):
    """Delete all bonuses for given event/year/month combinations.

    Args:
        selections: List of dicts with keys: event_id, year, month

    Returns:
        Number of deleted records
    """
    if not selections:
        return 0

    conn = get_db()
    cursor = get_cursor(conn)

    total_deleted = 0
    for sel in selections:
        cursor.execute(
            'DELETE FROM hr.event_bonuses WHERE event_id = %s AND year = %s AND month = %s',
            (sel['event_id'], sel['year'], sel['month'])
        )
        total_deleted += cursor.rowcount

    conn.commit()
    release_db(conn)
    return total_deleted


# ============== Summary/Stats ==============

def get_event_bonuses_summary(year=None):
    """Get summary stats for event bonuses."""
    conn = get_db()
    cursor = get_cursor(conn)

    query = '''
        SELECT
            COUNT(DISTINCT b.user_id) as total_employees,
            COUNT(DISTINCT b.event_id) as total_events,
            COUNT(*) as total_bonuses,
            SUM(b.bonus_net) as total_bonus_amount,
            SUM(b.hours_free) as total_hours,
            SUM(b.bonus_days) as total_days
        FROM hr.event_bonuses b
    '''
    params = []
    if year:
        query += ' WHERE b.year = %s'
        params.append(year)

    cursor.execute(query, params)
    row = cursor.fetchone()
    release_db(conn)
    return dict_from_row(row)


def get_bonuses_by_month(year):
    """Get bonus totals grouped by month for a year."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('''
        SELECT month, COUNT(*) as count, SUM(bonus_net) as total
        FROM hr.event_bonuses
        WHERE year = %s
        GROUP BY month
        ORDER BY month
    ''', (year,))
    rows = cursor.fetchall()
    release_db(conn)
    return [dict_from_row(row) for row in rows]


def get_bonuses_by_employee(year=None, month=None):
    """Get bonus totals grouped by employee from users table."""
    conn = get_db()
    cursor = get_cursor(conn)

    query = '''
        SELECT u.id, u.name, u.department, u.company, u.brand,
               COUNT(*) as bonus_count,
               COALESCE(SUM(b.bonus_days), 0) as total_days,
               COALESCE(SUM(b.hours_free), 0) as total_hours,
               COALESCE(SUM(b.bonus_net), 0) as total_bonus
        FROM hr.event_bonuses b
        LEFT JOIN public.users u ON u.id = b.user_id
        WHERE 1=1
    '''
    params = []
    if year:
        query += ' AND b.year = %s'
        params.append(year)
    if month:
        query += ' AND b.month = %s'
        params.append(month)

    query += ' GROUP BY u.id, u.name, u.department, u.company, u.brand ORDER BY total_bonus DESC'

    cursor.execute(query, params)
    rows = cursor.fetchall()
    release_db(conn)
    return [dict_from_row(row) for row in rows]


def get_bonuses_by_event(year=None, month=None):
    """Get bonus totals grouped by event, year, and month."""
    conn = get_db()
    cursor = get_cursor(conn)

    query = '''
        SELECT e.id, e.name, e.start_date, e.end_date, e.company, e.brand,
               b.year, b.month,
               COUNT(*) as bonus_count,
               COUNT(DISTINCT b.user_id) as employee_count,
               COALESCE(SUM(b.bonus_days), 0) as total_days,
               COALESCE(SUM(b.hours_free), 0) as total_hours,
               COALESCE(SUM(b.bonus_net), 0) as total_bonus
        FROM hr.event_bonuses b
        JOIN hr.events e ON e.id = b.event_id
        WHERE 1=1
    '''
    params = []
    if year:
        query += ' AND b.year = %s'
        params.append(year)
    if month:
        query += ' AND b.month = %s'
        params.append(month)

    query += ' GROUP BY e.id, e.name, e.start_date, e.end_date, e.company, e.brand, b.year, b.month ORDER BY b.year DESC, b.month DESC, total_bonus DESC'

    cursor.execute(query, params)
    rows = cursor.fetchall()
    release_db(conn)
    return [dict_from_row(row) for row in rows]


# ============== HR Bonus Types ==============

def get_all_bonus_types(active_only=True):
    """Get all bonus types."""
    conn = get_db()
    cursor = get_cursor(conn)

    query = 'SELECT * FROM hr.bonus_types'
    if active_only:
        query += ' WHERE is_active = TRUE'
    query += ' ORDER BY name'

    cursor.execute(query)
    rows = cursor.fetchall()
    release_db(conn)
    return [dict_from_row(row) for row in rows]


def get_bonus_type(bonus_type_id):
    """Get a single bonus type by ID."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('SELECT * FROM hr.bonus_types WHERE id = %s', (bonus_type_id,))
    row = cursor.fetchone()
    release_db(conn)
    return dict_from_row(row)


def save_bonus_type(name, amount, days_per_amount=1, description=None):
    """Create a new bonus type."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('''
        INSERT INTO hr.bonus_types (name, amount, days_per_amount, description)
        VALUES (%s, %s, %s, %s)
        RETURNING id
    ''', (name, amount, days_per_amount, description))
    bonus_type_id = cursor.fetchone()['id']
    conn.commit()
    release_db(conn)
    return bonus_type_id


def update_bonus_type(bonus_type_id, name, amount, days_per_amount=1, description=None, is_active=True):
    """Update a bonus type."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('''
        UPDATE hr.bonus_types
        SET name = %s, amount = %s, days_per_amount = %s, description = %s, is_active = %s
        WHERE id = %s
    ''', (name, amount, days_per_amount, description, is_active, bonus_type_id))
    conn.commit()
    release_db(conn)


def delete_bonus_type(bonus_type_id):
    """Soft delete a bonus type (set is_active = FALSE)."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('''
        UPDATE hr.bonus_types SET is_active = FALSE WHERE id = %s
    ''', (bonus_type_id,))
    conn.commit()
    release_db(conn)


# ============== Companies CRUD ==============

def get_all_companies_with_brands():
    """Get all companies with their brands."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("""
        SELECT id, company, vat, created_at
        FROM companies
        ORDER BY company
    """)
    companies = [dict_from_row(row) for row in cursor.fetchall()]

    # Get brands for each company
    cursor.execute("SELECT company_id, brand FROM company_brands WHERE is_active = TRUE")
    brand_rows = cursor.fetchall()
    release_db(conn)

    brands_by_company = {}
    for row in brand_rows:
        cid = row['company_id']
        if cid not in brands_by_company:
            brands_by_company[cid] = []
        brands_by_company[cid].append(row['brand'])

    for c in companies:
        c['brands'] = brands_by_company.get(c['id'], [])

    return companies


def create_company(company_name, vat=None):
    """Create a new company."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("""
        INSERT INTO companies (company, vat)
        VALUES (%s, %s)
        RETURNING id
    """, (company_name, vat))
    company_id = cursor.fetchone()['id']
    conn.commit()
    release_db(conn)
    return company_id


def update_company(company_id, company_name, vat=None):
    """Update a company."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("""
        UPDATE companies
        SET company = %s, vat = %s
        WHERE id = %s
    """, (company_name, vat, company_id))
    conn.commit()
    release_db(conn)


def delete_company(company_id):
    """Delete a company."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("DELETE FROM companies WHERE id = %s", (company_id,))
    conn.commit()
    release_db(conn)


# ============== Company Brands CRUD ==============

def get_all_company_brands(company_id=None):
    """Get all company brands, optionally filtered by company."""
    conn = get_db()
    cursor = get_cursor(conn)

    if company_id:
        cursor.execute("""
            SELECT cb.id, cb.company_id, c.company, cb.brand, cb.is_active, cb.created_at
            FROM company_brands cb
            JOIN companies c ON cb.company_id = c.id
            WHERE cb.company_id = %s AND cb.is_active = TRUE
            ORDER BY cb.brand
        """, (company_id,))
    else:
        cursor.execute("""
            SELECT cb.id, cb.company_id, c.company, cb.brand, cb.is_active, cb.created_at
            FROM company_brands cb
            JOIN companies c ON cb.company_id = c.id
            WHERE cb.is_active = TRUE
            ORDER BY c.company, cb.brand
        """)

    rows = cursor.fetchall()
    release_db(conn)
    return [dict_from_row(r) for r in rows]


def create_company_brand(company_id, brand):
    """Create a new company brand."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("""
        INSERT INTO company_brands (company_id, brand)
        VALUES (%s, %s)
        RETURNING id
    """, (company_id, brand))
    brand_id = cursor.fetchone()['id']
    conn.commit()
    release_db(conn)
    return brand_id


def update_company_brand(brand_id, company_id, brand, is_active=True):
    """Update a company brand."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("""
        UPDATE company_brands
        SET company_id = %s, brand = %s, is_active = %s
        WHERE id = %s
    """, (company_id, brand, is_active, brand_id))
    conn.commit()
    release_db(conn)


def delete_company_brand(brand_id):
    """Delete a company brand."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("DELETE FROM company_brands WHERE id = %s", (brand_id,))
    conn.commit()
    release_db(conn)


# ============== Department Structure CRUD ==============

def get_all_department_structures():
    """Get all department structure entries."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("""
        SELECT ds.id, ds.company, ds.brand, ds.department, ds.subdepartment,
               ds.manager, ds.company_id, ds.manager_ids, ds.cc_email
        FROM department_structure ds
        ORDER BY ds.company, ds.brand, ds.department
    """)
    rows = cursor.fetchall()
    release_db(conn)
    return [dict_from_row(r) for r in rows]


def create_department_structure(company_id, manager, company, brand, department, subdepartment, manager_ids=None, cc_email=None):
    """Create a new department structure entry."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("""
        INSERT INTO department_structure (company_id, manager, company, brand, department, subdepartment, manager_ids, cc_email)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (company_id, manager, company, brand, department, subdepartment, manager_ids, cc_email))
    struct_id = cursor.fetchone()['id']
    conn.commit()
    release_db(conn)
    return struct_id


def update_department_structure(struct_id, company_id, manager, company, brand, department, subdepartment, manager_ids=None, cc_email=None):
    """Update a department structure entry."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("""
        UPDATE department_structure
        SET company_id = %s, manager = %s, company = %s, brand = %s,
            department = %s, subdepartment = %s, manager_ids = %s, cc_email = %s
        WHERE id = %s
    """, (company_id, manager, company, brand, department, subdepartment, manager_ids, cc_email, struct_id))
    conn.commit()
    release_db(conn)


def delete_department_structure(struct_id):
    """Delete a department structure entry."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("DELETE FROM department_structure WHERE id = %s", (struct_id,))
    conn.commit()
    release_db(conn)


def get_name_by_id(table, id_value):
    """Get name from a lookup table by ID."""
    if not id_value:
        return None
    conn = get_db()
    cursor = get_cursor(conn)
    if table == 'companies':
        cursor.execute("SELECT company as name FROM companies WHERE id = %s", (id_value,))
    else:
        cursor.execute(f"SELECT name FROM {table} WHERE id = %s", (id_value,))
    row = cursor.fetchone()
    release_db(conn)
    return row['name'] if row else None


# ============== Master Tables CRUD (brands, departments, subdepartments) ==============

def get_all_master_brands():
    """Get all master brands."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("SELECT id, name, is_active FROM brands WHERE is_active = TRUE ORDER BY name")
    rows = cursor.fetchall()
    release_db(conn)
    return [dict_from_row(r) for r in rows]


def create_master_brand(name):
    """Create a new master brand."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("INSERT INTO brands (name) VALUES (%s) RETURNING id", (name,))
    brand_id = cursor.fetchone()['id']
    conn.commit()
    release_db(conn)
    return brand_id


def update_master_brand(brand_id, name, is_active=True):
    """Update a master brand."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("UPDATE brands SET name = %s, is_active = %s WHERE id = %s", (name, is_active, brand_id))
    conn.commit()
    release_db(conn)


def delete_master_brand(brand_id):
    """Soft delete a master brand."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("UPDATE brands SET is_active = FALSE WHERE id = %s", (brand_id,))
    conn.commit()
    release_db(conn)


def get_all_master_departments():
    """Get all master departments."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("SELECT id, name, is_active FROM departments WHERE is_active = TRUE ORDER BY name")
    rows = cursor.fetchall()
    release_db(conn)
    return [dict_from_row(r) for r in rows]


def create_master_department(name):
    """Create a new master department."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("INSERT INTO departments (name) VALUES (%s) RETURNING id", (name,))
    dept_id = cursor.fetchone()['id']
    conn.commit()
    release_db(conn)
    return dept_id


def update_master_department(dept_id, name, is_active=True):
    """Update a master department."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("UPDATE departments SET name = %s, is_active = %s WHERE id = %s", (name, is_active, dept_id))
    conn.commit()
    release_db(conn)


def delete_master_department(dept_id):
    """Soft delete a master department."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("UPDATE departments SET is_active = FALSE WHERE id = %s", (dept_id,))
    conn.commit()
    release_db(conn)


def get_all_master_subdepartments():
    """Get all master subdepartments."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("SELECT id, name, is_active FROM subdepartments WHERE is_active = TRUE ORDER BY name")
    rows = cursor.fetchall()
    release_db(conn)
    return [dict_from_row(r) for r in rows]


def create_master_subdepartment(name):
    """Create a new master subdepartment."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("INSERT INTO subdepartments (name) VALUES (%s) RETURNING id", (name,))
    subdept_id = cursor.fetchone()['id']
    conn.commit()
    release_db(conn)
    return subdept_id


def update_master_subdepartment(subdept_id, name, is_active=True):
    """Update a master subdepartment."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("UPDATE subdepartments SET name = %s, is_active = %s WHERE id = %s", (name, is_active, subdept_id))
    conn.commit()
    release_db(conn)


def delete_master_subdepartment(subdept_id):
    """Soft delete a master subdepartment."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute("UPDATE subdepartments SET is_active = FALSE WHERE id = %s", (subdept_id,))
    conn.commit()
    release_db(conn)
