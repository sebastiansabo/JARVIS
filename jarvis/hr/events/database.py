"""HR Module Database Operations."""
from database import get_db, get_cursor, release_db, dict_from_row
from core.organization.ghost import ghost_exclude_clause
from core.utils.scope_filter import apply_scope_filter
from .presence import derive_bonus_fields


def _replace_bonus_days(cursor, bonus_id, presence_days, day_hours=None):
    """Replace the presence-day rows for a bonus with the given dates (same txn).

    ``day_hours`` (optional) maps ``'YYYY-MM-DD' -> {'start': h, 'end': h}`` and
    stores the per-day worked interval (whole hours). Days absent from the map
    are written with NULL hours.
    """
    day_hours = day_hours or {}
    cursor.execute('DELETE FROM hr.event_bonus_days WHERE bonus_id = %s', (bonus_id,))
    for d in presence_days:
        interval = day_hours.get(str(d)[:10]) or {}
        cursor.execute(
            'INSERT INTO hr.event_bonus_days (bonus_id, day, start_hour, end_hour) '
            'VALUES (%s, %s, %s, %s) '
            'ON CONFLICT (bonus_id, day) DO NOTHING',
            (bonus_id, d, interval.get('start'), interval.get('end')))


# ============== HR Employees (now using users table) ==============

def get_all_hr_employees(active_only=True, scope='all', user_context=None, contract_status=None):
    """Get all HR employees from users table with scope-based filtering.

    Args:
        active_only: If True, only return active employees
        scope: Permission scope ('own', 'department', 'all')
        user_context: Dict with user_id, company, department for scope filtering
        contract_status: Filter by contract status ('active', 'suspended', 'closed')
    """
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        query = '''
            SELECT id, name, email, phone, department AS departments, subdepartment, company, brand,
                   notify_on_allocation, notify_missing_punch, schedule_flexible, flex_start, flex_end,
                   is_active, contract_status, created_at, updated_at
            FROM users
            WHERE 1=1
        '''
        params = []

        if contract_status:
            query += ' AND contract_status = %s'
            params.append(contract_status)
        elif active_only:
            query += ' AND is_active = TRUE'

        scope_sql, scope_params = apply_scope_filter(scope, user_context)
        query += scope_sql
        params.extend(scope_params)

        gfrag, gargs = ghost_exclude_clause('id')
        query += gfrag
        params += gargs

        query += ' ORDER BY name'

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict_from_row(row) for row in rows]


    finally:
        release_db(conn)
def get_hr_employee(employee_id):
    """Get a single HR employee by ID from users table."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('''
            SELECT id, name, email, phone, department AS departments, subdepartment, company, brand,
                   notify_on_allocation, notify_missing_punch, schedule_flexible, flex_start, flex_end,
                   is_active, contract_status, created_at, updated_at
            FROM users WHERE id = %s
        ''', (employee_id,))
        row = cursor.fetchone()
        return dict_from_row(row) if row else None


    finally:
        release_db(conn)
def save_hr_employee(name, department=None, subdepartment=None, brand=None, company=None,
                     email=None, phone=None, notify_on_allocation=True):
    """Create a new HR employee in users table."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('''
            INSERT INTO users (name, department, subdepartment, brand, company, email, phone, notify_on_allocation)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (name, department, subdepartment, brand, company, email, phone, notify_on_allocation))
        employee_id = cursor.fetchone()['id']
        conn.commit()
        return employee_id


    finally:
        release_db(conn)
