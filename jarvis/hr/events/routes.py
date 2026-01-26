"""HR Module Routes."""
from functools import wraps
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user

from . import events_bp
from .database import (
    get_all_hr_employees, get_hr_employee, save_hr_employee,
    update_hr_employee, delete_hr_employee, search_hr_employees,
    get_all_hr_events, get_hr_event, save_hr_event, update_hr_event, delete_hr_event,
    get_all_event_bonuses, get_event_bonus, save_event_bonus,
    save_event_bonuses_bulk, update_event_bonus, delete_event_bonus,
    get_event_bonuses_summary, get_bonuses_by_month, get_bonuses_by_employee, get_bonuses_by_event,
    get_all_bonus_types, get_bonus_type, save_bonus_type, update_bonus_type, delete_bonus_type
)

# Import from app root for structure data
import sys
import os
# Go up two levels: events/ -> hr/ -> app/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from models import get_companies, get_brands_for_company, get_departments_for_company


def hr_required(f):
    """Decorator to require HR access permission."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        if not getattr(current_user, 'can_access_hr', False):
            flash('HR access required.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


# Romanian month names for display
MONTH_NAMES = {
    1: 'Ianuarie', 2: 'Februarie', 3: 'Martie', 4: 'Aprilie',
    5: 'Mai', 6: 'Iunie', 7: 'Iulie', 8: 'August',
    9: 'Septembrie', 10: 'Octombrie', 11: 'Noiembrie', 12: 'Decembrie'
}


# ============== Events Routes ==============

@events_bp.route('/')
@events_bp.route('/event-bonuses')
@login_required
@hr_required
def event_bonuses():
    """Events main page."""
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)

    bonuses = get_all_event_bonuses(year=year, month=month)
    events = get_all_hr_events()
    employees = get_all_hr_employees()
    summary = get_event_bonuses_summary(year=year)
    employee_summary = get_bonuses_by_employee(year=year, month=month)
    event_summary = get_bonuses_by_event(year=year, month=month)

    # Get unique years from bonuses for filter
    years = sorted(set(b['year'] for b in bonuses), reverse=True) if bonuses else [2025]

    return render_template('event_bonuses.html',
                           bonuses=bonuses,
                           events=events,
                           employees=employees,
                           summary=summary,
                           employee_summary=employee_summary,
                           event_summary=event_summary,
                           years=years,
                           months=MONTH_NAMES,
                           selected_year=year,
                           selected_month=month,
                           is_hr_manager=current_user.is_hr_manager)


@events_bp.route('/api/event-bonuses', methods=['GET'])
@login_required
@hr_required
def api_get_event_bonuses():
    """API: Get event bonuses with filters."""
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    employee_id = request.args.get('employee_id', type=int)
    event_id = request.args.get('event_id', type=int)

    bonuses = get_all_event_bonuses(year=year, month=month,
                                    employee_id=employee_id, event_id=event_id)
    return jsonify(bonuses)


@events_bp.route('/api/event-bonuses', methods=['POST'])
@login_required
@hr_required
def api_create_event_bonus():
    """API: Create a new event bonus."""
    data = request.get_json()

    bonus_id = save_event_bonus(
        employee_id=data['employee_id'],
        event_id=data['event_id'],
        year=data['year'],
        month=data['month'],
        participation_start=data.get('participation_start'),
        participation_end=data.get('participation_end'),
        bonus_days=data.get('bonus_days'),
        hours_free=data.get('hours_free'),
        bonus_net=data.get('bonus_net'),
        details=data.get('details'),
        allocation_month=data.get('allocation_month'),
        created_by=current_user.id
    )

    return jsonify({'success': True, 'id': bonus_id})


@events_bp.route('/api/event-bonuses/bulk', methods=['POST'])
@login_required
@hr_required
def api_create_event_bonuses_bulk():
    """API: Bulk create event bonuses."""
    data = request.get_json()
    bonuses = data.get('bonuses', [])

    if not bonuses:
        return jsonify({'success': False, 'error': 'No bonuses provided'}), 400

    created_ids = save_event_bonuses_bulk(bonuses, created_by=current_user.id)
    return jsonify({'success': True, 'ids': created_ids, 'count': len(created_ids)})


@events_bp.route('/api/event-bonuses/<int:bonus_id>', methods=['GET'])
@login_required
@hr_required
def api_get_event_bonus(bonus_id):
    """API: Get a single event bonus."""
    bonus = get_event_bonus(bonus_id)
    if not bonus:
        return jsonify({'error': 'Bonus not found'}), 404
    return jsonify(bonus)


@events_bp.route('/api/event-bonuses/<int:bonus_id>', methods=['PUT'])
@login_required
@hr_required
def api_update_event_bonus(bonus_id):
    """API: Update an event bonus."""
    data = request.get_json()

    update_event_bonus(
        bonus_id=bonus_id,
        employee_id=data['employee_id'],
        event_id=data['event_id'],
        year=data['year'],
        month=data['month'],
        participation_start=data.get('participation_start'),
        participation_end=data.get('participation_end'),
        bonus_days=data.get('bonus_days'),
        hours_free=data.get('hours_free'),
        bonus_net=data.get('bonus_net'),
        details=data.get('details'),
        allocation_month=data.get('allocation_month')
    )

    return jsonify({'success': True})


@events_bp.route('/api/event-bonuses/<int:bonus_id>', methods=['DELETE'])
@login_required
@hr_required
def api_delete_event_bonus(bonus_id):
    """API: Delete an event bonus."""
    delete_event_bonus(bonus_id)
    return jsonify({'success': True})


# ============== Events Routes ==============

@events_bp.route('/events')
@login_required
@hr_required
def events():
    """Events management page."""
    all_events = get_all_hr_events()
    companies = get_companies()
    return render_template('events.html', events=all_events, companies=companies)


@events_bp.route('/events/new')
@login_required
@hr_required
def add_event():
    """Add new event page."""
    companies = get_companies()
    employees = get_all_hr_employees(active_only=True)
    bonus_types = get_all_bonus_types(active_only=True)
    return render_template('add_event.html',
                           companies=companies,
                           employees=employees,
                           bonus_types=bonus_types,
                           is_hr_manager=current_user.is_hr_manager)


@events_bp.route('/bonuses/new')
@login_required
@hr_required
def add_bonus():
    """Add new bonus page."""
    from datetime import datetime
    events = get_all_hr_events()
    employees = get_all_hr_employees()
    bonus_types = get_all_bonus_types(active_only=True)
    return render_template('add_bonus.html',
                           events=events,
                           employees=employees,
                           bonus_types=bonus_types,
                           months=MONTH_NAMES,
                           current_year=datetime.now().year,
                           current_month=datetime.now().month,
                           is_hr_manager=current_user.is_hr_manager)


@events_bp.route('/api/events', methods=['GET'])
@login_required
@hr_required
def api_get_events():
    """API: Get all events."""
    events = get_all_hr_events()
    return jsonify(events)


@events_bp.route('/api/events', methods=['POST'])
@login_required
@hr_required
def api_create_event():
    """API: Create a new event."""
    data = request.get_json()

    event_id = save_hr_event(
        name=data['name'],
        start_date=data['start_date'],
        end_date=data['end_date'],
        company=data.get('company'),
        brand=data.get('brand'),
        description=data.get('description'),
        created_by=current_user.id
    )

    return jsonify({'success': True, 'id': event_id})


@events_bp.route('/api/events/<int:event_id>', methods=['GET'])
@login_required
@hr_required
def api_get_event(event_id):
    """API: Get a single event."""
    event = get_hr_event(event_id)
    if not event:
        return jsonify({'error': 'Event not found'}), 404
    return jsonify(event)


@events_bp.route('/api/events/<int:event_id>', methods=['PUT'])
@login_required
@hr_required
def api_update_event(event_id):
    """API: Update an event."""
    data = request.get_json()

    update_hr_event(
        event_id=event_id,
        name=data['name'],
        start_date=data['start_date'],
        end_date=data['end_date'],
        company=data.get('company'),
        brand=data.get('brand'),
        description=data.get('description')
    )

    return jsonify({'success': True})


@events_bp.route('/api/events/<int:event_id>', methods=['DELETE'])
@login_required
@hr_required
def api_delete_event(event_id):
    """API: Delete an event."""
    delete_hr_event(event_id)
    return jsonify({'success': True})


# ============== Employees API Routes ==============
# Note: Employee management page is now in core Settings (Settings → HR → Employees)
# These API routes are kept for HR Events module to fetch employees for bonuses

@events_bp.route('/api/employees', methods=['GET'])
@login_required
@hr_required
def api_get_employees():
    """API: Get all employees."""
    active_only = request.args.get('active_only', 'true').lower() == 'true'
    employees = get_all_hr_employees(active_only=active_only)
    return jsonify(employees)


@events_bp.route('/api/employees/search', methods=['GET'])
@login_required
@hr_required
def api_search_employees():
    """API: Search employees by name."""
    query = request.args.get('q', '')
    if len(query) < 2:
        return jsonify([])
    employees = search_hr_employees(query)
    return jsonify(employees)


@events_bp.route('/api/employees', methods=['POST'])
@login_required
@hr_required
def api_create_employee():
    """API: Create a new employee."""
    data = request.get_json()

    employee_id = save_hr_employee(
        name=data['name'],
        department=data.get('departments'),  # frontend sends 'departments'
        subdepartment=data.get('subdepartment'),
        brand=data.get('brand'),
        company=data.get('company'),
        email=data.get('email'),
        phone=data.get('phone'),
        notify_on_allocation=data.get('notify_on_allocation', True)
    )

    return jsonify({'success': True, 'id': employee_id})


@events_bp.route('/api/employees/<int:employee_id>', methods=['GET'])
@login_required
@hr_required
def api_get_employee(employee_id):
    """API: Get a single employee."""
    employee = get_hr_employee(employee_id)
    if not employee:
        return jsonify({'error': 'Employee not found'}), 404
    return jsonify(employee)


@events_bp.route('/api/employees/<int:employee_id>', methods=['PUT'])
@login_required
@hr_required
def api_update_employee(employee_id):
    """API: Update an employee."""
    data = request.get_json()

    update_hr_employee(
        employee_id=employee_id,
        name=data['name'],
        department=data.get('departments'),  # frontend sends 'departments'
        subdepartment=data.get('subdepartment'),
        brand=data.get('brand'),
        company=data.get('company'),
        email=data.get('email'),
        phone=data.get('phone'),
        notify_on_allocation=data.get('notify_on_allocation', True),
        is_active=data.get('is_active', True)
    )

    return jsonify({'success': True})


@events_bp.route('/api/employees/<int:employee_id>', methods=['DELETE'])
@login_required
@hr_required
def api_delete_employee(employee_id):
    """API: Soft delete an employee."""
    delete_hr_employee(employee_id)
    return jsonify({'success': True})


# ============== Summary/Stats Routes ==============

@events_bp.route('/api/summary', methods=['GET'])
@login_required
@hr_required
def api_get_summary():
    """API: Get summary statistics."""
    year = request.args.get('year', type=int)
    summary = get_event_bonuses_summary(year=year)
    return jsonify(summary)


@events_bp.route('/api/summary/by-month', methods=['GET'])
@login_required
@hr_required
def api_get_by_month():
    """API: Get bonuses grouped by month."""
    year = request.args.get('year', type=int, default=2025)
    data = get_bonuses_by_month(year)
    return jsonify(data)


@events_bp.route('/api/summary/by-employee', methods=['GET'])
@login_required
@hr_required
def api_get_by_employee():
    """API: Get bonuses grouped by employee."""
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    data = get_bonuses_by_employee(year=year, month=month)
    return jsonify(data)


# ============== Structure Data Routes ==============

@events_bp.route('/api/structure/companies', methods=['GET'])
@login_required
@hr_required
def api_get_companies():
    """API: Get all companies."""
    companies = get_companies()
    return jsonify(companies)


@events_bp.route('/api/structure/brands/<company>', methods=['GET'])
@login_required
@hr_required
def api_get_brands(company):
    """API: Get brands for a company."""
    brands = get_brands_for_company(company)
    return jsonify(brands)


@events_bp.route('/api/structure/departments/<company>', methods=['GET'])
@login_required
@hr_required
def api_get_departments(company):
    """API: Get departments for a company."""
    departments = get_departments_for_company(company)
    return jsonify(departments)


# ============== Companies CRUD API ==============

@events_bp.route('/api/structure/companies-full', methods=['GET'])
@login_required
@hr_required
def api_get_companies_full():
    """API: Get all companies with full details including brands from company_brands."""
    from database import get_db, get_cursor, release_db

    conn = get_db()
    try:
        cur = get_cursor(conn)

        # Get companies
        cur.execute("""
            SELECT id, company, vat, created_at
            FROM companies
            ORDER BY company
        """)
        companies = []
        for r in cur.fetchall():
            companies.append({
                'id': r['id'],
                'company': r['company'],
                'vat': r['vat'],
                'created_at': r['created_at'].isoformat() if r['created_at'] else None
            })

        # Get brands for all companies (JOIN with brands table to get name)
        cur.execute("""
            SELECT cb.id as cb_id, cb.company_id, cb.brand_id, b.name as brand
            FROM company_brands cb
            JOIN brands b ON cb.brand_id = b.id
            WHERE cb.is_active = TRUE ORDER BY b.name
        """)
        brands_by_company = {}
        for r in cur.fetchall():
            cid = r['company_id']
            if cid not in brands_by_company:
                brands_by_company[cid] = []
            brands_by_company[cid].append({
                'id': r['cb_id'],        # company_brands.id for update/delete
                'brand_id': r['brand_id'],  # brands.id (FK)
                'brand': r['brand']      # brand name
            })

        # Add brands to companies
        for company in companies:
            brand_list = brands_by_company.get(company['id'], [])
            company['brands'] = ', '.join(b['brand'] for b in brand_list)
            company['brands_list'] = brand_list  # Already has {id, brand} structure

        return jsonify(companies)
    finally:
        release_db(conn)


@events_bp.route('/api/structure/companies', methods=['POST'])
@login_required
@hr_required
def api_create_company():
    """API: Create a new company."""
    from database import get_db, get_cursor, release_db
    from models import clear_structure_cache

    data = request.get_json()
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("""
            INSERT INTO companies (company, vat)
            VALUES (%s, %s)
            RETURNING id
        """, (data['company'], data.get('vat')))
        company_id = cur.fetchone()['id']
        conn.commit()
        clear_structure_cache()
        return jsonify({'success': True, 'id': company_id})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    finally:
        release_db(conn)


@events_bp.route('/api/structure/companies/<int:company_id>', methods=['PUT'])
@login_required
@hr_required
def api_update_company(company_id):
    """API: Update a company."""
    from database import get_db, get_cursor, release_db
    from models import clear_structure_cache

    data = request.get_json()
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("""
            UPDATE companies
            SET company = %s, vat = %s
            WHERE id = %s
        """, (data['company'], data.get('vat'), company_id))
        conn.commit()
        clear_structure_cache()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    finally:
        release_db(conn)


@events_bp.route('/api/structure/companies/<int:company_id>', methods=['DELETE'])
@login_required
@hr_required
def api_delete_company(company_id):
    """API: Delete a company."""
    from jarvis.core.database import get_db_connection

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM companies WHERE id = %s", (company_id,))
        conn.commit()
        cur.close()

    return jsonify({'success': True})


# ============== Company Brands CRUD API ==============

@events_bp.route('/api/structure/company-brands', methods=['GET'])
@login_required
@hr_required
def api_get_company_brands():
    """API: Get all company brands."""
    from database import get_db, get_cursor, release_db, dict_from_row

    company_id = request.args.get('company_id', type=int)

    conn = get_db()
    try:
        cur = get_cursor(conn)

        if company_id:
            cur.execute("""
                SELECT cb.id, cb.company_id, c.company, cb.brand_id, b.name as brand, cb.is_active, cb.created_at
                FROM company_brands cb
                JOIN companies c ON cb.company_id = c.id
                JOIN brands b ON cb.brand_id = b.id
                WHERE cb.company_id = %s AND cb.is_active = TRUE
                ORDER BY b.name
            """, (company_id,))
        else:
            cur.execute("""
                SELECT cb.id, cb.company_id, c.company, cb.brand_id, b.name as brand, cb.is_active, cb.created_at
                FROM company_brands cb
                JOIN companies c ON cb.company_id = c.id
                JOIN brands b ON cb.brand_id = b.id
                WHERE cb.is_active = TRUE
                ORDER BY c.company, b.name
            """)

        rows = cur.fetchall()
        return jsonify([dict_from_row(r) for r in rows])
    finally:
        release_db(conn)


@events_bp.route('/api/structure/company-brands', methods=['POST'])
@login_required
@hr_required
def api_create_company_brand():
    """API: Create a new company brand."""
    from database import get_db, get_cursor, release_db
    from models import clear_structure_cache

    data = request.get_json()
    conn = get_db()
    cur = get_cursor(conn)

    try:
        cur.execute("""
            INSERT INTO company_brands (company_id, brand_id)
            VALUES (%s, %s)
            RETURNING id
        """, (data['company_id'], data['brand_id']))
        cb_id = cur.fetchone()['id']
        conn.commit()
        release_db(conn)
        clear_structure_cache()
        return jsonify({'success': True, 'id': cb_id})
    except Exception as e:
        conn.rollback()
        release_db(conn)
        return jsonify({'success': False, 'error': str(e)}), 400


@events_bp.route('/api/structure/company-brands/<int:brand_id>', methods=['PUT'])
@login_required
@hr_required
def api_update_company_brand(brand_id):
    """API: Update a company brand."""
    from database import get_db, get_cursor, release_db
    from models import clear_structure_cache

    data = request.get_json()
    conn = get_db()
    cur = get_cursor(conn)

    cur.execute("""
        UPDATE company_brands
        SET brand_id = %s, is_active = %s
        WHERE id = %s
    """, (data['brand_id'], data.get('is_active', True), brand_id))
    conn.commit()
    release_db(conn)
    clear_structure_cache()

    return jsonify({'success': True})


@events_bp.route('/api/structure/company-brands/<int:brand_id>', methods=['DELETE'])
@login_required
@hr_required
def api_delete_company_brand(brand_id):
    """API: Delete a company brand."""
    from database import get_db, get_cursor, release_db
    from models import clear_structure_cache

    conn = get_db()
    cur = get_cursor(conn)
    cur.execute("DELETE FROM company_brands WHERE id = %s", (brand_id,))
    conn.commit()
    release_db(conn)
    clear_structure_cache()

    return jsonify({'success': True})


@events_bp.route('/api/structure/companies/<int:company_id>/brands', methods=['GET'])
@login_required
@hr_required
def api_get_brands_for_company(company_id):
    """API: Get brands for a specific company."""
    from database import get_db, get_cursor, release_db, dict_from_row

    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("""
            SELECT cb.id, cb.brand_id, b.name as brand, cb.is_active
            FROM company_brands cb
            JOIN brands b ON cb.brand_id = b.id
            WHERE cb.company_id = %s AND cb.is_active = TRUE
            ORDER BY b.name
        """, (company_id,))
        rows = cur.fetchall()
        return jsonify([dict_from_row(r) for r in rows])
    finally:
        release_db(conn)


# ============== Departments CRUD API ==============

@events_bp.route('/api/structure/departments-full', methods=['GET'])
@login_required
@hr_required
def api_get_departments_full():
    """API: Get all department structure entries with full details."""
    from database import get_db, get_cursor, release_db

    conn = get_db()
    try:
        cur = get_cursor(conn)
        # department_structure stores values directly as TEXT, not as foreign keys
        cur.execute("""
            SELECT id, company, brand, department, subdepartment, manager, marketing, company_id
            FROM department_structure
            ORDER BY company, brand, department, subdepartment
        """)
        rows = cur.fetchall()
        return jsonify([{
            'id': r['id'],
            'company': r['company'],
            'brand': r['brand'],
            'department': r['department'],
            'subdepartment': r['subdepartment'],
            'manager': r['manager'],
            'marketing': r['marketing'],
            'company_id': r['company_id']
        } for r in rows])
    finally:
        release_db(conn)


@events_bp.route('/api/structure/departments', methods=['POST'])
@login_required
@hr_required
def api_create_department():
    """API: Create a new department structure entry."""
    from database import get_db, get_cursor, release_db
    from models import clear_structure_cache

    data = request.get_json()
    conn = get_db()
    try:
        cur = get_cursor(conn)

        # company_id is a real FK to companies table, look up the company name
        company_name = None
        company_id = data.get('company_id')
        if company_id:
            cur.execute("SELECT company FROM companies WHERE id = %s", (company_id,))
            row = cur.fetchone()
            if row:
                company_name = row['company']

        # brand_id, department_id, subdepartment_id are now TEXT values (the names themselves)
        brand_name = data.get('brand_id') or None
        dept_name = data.get('department_id') or None
        subdept_name = data.get('subdepartment_id') or None

        cur.execute("""
            INSERT INTO department_structure (company_id, company, brand, department, subdepartment, manager)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (company_id, company_name, brand_name, dept_name, subdept_name, data.get('manager')))
        dept_id = cur.fetchone()['id']
        conn.commit()
        clear_structure_cache()
        return jsonify({'success': True, 'id': dept_id})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    finally:
        release_db(conn)


