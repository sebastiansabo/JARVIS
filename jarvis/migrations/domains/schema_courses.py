"""HR Courses schema: hr.course_types, hr.courses, hr.course_enrollments, hr.course_certifications, hr.course_invoices."""


def create_schema_courses(conn, cursor):
    """Create HR Courses module tables, indexes, and seed data."""

    # ============== HR Courses Module Schema ==============
    # Ensure hr schema exists (idempotent)
    cursor.execute('CREATE SCHEMA IF NOT EXISTS hr')
    conn.commit()

    # Course Types - classification of courses (SSM, PSI, ISCIR, etc.)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hr.course_types (
            id SERIAL PRIMARY KEY,
            code VARCHAR(20) UNIQUE NOT NULL,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            requires_certification BOOLEAN DEFAULT TRUE,
            default_validity_months INTEGER,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Courses - individual course instances
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hr.courses (
            id SERIAL PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            course_type_id INTEGER REFERENCES hr.course_types(id),
            company_id INTEGER REFERENCES companies(id),
            supplier_id INTEGER REFERENCES suppliers(id) ON DELETE SET NULL,
            trainer_name VARCHAR(200),
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            location VARCHAR(200),
            description TEXT,
            budget NUMERIC(12,2),
            currency VARCHAR(3) DEFAULT 'RON',
            status VARCHAR(20) DEFAULT 'draft',
            approval_request_id INTEGER,
            created_by INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP
        )
    ''')

    # Course Enrollments - employees enrolled in courses
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hr.course_enrollments (
            id SERIAL PRIMARY KEY,
            course_id INTEGER NOT NULL REFERENCES hr.courses(id) ON DELETE CASCADE,
            employee_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
            enrollment_status VARCHAR(20) DEFAULT 'enrolled',
            enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            notes TEXT,
            UNIQUE(course_id, employee_id)
        )
    ''')

    # Course Certifications - certificates issued after course completion
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hr.course_certifications (
            id SERIAL PRIMARY KEY,
            enrollment_id INTEGER REFERENCES hr.course_enrollments(id) ON DELETE SET NULL,
            employee_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
            course_type_id INTEGER NOT NULL REFERENCES hr.course_types(id),
            certificate_number VARCHAR(100),
            issued_date DATE NOT NULL,
            expiry_date DATE,
            status VARCHAR(20) DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Course Invoices - link table between courses and invoices
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hr.course_invoices (
            course_id INTEGER NOT NULL REFERENCES hr.courses(id) ON DELETE CASCADE,
            invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
            PRIMARY KEY (course_id, invoice_id)
        )
    ''')

    # Enrollment Costs - per-employee cost breakdown (mirrors legacy Excel)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hr.enrollment_costs (
            id SERIAL PRIMARY KEY,
            enrollment_id INTEGER NOT NULL REFERENCES hr.course_enrollments(id) ON DELETE CASCADE,
            training_fee NUMERIC(12,2) DEFAULT 0,
            per_diem NUMERIC(12,2) DEFAULT 0,
            accommodation NUMERIC(12,2) DEFAULT 0,
            transport NUMERIC(12,2) DEFAULT 0,
            taxi NUMERIC(12,2) DEFAULT 0,
            total_cost NUMERIC(12,2) GENERATED ALWAYS AS (
                training_fee + per_diem + accommodation + transport + taxi
            ) STORED,
            currency VARCHAR(3) DEFAULT 'RON',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(enrollment_id)
        )
    ''')

    # Course Activity - audit trail for course changes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hr.course_activity (
            id SERIAL PRIMARY KEY,
            course_id INTEGER NOT NULL REFERENCES hr.courses(id) ON DELETE CASCADE,
            action VARCHAR(50) NOT NULL,
            actor_id INTEGER REFERENCES public.users(id),
            actor_name VARCHAR(200),
            details JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Add new columns to existing tables (idempotent)
    for stmt in [
        "ALTER TABLE hr.courses ADD COLUMN IF NOT EXISTS duration_hours NUMERIC(6,1)",
        "ALTER TABLE hr.courses ADD COLUMN IF NOT EXISTS travel_mode VARCHAR(50)",
        "ALTER TABLE hr.courses ADD COLUMN IF NOT EXISTS course_code VARCHAR(50)",
        "ALTER TABLE hr.course_enrollments ADD COLUMN IF NOT EXISTS order_number VARCHAR(50)",
        "ALTER TABLE hr.course_enrollments ADD COLUMN IF NOT EXISTS travel_order VARCHAR(50)",
        "ALTER TABLE hr.course_enrollments ADD COLUMN IF NOT EXISTS additional_act VARCHAR(100)",
        "ALTER TABLE hr.course_enrollments ADD COLUMN IF NOT EXISTS department VARCHAR(100)",
        "ALTER TABLE hr.course_enrollments ADD COLUMN IF NOT EXISTS travel_mode VARCHAR(50)",
    ]:
        cursor.execute(stmt)
    conn.commit()

    # ============== Indexes ==============
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_courses_company ON hr.courses(company_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_courses_type ON hr.courses(course_type_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_courses_status ON hr.courses(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_courses_dates ON hr.courses(start_date, end_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_courses_deleted ON hr.courses(deleted_at) WHERE deleted_at IS NOT NULL')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_courses_year ON hr.courses(EXTRACT(YEAR FROM start_date))')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_enrollments_course ON hr.course_enrollments(course_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_enrollments_employee ON hr.course_enrollments(employee_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_certs_employee ON hr.course_certifications(employee_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_certs_enrollment ON hr.course_certifications(enrollment_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_certs_expiry ON hr.course_certifications(expiry_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_certs_status ON hr.course_certifications(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_enrollment_costs_enrollment ON hr.enrollment_costs(enrollment_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_course_activity_course ON hr.course_activity(course_id)')
    conn.commit()

    # ============== Seed Course Types ==============
    seed_types = [
        ('SSM_GEN', 'SSM General', 'Securitate și Sănătate în Muncă - Instruire generală', True, 12),
        ('SSM_PER', 'SSM Periodic', 'Securitate și Sănătate în Muncă - Instruire periodică', True, 6),
        ('PSI', 'PSI', 'Prevenirea și Stingerea Incendiilor', True, 12),
        ('ISCIR', 'ISCIR', 'Autorizare ISCIR - echipamente sub presiune/ridicat', True, 24),
        ('OEM', 'OEM Training', 'Training tehnic OEM / producător', True, 12),
        ('PROF_DEV', 'Professional Development', 'Dezvoltare profesională', False, None),
        ('ONBOARD', 'Onboarding', 'Program de integrare angajați noi', False, None),
        ('SALES', 'Sales Training', 'Training vânzări', False, None),
        ('MGMT', 'Management', 'Training management și leadership', False, None),
        ('FIRST_AID', 'Prim Ajutor', 'Curs de prim ajutor', True, 24),
        ('GDPR', 'GDPR', 'Protecția datelor cu caracter personal', True, 12),
        ('QUALITY', 'Quality', 'Managementul calității', True, 12),
    ]

    for code, name, desc, req_cert, validity in seed_types:
        cursor.execute('''
            INSERT INTO hr.course_types (code, name, description, requires_certification, default_validity_months)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (code) DO NOTHING
        ''', (code, name, desc, req_cert, validity))
    conn.commit()

    # ============== Seed Permissions ==============
    _courses_perms = [
        ('hr', 'HR', 'bi-people', 'courses', 'Courses', 'view', 'View', 'View HR courses', False, 20),
        ('hr', 'HR', 'bi-people', 'courses', 'Courses', 'add', 'Add', 'Add HR courses', False, 21),
        ('hr', 'HR', 'bi-people', 'courses', 'Courses', 'edit', 'Edit', 'Edit HR courses', False, 22),
        ('hr', 'HR', 'bi-people', 'courses', 'Courses', 'delete', 'Delete', 'Delete HR courses', False, 23),
    ]

    for p in _courses_perms:
        cursor.execute('''
            INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label,
                                        action_key, action_label, description, is_scope_based, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (module_key, entity_key, action_key) DO NOTHING
        ''', p)
    conn.commit()