def update_hr_employee(employee_id, name=None, department=None, subdepartment=None, brand=None, company=None,
                       email=None, phone=None, notify_on_allocation=None, is_active=None,
                       contract_status=None, notify_missing_punch=None,
                       schedule_flexible=None, flex_start=None, flex_end=None):
    """Update an HR employee in users table. All fields use COALESCE for partial updates
    (None keeps the current value). schedule_flexible/flex_start/flex_end drive the
    flexible leave-permit window; when schedule_flexible is False the bounds are ignored
    downstream, so they need no clearing."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('''
            UPDATE users
            SET name = COALESCE(%s, name),
                department = COALESCE(%s, department),
                subdepartment = COALESCE(%s, subdepartment),
                brand = COALESCE(%s, brand),
                company = COALESCE(%s, company),
                email = COALESCE(%s, email),
                phone = COALESCE(%s, phone),
                notify_on_allocation = COALESCE(%s, notify_on_allocation),
                is_active = COALESCE(%s, is_active),
                contract_status = COALESCE(%s, contract_status),
                notify_missing_punch = COALESCE(%s, notify_missing_punch),
                schedule_flexible = COALESCE(%s, schedule_flexible),
                flex_start = COALESCE(%s, flex_start),
                flex_end = COALESCE(%s, flex_end),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (name, department, subdepartment, brand, company, email, phone, notify_on_allocation,
              is_active, contract_status, notify_missing_punch,
              schedule_flexible, flex_start, flex_end, employee_id))
        conn.commit()


    finally:
        release_db(conn)
def delete_hr_employee(employee_id):
    """Soft delete an HR employee (set contract_status = 'closed', trigger syncs is_active)."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('''
            UPDATE users SET contract_status = 'closed', updated_at = CURRENT_TIMESTAMP WHERE id = %s
        ''', (employee_id,))
        conn.commit()


    finally:
        release_db(conn)
def search_hr_employees(query):
    """Search HR employees by name from users table (active + suspended)."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('''
            SELECT id, name, email, phone, department AS departments, subdepartment, company, brand,
                   notify_on_allocation, notify_missing_punch, schedule_flexible, flex_start, flex_end,
                   is_active, contract_status, created_at, updated_at
            FROM users
            WHERE is_active = TRUE AND name ILIKE %s
            ORDER BY name
            LIMIT 20
        ''', (f'%{query}%',))
        rows = cursor.fetchall()
        return [dict_from_row(row) for row in rows]


    finally:
        release_db(conn)
# ============== HR Events ==============

def get_all_hr_events(limit=200, offset=0):
    """Get HR events ordered by date, with optional pagination."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('''
            SELECT e.*, u.name as created_by_name,
                   (SELECT COUNT(*) FROM hr.event_bonuses eb WHERE eb.event_id = e.id) AS participants_count
            FROM hr.events e
            LEFT JOIN public.users u ON e.created_by = u.id
            ORDER BY e.start_date DESC
            LIMIT %s OFFSET %s
        ''', (limit, offset))
        rows = cursor.fetchall()
        return [dict_from_row(row) for row in rows]


    finally:
        release_db(conn)
def get_hr_event(event_id):
    """Get a single HR event by ID."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('''
            SELECT e.*, u.name as created_by_name
            FROM hr.events e
            LEFT JOIN public.users u ON e.created_by = u.id
            WHERE e.id = %s
        ''', (event_id,))
        row = cursor.fetchone()
        return dict_from_row(row)


    finally:
        release_db(conn)
def save_hr_event(name, start_date, end_date, company=None, brand=None, description=None, created_by=None):
    """Create a new HR event."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('''
            INSERT INTO hr.events (name, start_date, end_date, company, brand, description, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (name, start_date, end_date, company, brand, description, created_by))
        event_id = cursor.fetchone()['id']
        conn.commit()
        return event_id


    finally:
        release_db(conn)