@events_bp.route('/api/structure/departments/<int:dept_id>', methods=['PUT'])
@login_required
@hr_required
def api_update_department(dept_id):
    """API: Update a department structure entry."""
    from database import get_db, get_cursor, release_db
    from models import clear_structure_cache

    data = request.get_json()
    conn = get_db()
    try:
        cur = get_cursor(conn)

        # company_id is a real FK to companies table, look up the company name
        company_name = None
        company_id = data.get('company_id')
        if company_id:
            cur.execute("SELECT company FROM companies WHERE id = %s", (company_id,))
            row = cur.fetchone()
            if row:
                company_name = row['company']

        # brand_id, department_id, subdepartment_id are now TEXT values (the names themselves)
        brand_name = data.get('brand_id') or None
        dept_name = data.get('department_id') or None
        subdept_name = data.get('subdepartment_id') or None

        cur.execute("""
            UPDATE department_structure
            SET company_id = %s, company = %s, brand = %s, department = %s, subdepartment = %s, manager = %s
            WHERE id = %s
        """, (company_id, company_name, brand_name, dept_name, subdept_name, data.get('manager'), dept_id))
        conn.commit()
        clear_structure_cache()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    finally:
        release_db(conn)


@events_bp.route('/api/structure/departments/<int:dept_id>', methods=['DELETE'])
@login_required
@hr_required
def api_delete_department(dept_id):
    """API: Delete a department."""
    from database import get_db, get_cursor, release_db
    from models import clear_structure_cache

    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("DELETE FROM department_structure WHERE id = %s", (dept_id,))
        conn.commit()
        clear_structure_cache()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    finally:
        release_db(conn)


