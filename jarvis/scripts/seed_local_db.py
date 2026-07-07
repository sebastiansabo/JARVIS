"""Seed local database with dummy data for Playwright/manual testing.

Usage:
    DATABASE_URL='postgresql://localhost/defaultdb' python -m scripts.seed_local_db

Idempotent — uses ON CONFLICT DO NOTHING / checks before inserting.
"""
import os
import sys
import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://localhost/defaultdb')

# ── Test credentials ──
TEST_PASSWORD = 'test1234'
TEST_USERS = [
    # (name, email, role_name, company, department)
    ('Test Admin',   'admin@test.local',   'Admin',   'Test Company SRL',    'Management'),
    ('Test Manager', 'manager@test.local', 'Manager', 'Test Company SRL',    'Sales'),
    ('Test User',    'user@test.local',    'User',    'Test Company SRL',    'Marketing'),
    ('Test Viewer',  'viewer@test.local',  'Viewer',  'Test Company SRL',    'Service'),
    ('Test Manager2','manager2@test.local','Manager', 'Test Subsidiary SRL', 'After Sales'),
]

TEST_COMPANIES = [
    # (name, vat, reg_no, iban, bank, street, city, county, postal_code)
    ('Test Company SRL',    'RO12345678', 'J01/100/2020', 'RO49AAAA1B31007593840000', 'Test Bank', 'Str. Test 1',  'Bucharest', 'Bucharest', '010101'),
    ('Test Subsidiary SRL', 'RO87654321', 'J01/200/2021', 'RO49BBBB1B31007593840000', 'Test Bank', 'Str. Test 2',  'Cluj-Napoca','Cluj',      '400001'),
]

TEST_INVOICES = [
    # (supplier, invoice_number, invoice_date, invoice_value, currency, status, payment_status)
    ('Supplier Alpha SRL', 'INV-TEST-001', '2026-01-15', 5000.00,  'RON', 'approved',  'paid'),
    ('Supplier Beta SRL',  'INV-TEST-002', '2026-02-01', 12500.50, 'RON', 'approved',  'not_paid'),
    ('Supplier Gamma SRL', 'INV-TEST-003', '2026-03-10', 3200.00,  'EUR', 'new',       'not_paid'),
    ('Supplier Delta SRL', 'INV-TEST-004', '2026-04-05', 8750.25,  'RON', 'pending',   'partial'),
    ('Supplier Epsilon SA','INV-TEST-005', '2026-05-20', 1500.00,  'RON', 'approved',  'paid'),
    ('Supplier Zeta SRL',  'INV-TEST-006', '2026-06-01', 22000.00, 'RON', 'new',       'not_paid'),
]


def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def seed_companies(cur):
    """Seed test companies."""
    for name, vat, reg_no, iban, bank, street, city, county, postal in TEST_COMPANIES:
        cur.execute("""
            INSERT INTO companies (company, vat, reg_no, iban, bank, street, city, county, postal_code)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (company) DO NOTHING
        """, (name, vat, reg_no, iban, bank, street, city, county, postal))
    print(f"  [ok] {len(TEST_COMPANIES)} companies seeded")


def seed_users(cur):
    """Seed test users with known passwords."""
    pw_hash = generate_password_hash(TEST_PASSWORD)

    for name, email, role_name, company, department in TEST_USERS:
        # Get role_id
        cur.execute("SELECT id FROM roles WHERE name = %s", (role_name,))
        role_row = cur.fetchone()
        if not role_row:
            print(f"  [skip] role '{role_name}' not found — run app once to seed roles")
            continue
        role_id = role_row['id']

        cur.execute("""
            INSERT INTO users (name, email, password_hash, role_id, company, department, is_active, contract_status)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE, 'active')
            ON CONFLICT (email) DO UPDATE SET
                password_hash = EXCLUDED.password_hash,
                role_id = EXCLUDED.role_id,
                is_active = TRUE,
                contract_status = 'active'
        """, (name, email, pw_hash, role_id, company, department))
    print(f"  [ok] {len(TEST_USERS)} test users seeded (password: {TEST_PASSWORD})")


def seed_department_structure(cur):
    """Seed org structure."""
    departments = [
        ('Test Company SRL', 'TestBrand', 'Management',  None),
        ('Test Company SRL', 'TestBrand', 'Sales',       None),
        ('Test Company SRL', 'TestBrand', 'Marketing',   None),
        ('Test Company SRL', 'TestBrand', 'Service',     None),
        ('Test Company SRL', 'TestBrand', 'After Sales', None),
    ]
    for company, brand, dept, subdept in departments:
        cur.execute("""
            INSERT INTO department_structure (company, brand, department, subdepartment)
            SELECT %s, %s, %s, %s
            WHERE NOT EXISTS (
                SELECT 1 FROM department_structure
                WHERE company = %s AND department = %s
            )
        """, (company, brand, dept, subdept, company, dept))
    print(f"  [ok] {len(departments)} department_structure rows seeded")