def update_hr_event(event_id, name, start_date, end_date, company=None, brand=None, description=None):
    """Update an HR event."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('''
            UPDATE hr.events
            SET name = %s, start_date = %s, end_date = %s, company = %s, brand = %s, description = %s
            WHERE id = %s
        ''', (name, start_date, end_date, company, brand, description, event_id))
        conn.commit()


    finally:
        release_db(conn)
def delete_hr_event(event_id):
    """Delete an HR event (cascades to bonuses)."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('DELETE FROM hr.events WHERE id = %s', (event_id,))
        conn.commit()


    finally:
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
    try:
        cursor = get_cursor(conn)
        placeholders = ','.join(['%s'] * len(event_ids))
        cursor.execute(f'DELETE FROM hr.events WHERE id IN ({placeholders})', tuple(event_ids))
        deleted_count = cursor.rowcount
        conn.commit()
        return deleted_count


    finally:
        release_db(conn)
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
    try:
        cursor = get_cursor(conn)

        # user_id references users.id directly.
        # period.* = the days & money that fall in the requested year[/month]
        # (pro-rata via the per-day view); mirrors the whole bonus when unfiltered.
        period_cond = 'TRUE'
        period_params = []
        if year:
            period_cond = 'vd.year = %s'
            period_params.append(year)
            if month:
                period_cond += ' AND vd.month = %s'
                period_params.append(month)

        query = f'''
            SELECT b.*, u.name as employee_name, u.department, u.brand,
                   COALESCE(co.company, u.company) AS company,
                   ev.name as event_name, ev.start_date as event_start, ev.end_date as event_end,
                   creator.name as created_by_name,
                   b.user_id as effective_employee_id,
                   period.period_bonus_days,
                   period.period_bonus_net,
                   period.period_event_hours AS event_hours
            FROM hr.event_bonuses b
            LEFT JOIN public.users u ON u.id = b.user_id
            LEFT JOIN public.companies co ON co.id = u.company_id
            JOIN hr.events ev ON b.event_id = ev.id
            LEFT JOIN public.users creator ON b.created_by = creator.id
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS period_bonus_days,
                       COALESCE(SUM(vd.day_net), 0) AS period_bonus_net,
                       COALESCE(SUM(vd.day_event_hours), 0) AS period_event_hours
                FROM hr.v_event_bonus_days vd
                WHERE vd.bonus_id = b.id AND {period_cond}
            ) period ON TRUE
            WHERE 1=1
        '''
        params = list(period_params)

        if year:
            # Day-based membership: a bonus appears for a period if ANY of its
            # days fall in it (so a boundary-spanning bonus shows in both months).
            query += ' AND EXISTS (SELECT 1 FROM hr.v_event_bonus_days vd2 WHERE vd2.bonus_id = b.id AND vd2.year = %s'
            params.append(year)
            if month:
                query += ' AND vd2.month = %s'
                params.append(month)
            query += ')'
        if employee_id:
            query += ' AND b.user_id = %s'
            params.append(employee_id)
        if event_id:
            query += ' AND b.event_id = %s'
            params.append(event_id)

        scope_sql, scope_params = apply_scope_filter(
            scope, user_context,
            user_id_col='b.user_id', dept_col='u.department', company_col='COALESCE(co.company, u.company)',
        )
        query += scope_sql
        params.extend(scope_params)

        gfrag, gargs = ghost_exclude_clause('b.user_id')
        query += gfrag
        params += gargs

        query += ' ORDER BY b.year DESC, b.month DESC, u.name'

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict_from_row(row) for row in rows]


    finally:
        release_db(conn)