# ============== Master Tables CRUD API ==============

# --- Brands Master Table ---

@events_bp.route('/api/master/brands', methods=['GET'])
@login_required
@hr_required
def api_get_master_brands():
    """API: Get all brands from master table."""
    from database import get_db, get_cursor, release_db

    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("SELECT id, name, is_active FROM brands WHERE is_active = TRUE ORDER BY name")
        rows = cur.fetchall()
        return jsonify([{'id': r['id'], 'name': r['name'], 'is_active': r['is_active']} for r in rows])
    finally:
        release_db(conn)


@events_bp.route('/api/master/brands', methods=['POST'])
@login_required
@hr_required
def api_create_master_brand():
    """API: Create a new brand in master table."""
    from database import get_db, get_cursor, release_db
    from models import clear_structure_cache

    data = request.get_json()
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("INSERT INTO brands (name) VALUES (%s) RETURNING id", (data['name'],))
        brand_id = cur.fetchone()['id']
        conn.commit()
        clear_structure_cache()
        return jsonify({'success': True, 'id': brand_id})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    finally:
        release_db(conn)


@events_bp.route('/api/master/brands/<int:brand_id>', methods=['PUT'])
@login_required
@hr_required
def api_update_master_brand(brand_id):
    """API: Update a brand in master table."""
    from database import get_db, get_cursor, release_db
    from models import clear_structure_cache

    data = request.get_json()
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("UPDATE brands SET name = %s, is_active = %s WHERE id = %s",
                    (data['name'], data.get('is_active', True), brand_id))
        conn.commit()
        clear_structure_cache()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    finally:
        release_db(conn)