def seed_structure_nodes(cur):
    """Seed organigram tree."""
    # Get company id
    cur.execute("SELECT id FROM companies WHERE company = 'Test Company SRL'")
    row = cur.fetchone()
    if not row:
        print("  [skip] structure_nodes — company not found")
        return
    company_id = row['id']

    # Check if already seeded
    cur.execute("SELECT COUNT(*) as cnt FROM structure_nodes WHERE company_id = %s", (company_id,))
    if cur.fetchone()['cnt'] > 0:
        print("  [skip] structure_nodes already seeded")
        return

    # L1 node
    cur.execute("""
        INSERT INTO structure_nodes (company_id, parent_id, name, level, has_team, display_order)
        VALUES (%s, NULL, 'Headquarters', 1, FALSE, 1) RETURNING id
    """, (company_id,))
    l1_id = cur.fetchone()['id']

    # L2 nodes
    l2_depts = ['Sales Division', 'Operations Division', 'Support Division']
    l2_ids = []
    for i, name in enumerate(l2_depts):
        cur.execute("""
            INSERT INTO structure_nodes (company_id, parent_id, name, level, has_team, display_order)
            VALUES (%s, %s, %s, 2, TRUE, %s) RETURNING id
        """, (company_id, l1_id, name, i + 1))
        l2_ids.append(cur.fetchone()['id'])

    # Assign test users to nodes
    cur.execute("SELECT id FROM users WHERE email = 'admin@test.local'")
    admin = cur.fetchone()
    if admin:
        cur.execute("""
            INSERT INTO structure_node_members (node_id, user_id, role)
            VALUES (%s, %s, 'responsable')
            ON CONFLICT (node_id, user_id) DO NOTHING
        """, (l1_id, admin['id']))

    cur.execute("SELECT id FROM users WHERE email = 'manager@test.local'")
    mgr = cur.fetchone()
    if mgr and l2_ids:
        cur.execute("""
            INSERT INTO structure_node_members (node_id, user_id, role)
            VALUES (%s, %s, 'responsable')
            ON CONFLICT (node_id, user_id) DO NOTHING
        """, (l2_ids[0], mgr['id']))

    cur.execute("SELECT id FROM users WHERE email = 'user@test.local'")
    usr = cur.fetchone()
    if usr and l2_ids:
        cur.execute("""
            INSERT INTO structure_node_members (node_id, user_id, role)
            VALUES (%s, %s, 'team')
            ON CONFLICT (node_id, user_id) DO NOTHING
        """, (l2_ids[0], usr['id']))

    print(f"  [ok] {1 + len(l2_depts)} structure_nodes + members seeded")


def seed_invoices(cur):
    """Seed test invoices with allocations."""
    for supplier, inv_num, inv_date, value, currency, status, pay_status in TEST_INVOICES:
        cur.execute("SELECT id FROM invoices WHERE invoice_number = %s", (inv_num,))
        if cur.fetchone():
            continue

        value_ron = value if currency == 'RON' else value * 4.97
        value_eur = value if currency == 'EUR' else value / 4.97

        cur.execute("""
            INSERT INTO invoices (supplier, invoice_number, invoice_date, invoice_value,
                                  currency, value_ron, value_eur, status, payment_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        """, (supplier, inv_num, inv_date, value, currency,
              round(value_ron, 2), round(value_eur, 2), status, pay_status))
        inv_id = cur.fetchone()['id']

        # Add allocation
        cur.execute("""
            INSERT INTO allocations (invoice_id, company, department, allocation_percent, allocation_value)
            VALUES (%s, 'Test Company SRL', 'Management', 100.0, %s)
        """, (inv_id, value))

    print(f"  [ok] {len(TEST_INVOICES)} invoices + allocations seeded")


