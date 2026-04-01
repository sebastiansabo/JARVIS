"""Field Sales schema: client_profiles, client_fleet, kam_visit_plans, kam_visit_notes."""


def create_schema_field_sales(conn, cursor):
    """Create Field Sales / KAM module tables."""

    # 1. Client profile enrichment (extends crm_clients 1:1)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS client_profiles (
            id SERIAL PRIMARY KEY,
            client_id INTEGER NOT NULL REFERENCES crm_clients(id) ON DELETE CASCADE,
            client_type VARCHAR(20) DEFAULT 'private',
            industry VARCHAR(100),
            country_code VARCHAR(5) DEFAULT 'RO',
            legal_form VARCHAR(30),
            country_detected_from VARCHAR(30),
            assigned_kam_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            fleet_size INTEGER DEFAULT 0,
            renewal_score INTEGER DEFAULT 0,
            last_scored_at TIMESTAMP,
            cui VARCHAR(20),
            anaf_data JSONB,
            anaf_fetched_at TIMESTAMP,
            estimated_annual_value NUMERIC(12,2),
            priority VARCHAR(10) DEFAULT 'medium',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(client_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_client_profiles_kam ON client_profiles(assigned_kam_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_client_profiles_type ON client_profiles(client_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_client_profiles_country ON client_profiles(country_code)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_client_profiles_priority ON client_profiles(priority)')

    # Clienti import extensions: revenue breakdown + service history
    cursor.execute("ALTER TABLE client_profiles ADD COLUMN IF NOT EXISTS revenue_nw NUMERIC(12,2)")
    cursor.execute("ALTER TABLE client_profiles ADD COLUMN IF NOT EXISTS revenue_gw NUMERIC(12,2)")
    cursor.execute("ALTER TABLE client_profiles ADD COLUMN IF NOT EXISTS last_service_date DATE")
    cursor.execute("ALTER TABLE client_profiles ADD COLUMN IF NOT EXISTS last_service_advisor TEXT")
    cursor.execute("ALTER TABLE client_profiles ADD COLUMN IF NOT EXISTS last_advisor_date DATE")

    # 2. Client fleet registry
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS client_fleet (
            id SERIAL PRIMARY KEY,
            client_id INTEGER NOT NULL REFERENCES crm_clients(id) ON DELETE CASCADE,
            vehicle_make VARCHAR(50),
            vehicle_model VARCHAR(50),
            vehicle_year INTEGER,
            vin VARCHAR(20),
            license_plate VARCHAR(20),
            sale_id INTEGER,
            purchase_date DATE,
            purchase_price NUMERIC(12,2),
            purchase_currency VARCHAR(5) DEFAULT 'EUR',
            estimated_mileage INTEGER,
            financing_type VARCHAR(30),
            financing_expiry DATE,
            warranty_expiry DATE,
            status VARCHAR(20) DEFAULT 'active',
            renewal_candidate BOOLEAN DEFAULT FALSE,
            renewal_reason TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_client_fleet_client ON client_fleet(client_id)')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_client_fleet_renewal ON client_fleet(renewal_candidate) WHERE renewal_candidate = TRUE")
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_client_fleet_status ON client_fleet(status)')

    # Clienti import extensions: batch tracking
    cursor.execute("ALTER TABLE client_fleet ADD COLUMN IF NOT EXISTS import_batch_id INTEGER REFERENCES crm_import_batches(id)")
    cursor.execute("ALTER TABLE client_fleet ADD COLUMN IF NOT EXISTS source_row_hash TEXT")

    # 3. KAM visit plans
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS kam_visit_plans (
            id SERIAL PRIMARY KEY,
            kam_id INTEGER NOT NULL REFERENCES users(id),
            client_id INTEGER NOT NULL REFERENCES crm_clients(id),
            planned_date DATE NOT NULL,
            planned_time TIME,
            visit_type VARCHAR(40) DEFAULT 'general',
            goals TEXT,
            ai_brief TEXT,
            ai_brief_generated_at TIMESTAMP,
            status VARCHAR(20) DEFAULT 'planned',
            checkin_at TIMESTAMP,
            checkout_at TIMESTAMP,
            outcome VARCHAR(30),
            checkin_lat DOUBLE PRECISION,
            checkin_lng DOUBLE PRECISION,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_kam_visits_kam_date ON kam_visit_plans(kam_id, planned_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_kam_visits_client ON kam_visit_plans(client_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_kam_visits_status ON kam_visit_plans(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_kam_visits_date ON kam_visit_plans(planned_date)')

    # 4. Visit notes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS kam_visit_notes (
            id SERIAL PRIMARY KEY,
            visit_id INTEGER NOT NULL REFERENCES kam_visit_plans(id) ON DELETE CASCADE,
            raw_note TEXT NOT NULL,
            structured_note JSONB,
            structured_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_kam_notes_visit ON kam_visit_notes(visit_id)')

    # 5. Permissions V2 seed — full matrix
    _field_sales_perms = [
        # Module-level access (used by get_module_access_map)
        ('field_sales', 'Field Sales', 'bi-geo-alt-fill', 'module', 'Module', 'access', 'Access', 'Access the field sales module', False, 1),
        # Mobile toggle (used by get_mobile_access_map)
        ('field_sales', 'Field Sales', 'bi-geo-alt-fill', 'mobile', 'Mobile', 'access', 'Mobile Access', 'Access field sales on mobile app', False, 2),
        # Granular permissions
        ('field_sales', 'Field Sales', 'bi-geo-alt-fill', 'visits', 'Visits', 'manage_own', 'Manage Own', 'Create and manage own visit plans and notes', False, 3),
        ('field_sales', 'Field Sales', 'bi-geo-alt-fill', 'team', 'Team', 'view', 'View', 'Manager: view all KAM visits and pipeline', False, 4),
        ('field_sales', 'Field Sales', 'bi-geo-alt-fill', 'fiscal', 'Fiscal Data', 'view', 'View', 'See ANAF fiscal data on client card', False, 5),
        ('field_sales', 'Field Sales', 'bi-geo-alt-fill', 'fleet', 'Fleet', 'manage', 'Manage', 'Add/edit vehicles in client fleet registry', False, 6),
    ]
    for p in _field_sales_perms:
        cursor.execute('''
            INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label,
                                        action_key, action_label, description, is_scope_based, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (module_key, entity_key, action_key) DO NOTHING
        ''', p)

    # ── Role grants ──

    # Admin: ALL field_sales permissions
    cursor.execute('''
        INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
        SELECT r.id, p.id, 'all', TRUE
        FROM roles r
        CROSS JOIN permissions_v2 p
        WHERE r.name = 'Admin' AND p.module_key = 'field_sales'
        ON CONFLICT (role_id, permission_id) DO NOTHING
    ''')

    # Manager: module access, mobile access, manage visits, view team, view fiscal, manage fleet
    cursor.execute('''
        INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
        SELECT r.id, p.id, 'all', TRUE
        FROM roles r
        CROSS JOIN permissions_v2 p
        WHERE r.name = 'Manager' AND p.module_key = 'field_sales'
          AND (p.entity_key || '.' || p.action_key) IN (
              'module.access', 'mobile.access', 'visits.manage_own',
              'team.view', 'fiscal.view', 'fleet.manage'
          )
        ON CONFLICT (role_id, permission_id) DO NOTHING
    ''')

    # User (KAM): module access, mobile access, manage own visits, view fiscal
    cursor.execute('''
        INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
        SELECT r.id, p.id, 'all', TRUE
        FROM roles r
        CROSS JOIN permissions_v2 p
        WHERE r.name = 'User' AND p.module_key = 'field_sales'
          AND (p.entity_key || '.' || p.action_key) IN (
              'module.access', 'mobile.access', 'visits.manage_own', 'fiscal.view'
          )
        ON CONFLICT (role_id, permission_id) DO NOTHING
    ''')

    conn.commit()