@events_bp.route('/api/master/brands/<int:brand_id>', methods=['DELETE'])
@login_required
@hr_required
def api_delete_master_brand(brand_id):
    """API: Delete a brand from master table (soft delete)."""
    from database import get_db, get_cursor, release_db
    from models import clear_structure_cache

    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("UPDATE brands SET is_active = FALSE WHERE id = %s", (brand_id,))
        conn.commit()
        clear_structure_cache()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    finally:
        release_db(conn)


# --- Departments Master Table ---

@events_bp.route('/api/master/departments', methods=['GET'])
@login_required
@hr_required
def api_get_master_departments():
    """API: Get all departments from master table."""
    from database import get_db, get_cursor, release_db

    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("SELECT id, name, is_active FROM departments WHERE is_active = TRUE ORDER BY name")
        rows = cur.fetchall()
        return jsonify([{'id': r['id'], 'name': r['name'], 'is_active': r['is_active']} for r in rows])
    finally:
        release_db(conn)


@events_bp.route('/api/master/departments', methods=['POST'])
@login_required
@hr_required
def api_create_master_department():
    """API: Create a new department in master table."""
    from database import get_db, get_cursor, release_db
    from models import clear_structure_cache

    data = request.get_json()
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("INSERT INTO departments (name) VALUES (%s) RETURNING id", (data['name'],))
        dept_id = cur.fetchone()['id']
        conn.commit()
        clear_structure_cache()
        return jsonify({'success': True, 'id': dept_id})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    finally:
        release_db(conn)