def get_event_bonus(bonus_id):
    """Get a single event bonus by ID."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('''
            SELECT b.*, u.name as employee_name, u.department, u.brand,
                   COALESCE(co.company, u.company) AS company,
                   ev.name as event_name, ev.start_date as event_start, ev.end_date as event_end,
                   b.user_id as effective_employee_id
            FROM hr.event_bonuses b
            LEFT JOIN public.users u ON u.id = b.user_id
            LEFT JOIN public.companies co ON co.id = u.company_id
            JOIN hr.events ev ON b.event_id = ev.id
            WHERE b.id = %s
        ''', (bonus_id,))
        row = cursor.fetchone()
        return dict_from_row(row) if row else None


    finally:
        release_db(conn)
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
                     bonus_net=None, details=None, allocation_month=None, created_by=None,
                     presence_days=None, day_hours=None):
    """Create a new event bonus record using user_id (references users.id).

    When ``presence_days`` (a list of dates) is given it is the source of truth:
    year/month/participation_start/participation_end/bonus_days are derived from
    it and the per-day rows are written in the same transaction.
    """
    if presence_days:
        f = derive_bonus_fields(presence_days)
        year, month = f['year'], f['month']
        participation_start, participation_end = f['participation_start'], f['participation_end']
        bonus_days = f['bonus_days']
    conn = get_db()
    try:
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
        if presence_days:
            _replace_bonus_days(cursor, bonus_id, presence_days, day_hours)
        conn.commit()
        return bonus_id


    finally:
        release_db(conn)
def save_event_bonuses_bulk(bonuses, created_by=None):
    """Bulk create event bonus records using user_id (references users.id)."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        created_ids = []
        for b in bonuses:
            presence_days = b.get('presence_days')
            year, month = b['year'], b['month']
            participation_start = b.get('participation_start')
            participation_end = b.get('participation_end')
            bonus_days = b.get('bonus_days')
            if presence_days:
                f = derive_bonus_fields(presence_days)
                year, month = f['year'], f['month']
                participation_start, participation_end = f['participation_start'], f['participation_end']
                bonus_days = f['bonus_days']
            cursor.execute('''
                INSERT INTO hr.event_bonuses
                (user_id, event_id, year, month, participation_start, participation_end,
                 bonus_days, hours_free, bonus_net, details, allocation_month, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (b['employee_id'], b['event_id'], year, month,
                  participation_start, participation_end,
                  bonus_days, b.get('hours_free'), b.get('bonus_net'),
                  b.get('details'), b.get('allocation_month'), created_by))
            new_id = cursor.fetchone()['id']
            if presence_days:
                _replace_bonus_days(cursor, new_id, presence_days, b.get('day_hours'))
            created_ids.append(new_id)

        conn.commit()
        return created_ids


    finally:
        release_db(conn)
def update_event_bonus(bonus_id, employee_id, event_id, year, month, participation_start=None,
                       participation_end=None, bonus_days=None, hours_free=None,
                       bonus_net=None, details=None, allocation_month=None,
                       presence_days=None, day_hours=None):
    """Update an event bonus record using user_id (references users.id).

    When ``presence_days`` is given it is the source of truth: the derived
    columns are recomputed and the day rows replaced in the same transaction.
    """
    if presence_days:
        f = derive_bonus_fields(presence_days)
        year, month = f['year'], f['month']
        participation_start, participation_end = f['participation_start'], f['participation_end']
        bonus_days = f['bonus_days']
    conn = get_db()
    try:
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
        if presence_days is not None:
            _replace_bonus_days(cursor, bonus_id, presence_days, day_hours)
        conn.commit()


    finally:
        release_db(conn)
def delete_event_bonus(bonus_id):
    """Delete an event bonus record."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('DELETE FROM hr.event_bonuses WHERE id = %s', (bonus_id,))
        conn.commit()


    finally:
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
    try:
        cursor = get_cursor(conn)
        # Use parameterized query with tuple expansion
        placeholders = ','.join(['%s'] * len(bonus_ids))
        cursor.execute(f'DELETE FROM hr.event_bonuses WHERE id IN ({placeholders})', tuple(bonus_ids))
        deleted_count = cursor.rowcount
        conn.commit()
        return deleted_count


    finally:
        release_db(conn)
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
    try:
        cursor = get_cursor(conn)
        placeholders = ','.join(['%s'] * len(employee_ids))
        cursor.execute(f'DELETE FROM hr.event_bonuses WHERE user_id IN ({placeholders})', tuple(employee_ids))
        deleted_count = cursor.rowcount
        conn.commit()
        return deleted_count


    finally:
        release_db(conn)
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
    try:
        cursor = get_cursor(conn)

        total_deleted = 0
        for sel in selections:
            cursor.execute(
                'DELETE FROM hr.event_bonuses WHERE event_id = %s AND year = %s AND month = %s',
                (sel['event_id'], sel['year'], sel['month'])
            )
            total_deleted += cursor.rowcount

        conn.commit()
        return total_deleted


    finally:
        release_db(conn)
# ============== Summary/Stats ==============

def get_event_bonuses_summary(year=None):
    """Get summary stats for event bonuses."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        query = '''
            SELECT
                COUNT(DISTINCT b.user_id) as total_employees,
                COUNT(DISTINCT b.event_id) as total_events,
                COUNT(*) as total_bonuses,
                SUM(b.bonus_net) as total_bonus_amount,
                SUM(b.hours_free) as total_hours,
                COALESCE(SUM(eh.event_hours), 0) as total_event_hours,
                SUM(b.bonus_days) as total_days
            FROM hr.event_bonuses b
            LEFT JOIN (
                SELECT bonus_id, SUM(end_hour - start_hour) AS event_hours
                FROM hr.event_bonus_days
                WHERE start_hour IS NOT NULL AND end_hour IS NOT NULL
                GROUP BY bonus_id
            ) eh ON eh.bonus_id = b.id
            WHERE 1=1
        '''
        params = []
        if year:
            query += ' AND b.year = %s'
            params.append(year)

        gfrag, gargs = ghost_exclude_clause('b.user_id')
        query += gfrag
        params += gargs

        cursor.execute(query, params)
        row = cursor.fetchone()
        return dict_from_row(row)


    finally:
        release_db(conn)
def get_bonuses_by_month(year):
    """Get bonus totals grouped by the month each presence DAY falls in.

    Money is split pro-rata (day_net) so a bonus whose days straddle a month
    boundary contributes its share to each month it touches.
    """
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        gfrag, gargs = ghost_exclude_clause('vd.user_id')
        query = '''
            SELECT vd.month AS month,
                   COUNT(DISTINCT vd.bonus_id) as count,
                   SUM(vd.day_net) as total
            FROM hr.v_event_bonus_days vd
            WHERE vd.year = %s
        ''' + gfrag + '''
            GROUP BY vd.month
            ORDER BY vd.month
        '''
        params = [year] + gargs

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict_from_row(row) for row in rows]


    finally:
        release_db(conn)
def get_bonuses_by_employee(year=None, month=None):
    """Get bonus totals grouped by employee from users table."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        # Day-based: money (day_net) and days split by the month they fall in;
        # hours_free is attributed to the bonus's primary day so it counts once.
        query = '''
            SELECT u.id, u.name, u.department, COALESCE(co.company, u.company) AS company, u.brand,
                   COUNT(DISTINCT vd.bonus_id) as bonus_count,
                   COUNT(*) as total_days,
                   COALESCE(SUM(CASE WHEN vd.is_primary_day THEN vd.hours_free ELSE 0 END), 0) as total_hours,
                   COALESCE(SUM(vd.day_event_hours), 0) as total_event_hours,
                   COALESCE(SUM(vd.day_net), 0) as total_bonus
            FROM hr.v_event_bonus_days vd
            LEFT JOIN public.users u ON u.id = vd.user_id
            LEFT JOIN public.companies co ON co.id = u.company_id
            WHERE 1=1
        '''
        params = []
        if year:
            query += ' AND vd.year = %s'
            params.append(year)
        if month:
            query += ' AND vd.month = %s'
            params.append(month)

        gfrag, gargs = ghost_exclude_clause('vd.user_id')
        query += gfrag
        params += gargs

        query += ' GROUP BY u.id, u.name, u.department, co.company, u.company, u.brand ORDER BY total_bonus DESC'

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict_from_row(row) for row in rows]


    finally:
        release_db(conn)
def get_bonuses_by_event(year=None, month=None):
    """Get bonus totals grouped by event, year, and month."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        # Day-based: an event's bonuses split across the months their days fall in.
        query = '''
            SELECT e.id, e.name, e.start_date, e.end_date, e.company, e.brand,
                   vd.year, vd.month,
                   COUNT(DISTINCT vd.bonus_id) as bonus_count,
                   COUNT(DISTINCT vd.user_id) as employee_count,
                   COUNT(*) as total_days,
                   COALESCE(SUM(CASE WHEN vd.is_primary_day THEN vd.hours_free ELSE 0 END), 0) as total_hours,
                   COALESCE(SUM(vd.day_event_hours), 0) as total_event_hours,
                   COALESCE(SUM(vd.day_net), 0) as total_bonus
            FROM hr.v_event_bonus_days vd
            JOIN hr.events e ON e.id = vd.event_id
            WHERE 1=1
        '''
        params = []
        if year:
            query += ' AND vd.year = %s'
            params.append(year)
        if month:
            query += ' AND vd.month = %s'
            params.append(month)

        gfrag, gargs = ghost_exclude_clause('vd.user_id')
        query += gfrag
        params += gargs

        query += ' GROUP BY e.id, e.name, e.start_date, e.end_date, e.company, e.brand, vd.year, vd.month ORDER BY vd.year DESC, vd.month DESC, total_bonus DESC'

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict_from_row(row) for row in rows]


    finally:
        release_db(conn)
# ============== HR Bonus Types ==============

def get_all_bonus_types(active_only=True):
    """Get all bonus types, including restricted employee name."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        query = '''
            SELECT bt.*, u.name AS restricted_to_user_name
            FROM hr.bonus_types bt
            LEFT JOIN public.users u ON u.id = bt.restricted_to_user_id
        '''
        if active_only:
            query += ' WHERE bt.is_active = TRUE'
        query += ' ORDER BY bt.name'

        cursor.execute(query)
        rows = cursor.fetchall()
        return [dict_from_row(row) for row in rows]


    finally:
        release_db(conn)
def get_bonus_type(bonus_type_id):
    """Get a single bonus type by ID."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('''
            SELECT bt.*, u.name AS restricted_to_user_name
            FROM hr.bonus_types bt
            LEFT JOIN public.users u ON u.id = bt.restricted_to_user_id
            WHERE bt.id = %s
        ''', (bonus_type_id,))
        row = cursor.fetchone()
        return dict_from_row(row)


    finally:
        release_db(conn)
def save_bonus_type(name, amount, days_per_amount=1, description=None, restricted_to_user_id=None):
    """Create a new bonus type."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('''
            INSERT INTO hr.bonus_types (name, amount, days_per_amount, description, restricted_to_user_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', (name, amount, days_per_amount, description, restricted_to_user_id))
        bonus_type_id = cursor.fetchone()['id']
        conn.commit()
        return bonus_type_id


    finally:
        release_db(conn)
def update_bonus_type(bonus_type_id, name, amount, days_per_amount=1, description=None,
                      is_active=True, restricted_to_user_id=None):
    """Update a bonus type."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('''
            UPDATE hr.bonus_types
            SET name = %s, amount = %s, days_per_amount = %s, description = %s,
                is_active = %s, restricted_to_user_id = %s
            WHERE id = %s
        ''', (name, amount, days_per_amount, description, is_active, restricted_to_user_id, bonus_type_id))
        conn.commit()


    finally:
        release_db(conn)
def delete_bonus_type(bonus_type_id):
    """Soft delete a bonus type (set is_active = FALSE)."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute('''
            UPDATE hr.bonus_types SET is_active = FALSE WHERE id = %s
        ''', (bonus_type_id,))
        conn.commit()


    finally:
        release_db(conn)
# ============== Companies CRUD ==============

def get_all_companies_with_brands():
    """Get all companies with their brands."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("""
            SELECT id, company, vat, created_at, parent_company_id, display_order
            FROM companies
            ORDER BY display_order, company
        """)
        companies = [dict_from_row(row) for row in cursor.fetchall()]

        # Get brands for each company
        cursor.execute("""
            SELECT cb.company_id, b.name AS brand
            FROM company_brands cb
            JOIN brands b ON b.id = cb.brand_id
            WHERE cb.is_active = TRUE
        """)
        brand_rows = cursor.fetchall()

        brands_by_company = {}
        for row in brand_rows:
            cid = row['company_id']
            if cid not in brands_by_company:
                brands_by_company[cid] = []
            brands_by_company[cid].append(row['brand'])

        for c in companies:
            c['brands'] = brands_by_company.get(c['id'], [])

        return companies


    finally:
        release_db(conn)
def _would_create_cycle(cursor, company_id, proposed_parent_id):
    """Walk up the parent chain from proposed_parent_id. If we reach company_id, it's a cycle."""
    if proposed_parent_id is None:
        return False
    if proposed_parent_id == company_id:
        return True
    visited = set()
    current = proposed_parent_id
    while current is not None:
        if current in visited:
            return True
        if current == company_id:
            return True
        visited.add(current)
        cursor.execute("SELECT parent_company_id FROM companies WHERE id = %s", (current,))
        row = cursor.fetchone()
        current = row['parent_company_id'] if row else None
    return False


def create_company(company_name, vat=None, parent_company_id=None):
    """Create a new company."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("""
            INSERT INTO companies (company, vat, parent_company_id)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (company_name, vat, parent_company_id))
        company_id = cursor.fetchone()['id']
        conn.commit()
        return company_id


    finally:
        release_db(conn)
def update_company(company_id, company_name, vat=None, parent_company_id=None):
    """Update a company."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        if _would_create_cycle(cursor, company_id, parent_company_id):
            raise ValueError("Cannot set parent: would create a circular reference")
        cursor.execute("""
            UPDATE companies
            SET company = %s, vat = %s, parent_company_id = %s
            WHERE id = %s
        """, (company_name, vat, parent_company_id, company_id))
        conn.commit()


    finally:
        release_db(conn)
def delete_company(company_id):
    """Delete a company. Detaches children to root level."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("UPDATE companies SET parent_company_id = NULL WHERE parent_company_id = %s", (company_id,))
        cursor.execute("DELETE FROM companies WHERE id = %s", (company_id,))
        conn.commit()


    finally:
        release_db(conn)
# ============== Company Brands CRUD ==============

def get_all_company_brands(company_id=None):
    """Get all company brands, optionally filtered by company."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        if company_id:
            cursor.execute("""
                SELECT cb.id, cb.company_id, c.company, b.name AS brand, cb.is_active, cb.created_at
                FROM company_brands cb
                JOIN companies c ON cb.company_id = c.id
                JOIN brands b ON cb.brand_id = b.id
                WHERE cb.company_id = %s AND cb.is_active = TRUE
                ORDER BY b.name
            """, (company_id,))
        else:
            cursor.execute("""
                SELECT cb.id, cb.company_id, c.company, b.name AS brand, cb.is_active, cb.created_at
                FROM company_brands cb
                JOIN companies c ON cb.company_id = c.id
                JOIN brands b ON cb.brand_id = b.id
                WHERE cb.is_active = TRUE
                ORDER BY c.company, b.name
            """)

        rows = cursor.fetchall()
        return [dict_from_row(r) for r in rows]


    finally:
        release_db(conn)
def get_brand_id_by_name(brand_name):
    """Look up brand ID by name from master brands table."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("SELECT id FROM brands WHERE name = %s AND is_active = TRUE", (brand_name,))
        row = cursor.fetchone()
        return row['id'] if row else None


    finally:
        release_db(conn)
def create_company_brand(company_id, brand):
    """Create a new company brand.

    Args:
        company_id: The company ID
        brand: Either a brand ID (int) or brand name (str)
    """
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        # Handle both brand_id (int) and brand name (str)
        if isinstance(brand, str):
            brand_id = get_brand_id_by_name(brand)
            if not brand_id:
                raise ValueError(f"Brand '{brand}' not found in master brands table")
        else:
            brand_id = brand

        cursor.execute("""
            INSERT INTO company_brands (company_id, brand_id)
            VALUES (%s, %s)
            RETURNING id
        """, (company_id, brand_id))
        cb_id = cursor.fetchone()['id']
        conn.commit()
        return cb_id


    finally:
        release_db(conn)
def update_company_brand(cb_id, company_id, brand, is_active=True):
    """Update a company brand.

    Args:
        cb_id: The company_brands row ID
        company_id: The company ID (or None to keep existing)
        brand: Either a brand ID (int) or brand name (str)
        is_active: Whether the brand is active
    """
    conn = get_db()
    try:
        cursor = get_cursor(conn)

        # Handle both brand_id (int) and brand name (str)
        if isinstance(brand, str):
            brand_id = get_brand_id_by_name(brand)
            if not brand_id:
                raise ValueError(f"Brand '{brand}' not found in master brands table")
        else:
            brand_id = brand

        if company_id is not None:
            cursor.execute("""
                UPDATE company_brands
                SET company_id = %s, brand_id = %s, is_active = %s
                WHERE id = %s
            """, (company_id, brand_id, is_active, cb_id))
        else:
            cursor.execute("""
                UPDATE company_brands
                SET brand_id = %s, is_active = %s
                WHERE id = %s
            """, (brand_id, is_active, cb_id))
        conn.commit()


    finally:
        release_db(conn)
def delete_company_brand(brand_id):
    """Delete a company brand."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("DELETE FROM company_brands WHERE id = %s", (brand_id,))
        conn.commit()


    finally:
        release_db(conn)
# ============== Department Structure CRUD ==============

def get_all_department_structures():
    """Get all department structure entries."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("""
            SELECT ds.id, ds.company, ds.brand, ds.department, ds.subdepartment,
                   ds.manager, ds.company_id, ds.manager_ids, ds.cc_email
            FROM department_structure ds
            ORDER BY ds.company, ds.brand, ds.department
        """)
        rows = cursor.fetchall()
        return [dict_from_row(r) for r in rows]


    finally:
        release_db(conn)
def create_department_structure(company_id, manager, company, brand, department, subdepartment, manager_ids=None, cc_email=None):
    """Create a new department structure entry."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("""
            INSERT INTO department_structure (company_id, manager, company, brand, department, subdepartment, manager_ids, cc_email)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (company_id, manager, company, brand, department, subdepartment, manager_ids, cc_email))
        struct_id = cursor.fetchone()['id']
        conn.commit()
        return struct_id


    finally:
        release_db(conn)
def update_department_structure(struct_id, company_id, manager, company, brand, department, subdepartment, manager_ids=None, cc_email=None):
    """Update a department structure entry."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("""
            UPDATE department_structure
            SET company_id = %s, manager = %s, company = %s, brand = %s,
                department = %s, subdepartment = %s, manager_ids = %s, cc_email = %s
            WHERE id = %s
        """, (company_id, manager, company, brand, department, subdepartment, manager_ids, cc_email, struct_id))
        conn.commit()


    finally:
        release_db(conn)
def delete_department_structure(struct_id):
    """Delete a department structure entry."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("DELETE FROM department_structure WHERE id = %s", (struct_id,))
        conn.commit()


    finally:
        release_db(conn)
def get_managed_employee_ids(manager_user_id, node_id=None):
    """Get all user IDs that are team members under this user in the organigram."""
    from core.organization.manager_utils import get_managed_employee_ids as _f
    return _f(manager_user_id, node_id)


def get_visible_tree(manager_user_id):
    """Get the organigram tree visible to this manager for filtering."""
    from core.organization.manager_utils import get_visible_tree as _f
    return _f(manager_user_id)


def is_manager(user_id):
    """Check if a user is a responsable on any organigram node or company."""
    from core.organization.manager_utils import is_manager as _f
    return _f(user_id)
_ALLOWED_LOOKUP_TABLES = frozenset({
    'companies', 'brands', 'departments', 'subdepartments',
    'positions', 'locations', 'cost_centers',
})


def get_name_by_id(table, id_value):
    """Get name from a lookup table by ID."""
    if not id_value:
        return None
    if table not in _ALLOWED_LOOKUP_TABLES:
        return None
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        if table == 'companies':
            cursor.execute("SELECT company as name FROM companies WHERE id = %s", (id_value,))
        else:
            cursor.execute(f"SELECT name FROM {table} WHERE id = %s", (id_value,))
        row = cursor.fetchone()
        return row['name'] if row else None


    finally:
        release_db(conn)
# ============== Master Tables CRUD (brands, departments, subdepartments) ==============

def get_all_master_brands():
    """Get all master brands."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("SELECT id, name, is_active FROM brands WHERE is_active = TRUE ORDER BY name")
        rows = cursor.fetchall()
        return [dict_from_row(r) for r in rows]


    finally:
        release_db(conn)
def create_master_brand(name):
    """Create a new master brand."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("INSERT INTO brands (name) VALUES (%s) RETURNING id", (name,))
        brand_id = cursor.fetchone()['id']
        conn.commit()
        return brand_id


    finally:
        release_db(conn)
def update_master_brand(brand_id, name, is_active=True):
    """Update a master brand."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("UPDATE brands SET name = %s, is_active = %s WHERE id = %s", (name, is_active, brand_id))
        conn.commit()


    finally:
        release_db(conn)
def delete_master_brand(brand_id):
    """Soft delete a master brand."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("UPDATE brands SET is_active = FALSE WHERE id = %s", (brand_id,))
        conn.commit()


    finally:
        release_db(conn)
def get_all_master_departments():
    """Get all master departments."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("SELECT id, name, is_active FROM departments WHERE is_active = TRUE ORDER BY name")
        rows = cursor.fetchall()
        return [dict_from_row(r) for r in rows]


    finally:
        release_db(conn)
def create_master_department(name):
    """Create a new master department."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("INSERT INTO departments (name) VALUES (%s) RETURNING id", (name,))
        dept_id = cursor.fetchone()['id']
        conn.commit()
        return dept_id


    finally:
        release_db(conn)
def update_master_department(dept_id, name, is_active=True):
    """Update a master department."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("UPDATE departments SET name = %s, is_active = %s WHERE id = %s", (name, is_active, dept_id))
        conn.commit()


    finally:
        release_db(conn)
def delete_master_department(dept_id):
    """Soft delete a master department."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("UPDATE departments SET is_active = FALSE WHERE id = %s", (dept_id,))
        conn.commit()


    finally:
        release_db(conn)
def get_all_master_subdepartments():
    """Get all master subdepartments."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("SELECT id, name, is_active FROM subdepartments WHERE is_active = TRUE ORDER BY name")
        rows = cursor.fetchall()
        return [dict_from_row(r) for r in rows]


    finally:
        release_db(conn)
def create_master_subdepartment(name):
    """Create a new master subdepartment."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("INSERT INTO subdepartments (name) VALUES (%s) RETURNING id", (name,))
        subdept_id = cursor.fetchone()['id']
        conn.commit()
        return subdept_id


    finally:
        release_db(conn)
def update_master_subdepartment(subdept_id, name, is_active=True):
    """Update a master subdepartment."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("UPDATE subdepartments SET name = %s, is_active = %s WHERE id = %s", (name, is_active, subdept_id))
        conn.commit()


    finally:
        release_db(conn)
def delete_master_subdepartment(subdept_id):
    """Soft delete a master subdepartment."""
    conn = get_db()
    try:
        cursor = get_cursor(conn)
        cursor.execute("UPDATE subdepartments SET is_active = FALSE WHERE id = %s", (subdept_id,))
        conn.commit()
    finally:
        release_db(conn)
