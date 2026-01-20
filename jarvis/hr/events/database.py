"""HR Module Database Operations."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db, get_cursor, release_db, dict_from_row


# ============== HR Employees ==============

def get_all_hr_employees(active_only=True):
    """Get all HR employees."""
    conn = get_db()
    cursor = get_cursor(conn)

    query = 'SELECT * FROM hr.employees'
    if active_only:
        query += ' WHERE is_active = TRUE'
    query += ' ORDER BY name'

    cursor.execute(query)
    rows = cursor.fetchall()
    release_db(conn)
    return [dict_from_row(row) for row in rows]


def get_hr_employee(employee_id):
    """Get a single HR employee by ID."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('SELECT * FROM hr.employees WHERE id = %s', (employee_id,))
    row = cursor.fetchone()
    release_db(conn)
    return dict_from_row(row)


def save_hr_employee(name, department=None, brand=None, company=None, user_id=None):
    """Create a new HR employee."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('''
        INSERT INTO hr.employees (name, department, brand, company, user_id)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
    ''', (name, department, brand, company, user_id))
    employee_id = cursor.fetchone()['id']
    conn.commit()
    release_db(conn)
    return employee_id


def update_hr_employee(employee_id, name, department=None, brand=None, company=None, user_id=None, is_active=True):
    """Update an HR employee."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('''
        UPDATE hr.employees
        SET name = %s, department = %s, brand = %s, company = %s, user_id = %s,
            is_active = %s, updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
    ''', (name, department, brand, company, user_id, is_active, employee_id))
    conn.commit()
    release_db(conn)


def delete_hr_employee(employee_id):
    """Soft delete an HR employee (set is_active = FALSE)."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('''
        UPDATE hr.employees SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP WHERE id = %s
    ''', (employee_id,))
    conn.commit()
    release_db(conn)


def search_hr_employees(query):
    """Search HR employees by name."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('''
        SELECT * FROM hr.employees
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


# ============== HR Events ==============

def get_all_event_bonuses(year=None, month=None, employee_id=None, event_id=None):
    """Get event bonuses with optional filters."""
    conn = get_db()
    cursor = get_cursor(conn)

    query = '''
        SELECT b.*, e.name as employee_name, e.department, e.brand, e.company,
               ev.name as event_name, ev.start_date as event_start, ev.end_date as event_end,
               u.name as created_by_name
        FROM hr.event_bonuses b
        JOIN hr.employees e ON b.employee_id = e.id
        JOIN hr.events ev ON b.event_id = ev.id
        LEFT JOIN public.users u ON b.created_by = u.id
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
        query += ' AND b.employee_id = %s'
        params.append(employee_id)
    if event_id:
        query += ' AND b.event_id = %s'
        params.append(event_id)

    query += ' ORDER BY b.year DESC, b.month DESC, e.name'

    cursor.execute(query, params)
    rows = cursor.fetchall()
    release_db(conn)
    return [dict_from_row(row) for row in rows]


def get_event_bonus(bonus_id):
    """Get a single event bonus by ID."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('''
        SELECT b.*, e.name as employee_name, e.department, e.brand, e.company,
               ev.name as event_name, ev.start_date as event_start, ev.end_date as event_end
        FROM hr.event_bonuses b
        JOIN hr.employees e ON b.employee_id = e.id
        JOIN hr.events ev ON b.event_id = ev.id
        WHERE b.id = %s
    ''', (bonus_id,))
    row = cursor.fetchone()
    release_db(conn)
    return dict_from_row(row)


def save_event_bonus(employee_id, event_id, year, month, participation_start=None,
                     participation_end=None, bonus_days=None, hours_free=None,
                     bonus_net=None, details=None, allocation_month=None, created_by=None):
    """Create a new event bonus record."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('''
        INSERT INTO hr.event_bonuses
        (employee_id, event_id, year, month, participation_start, participation_end,
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
    """Bulk create event bonus records."""
    conn = get_db()
    cursor = get_cursor(conn)

    created_ids = []
    for b in bonuses:
        cursor.execute('''
            INSERT INTO hr.event_bonuses
            (employee_id, event_id, year, month, participation_start, participation_end,
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
    """Update an event bonus record."""
    conn = get_db()
    cursor = get_cursor(conn)
    cursor.execute('''
        UPDATE hr.event_bonuses
        SET employee_id = %s, event_id = %s, year = %s, month = %s,
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


# ============== Summary/Stats ==============

def get_event_bonuses_summary(year=None):
    """Get summary stats for event bonuses."""
    conn = get_db()
    cursor = get_cursor(conn)

    query = '''
        SELECT
            COUNT(DISTINCT b.employee_id) as total_employees,
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
    """Get bonus totals grouped by employee."""
    conn = get_db()
    cursor = get_cursor(conn)

    query = '''
        SELECT e.id, e.name, e.department, e.company, e.brand,
               COUNT(*) as bonus_count,
               COALESCE(SUM(b.bonus_days), 0) as total_days,
               COALESCE(SUM(b.hours_free), 0) as total_hours,
               COALESCE(SUM(b.bonus_net), 0) as total_bonus
        FROM hr.event_bonuses b
        JOIN hr.employees e ON b.employee_id = e.id
        WHERE 1=1
    '''
    params = []
    if year:
        query += ' AND b.year = %s'
        params.append(year)
    if month:
        query += ' AND b.month = %s'
        params.append(month)

    query += ' GROUP BY e.id, e.name, e.department, e.company, e.brand ORDER BY total_bonus DESC'

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