@events_bp.route('/api/master/departments/<int:dept_id>', methods=['PUT'])
@login_required
@hr_required
def api_update_master_department(dept_id):
    """API: Update a department in master table."""
    from database import get_db, get_cursor, release_db
    from models import clear_structure_cache

    data = request.get_json()
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("UPDATE departments SET name = %s, is_active = %s WHERE id = %s",
                    (data['name'], data.get('is_active', True), dept_id))
        conn.commit()
        clear_structure_cache()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    finally:
        release_db(conn)


@events_bp.route('/api/master/departments/<int:dept_id>', methods=['DELETE'])
@login_required
@hr_required
def api_delete_master_department(dept_id):
    """API: Delete a department from master table (soft delete)."""
    from database import get_db, get_cursor, release_db
    from models import clear_structure_cache

    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("UPDATE departments SET is_active = FALSE WHERE id = %s", (dept_id,))
        conn.commit()
        clear_structure_cache()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    finally:
        release_db(conn)


# --- Subdepartments Master Table ---

@events_bp.route('/api/master/subdepartments', methods=['GET'])
@login_required
@hr_required
def api_get_master_subdepartments():
    """API: Get all subdepartments from master table."""
    from database import get_db, get_cursor, release_db

    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("SELECT id, name, is_active FROM subdepartments WHERE is_active = TRUE ORDER BY name")
        rows = cur.fetchall()
        return jsonify([{'id': r['id'], 'name': r['name'], 'is_active': r['is_active']} for r in rows])
    finally:
        release_db(conn)