def seed_hr_events(cur):
    """Seed HR events and bonus types."""
    # Bonus types
    bonus_types = [
        ('Performance Bonus', 500.00, 1),
        ('Attendance Bonus',  200.00, 1),
        ('Referral Bonus',    1000.00, 0),
    ]
    for name, amount, days in bonus_types:
        cur.execute("""
            INSERT INTO "hr"."bonus_types" (name, amount, days_per_amount)
            SELECT %s, %s, %s
            WHERE NOT EXISTS (SELECT 1 FROM "hr"."bonus_types" WHERE name = %s)
        """, (name, amount, days, name))

    # Get admin user for created_by
    cur.execute("SELECT id FROM users WHERE email = 'admin@test.local'")
    admin = cur.fetchone()
    if not admin:
        print("  [skip] HR events — admin user not found")
        return

    # Events
    events = [
        ('Team Building Q1 2026', '2026-03-15', '2026-03-16', 'Test Company SRL'),
        ('Training Workshop',     '2026-04-01', '2026-04-03', 'Test Company SRL'),
        ('Company Anniversary',   '2026-06-01', '2026-06-01', 'Test Company SRL'),
    ]
    for name, start, end, company in events:
        cur.execute("""
            INSERT INTO "hr"."events" (name, start_date, end_date, company, created_by)
            SELECT %s, %s, %s, %s, %s
            WHERE NOT EXISTS (SELECT 1 FROM "hr"."events" WHERE name = %s AND company = %s)
        """, (name, start, end, company, admin['id'], name, company))

    print(f"  [ok] {len(bonus_types)} bonus types + {len(events)} HR events seeded")


def seed_tags(cur):
    """Seed tag groups and tags."""
    # Check if test tags exist
    cur.execute("SELECT id FROM tag_groups WHERE name = 'Test Priority'")
    if cur.fetchone():
        print("  [skip] tags already seeded")
        return

    cur.execute("""
        INSERT INTO tag_groups (name, color, sort_order)
        VALUES ('Test Priority', '#e74c3c', 1) RETURNING id
    """)
    group_id = cur.fetchone()['id']

    cur.execute("SELECT id FROM users WHERE email = 'admin@test.local'")
    admin = cur.fetchone()
    admin_id = admin['id'] if admin else None

    for tag_name in ['Urgent', 'Normal', 'Low Priority']:
        cur.execute("""
            INSERT INTO tags (name, group_id, is_global, created_by)
            VALUES (%s, %s, TRUE, %s)
        """, (tag_name, group_id, admin_id))

    print("  [ok] 1 tag group + 3 tags seeded")


def seed_invoice_templates(cur):
    """Seed a couple of invoice templates."""
    templates = [
        ('Test Template - Standard', 'fixed', 'Supplier Alpha SRL', 'RO11111111', 'RON'),
        ('Test Template - Regex',    'regex', 'Supplier Beta SRL',  'RO22222222', 'RON'),
    ]
    for name, ttype, supplier, vat, currency in templates:
        cur.execute("""
            INSERT INTO invoice_templates (name, template_type, supplier, supplier_vat, currency)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (name) DO NOTHING
        """, (name, ttype, supplier, vat, currency))
    print(f"  [ok] {len(templates)} invoice templates seeded")


def seed_crm(cur):
    """Seed CRM clients and deals."""
    clients = [
        ('Ion Popescu',    'ion@example.com',    '0721000001', 'Test Company SRL'),
        ('Maria Ionescu',  'maria@example.com',  '0721000002', 'Test Subsidiary SRL'),
        ('Andrei Vasile',  'andrei@example.com', '0721000003', 'Test Company SRL'),
    ]
    for display_name, email, phone, company_name in clients:
        name_normalized = display_name.lower().strip()
        cur.execute("""
            INSERT INTO crm_clients (display_name, name_normalized, client_type, email, phone, company_name)
            SELECT %s, %s, 'person', %s, %s, %s
            WHERE NOT EXISTS (SELECT 1 FROM crm_clients WHERE email = %s)
        """, (display_name, name_normalized, email, phone, company_name, email))

    # Deals
    cur.execute("SELECT id FROM crm_clients WHERE email = 'ion@example.com'")
    client = cur.fetchone()
    if client:
        cur.execute("""
            INSERT INTO crm_deals (client_id, source, dealer_name, brand, model_name, contract_date)
            SELECT %s, 'VW', 'Test Dealer', 'Volkswagen', 'Golf 8', '2026-06-01'
            WHERE NOT EXISTS (SELECT 1 FROM crm_deals WHERE client_id = %s AND source = 'VW')
        """, (client['id'], client['id']))

    print(f"  [ok] {len(clients)} CRM clients + deals seeded")


def main():
    print(f"\n=== Seeding local DB: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL} ===\n")

    conn = get_conn()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        seed_companies(cur)
        seed_users(cur)
        seed_department_structure(cur)
        seed_structure_nodes(cur)
        seed_invoices(cur)
        seed_hr_events(cur)
        seed_tags(cur)
        seed_invoice_templates(cur)
        seed_crm(cur)
        conn.commit()
        print("\n=== Seed complete ===\n")
        print("Test accounts:")
        print("  admin@test.local   / test1234  (Admin)")
        print("  manager@test.local / test1234  (Manager)")
        print("  user@test.local    / test1234  (User)")
        print("  viewer@test.local  / test1234  (Viewer)")
        print()
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Seed failed: {e}")
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    main()