@events_bp.route('/api/master/subdepartments', methods=['POST'])
@login_required
@hr_required
def api_create_master_subdepartment():
    """API: Create a new subdepartment in master table."""
    from database import get_db, get_cursor, release_db
    from models import clear_structure_cache

    data = request.get_json()
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("INSERT INTO subdepartments (name) VALUES (%s) RETURNING id", (data['name'],))
        subdept_id = cur.fetchone()['id']
        conn.commit()
        clear_structure_cache()
        return jsonify({'success': True, 'id': subdept_id})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    finally:
        release_db(conn)


@events_bp.route('/api/master/subdepartments/<int:subdept_id>', methods=['PUT'])
@login_required
@hr_required
def api_update_master_subdepartment(subdept_id):
    """API: Update a subdepartment in master table."""
    from database import get_db, get_cursor, release_db
    from models import clear_structure_cache

    data = request.get_json()
    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("UPDATE subdepartments SET name = %s, is_active = %s WHERE id = %s",
                    (data['name'], data.get('is_active', True), subdept_id))
        conn.commit()
        clear_structure_cache()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    finally:
        release_db(conn)


@events_bp.route('/api/master/subdepartments/<int:subdept_id>', methods=['DELETE'])
@login_required
@hr_required
def api_delete_master_subdepartment(subdept_id):
    """API: Delete a subdepartment from master table (soft delete)."""
    from database import get_db, get_cursor, release_db
    from models import clear_structure_cache

    conn = get_db()
    try:
        cur = get_cursor(conn)
        cur.execute("UPDATE subdepartments SET is_active = FALSE WHERE id = %s", (subdept_id,))
        conn.commit()
        clear_structure_cache()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    finally:
        release_db(conn)


# ============== Bonus Types API Routes ==============

@events_bp.route('/api/bonus-types', methods=['GET'])
@login_required
@hr_required
def api_get_bonus_types():
    """API: Get all bonus types."""
    active_only = request.args.get('active_only', 'true').lower() == 'true'
    bonus_types = get_all_bonus_types(active_only=active_only)
    return jsonify(bonus_types)


@events_bp.route('/api/bonus-types', methods=['POST'])
@login_required
@hr_required
def api_create_bonus_type():
    """API: Create a new bonus type."""
    data = request.get_json()

    bonus_type_id = save_bonus_type(
        name=data['name'],
        amount=data['amount'],
        days_per_amount=data.get('days_per_amount', 1),
        description=data.get('description')
    )

    return jsonify({'success': True, 'id': bonus_type_id})


@events_bp.route('/api/bonus-types/<int:bonus_type_id>', methods=['GET'])
@login_required
@hr_required
def api_get_bonus_type(bonus_type_id):
    """API: Get a single bonus type."""
    bonus_type = get_bonus_type(bonus_type_id)
    if not bonus_type:
        return jsonify({'error': 'Bonus type not found'}), 404
    return jsonify(bonus_type)


@events_bp.route('/api/bonus-types/<int:bonus_type_id>', methods=['PUT'])
@login_required
@hr_required
def api_update_bonus_type(bonus_type_id):
    """API: Update a bonus type."""
    data = request.get_json()

    update_bonus_type(
        bonus_type_id=bonus_type_id,
        name=data['name'],
        amount=data['amount'],
        days_per_amount=data.get('days_per_amount', 1),
        description=data.get('description'),
        is_active=data.get('is_active', True)
    )

    return jsonify({'success': True})


@events_bp.route('/api/bonus-types/<int:bonus_type_id>', methods=['DELETE'])
@login_required
@hr_required
def api_delete_bonus_type(bonus_type_id):
    """API: Soft delete a bonus type."""
    delete_bonus_type(bonus_type_id)
    return jsonify({'success': True})


# ============== Export Routes ==============

@events_bp.route('/api/export', methods=['GET'])
@login_required
@hr_required
def api_export_bonuses():
    """API: Export event bonuses to Excel."""
    from flask import Response
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)

    bonuses = get_all_event_bonuses(year=year, month=month)

    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Events"

    # Headers
    headers = ['An', 'Luna', 'Nume', 'Dep', 'Brand', 'Compania', 'Eveniment',
               'Start event', 'End event', 'Data Start Participare', 'Data End Participare',
               'Zile Bonusabile', 'Ore / Libere', 'Prima (Net)', 'Detalii']

    header_fill = PatternFill(start_color='9C27B0', end_color='9C27B0', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF')

    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    # Data rows
    for row_idx, bonus in enumerate(bonuses, 2):
        ws.cell(row=row_idx, column=1, value=bonus['year'])
        ws.cell(row=row_idx, column=2, value=MONTH_NAMES.get(bonus['month'], bonus['month']))
        ws.cell(row=row_idx, column=3, value=bonus['employee_name'])
        ws.cell(row=row_idx, column=4, value=bonus.get('department', ''))
        ws.cell(row=row_idx, column=5, value=bonus.get('brand', ''))
        ws.cell(row=row_idx, column=6, value=bonus.get('company', ''))
        ws.cell(row=row_idx, column=7, value=bonus['event_name'])
        ws.cell(row=row_idx, column=8, value=bonus.get('event_start', ''))
        ws.cell(row=row_idx, column=9, value=bonus.get('event_end', ''))
        ws.cell(row=row_idx, column=10, value=bonus.get('participation_start', ''))
        ws.cell(row=row_idx, column=11, value=bonus.get('participation_end', ''))
        ws.cell(row=row_idx, column=12, value=bonus.get('bonus_days'))
        ws.cell(row=row_idx, column=13, value=bonus.get('hours_free'))
        ws.cell(row=row_idx, column=14, value=bonus.get('bonus_net'))
        ws.cell(row=row_idx, column=15, value=bonus.get('details', ''))

    # Auto-width columns
    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column].width = adjusted_width

    # Save to buffer
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    # Generate filename
    filename = f"Events"
    if year:
        filename += f"_{year}"
    if month:
        filename += f"_{MONTH_NAMES.get(month, month)}"
    filename += ".xlsx"

    return Response(
        buffer.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )
