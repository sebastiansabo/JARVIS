"""Voucher module schema."""
import logging

logger = logging.getLogger(__name__)


def create_schema_vouchers(conn, cursor):
    """Create vouchers table and indexes."""

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vouchers (
            id SERIAL PRIMARY KEY,
            company_id INT NOT NULL REFERENCES companies(id),
            voucher_code VARCHAR(20) NOT NULL UNIQUE,
            client_name VARCHAR(255) NOT NULL,
            contract_number VARCHAR(100) NOT NULL,
            car_vin VARCHAR(17) NOT NULL,
            validity_months INT NOT NULL,
            expires_at DATE,
            issued_at DATE,
            issued_by_user_id INT NOT NULL REFERENCES users(id),
            voucher_type VARCHAR(30) NOT NULL,
            value_lei NUMERIC(12,2),
            discount_code VARCHAR(100),
            discount_percentage NUMERIC(5,2),
            service_items JSONB,
            status VARCHAR(20) NOT NULL DEFAULT 'pending_approval',
            approval_request_id INT,
            approver_user_id INT REFERENCES users(id),
            redeemed_at TIMESTAMP,
            redeemed_by_user_id INT REFERENCES users(id),
            redemption_notes TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'chk_voucher_status'
            ) THEN
                ALTER TABLE vouchers ADD CONSTRAINT chk_voucher_status
                CHECK (status IN ('draft', 'pending_approval', 'approved', 'active', 'rejected', 'redeemed', 'expired', 'archived'));
            END IF;
        END $$;
    ''')

    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'chk_voucher_type'
            ) THEN
                ALTER TABLE vouchers ADD CONSTRAINT chk_voucher_type
                CHECK (voucher_type IN ('value', 'accessory_discount_code', 'accessory_percentage', 'service_items'));
            END IF;
        END $$;
    ''')

    cursor.execute('''
        DO $$
        BEGIN
            -- Self-healing: recreate only when missing or not yet widened to 36/48.
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'chk_validity_months'
                  AND pg_get_constraintdef(oid) LIKE '%36%'
            ) THEN
                ALTER TABLE vouchers DROP CONSTRAINT IF EXISTS chk_validity_months;
                ALTER TABLE vouchers ADD CONSTRAINT chk_validity_months
                CHECK (validity_months IN (1, 3, 6, 12, 24, 36, 48));
            END IF;
        END $$;
    ''')

    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'chk_car_vin_length'
            ) THEN
                ALTER TABLE vouchers ADD CONSTRAINT chk_car_vin_length
                CHECK (char_length(car_vin) = 17);
            END IF;
        END $$;
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vouchers_company_id ON vouchers(company_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vouchers_status ON vouchers(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vouchers_issued_by ON vouchers(issued_by_user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vouchers_expires_at ON vouchers(expires_at)')
    # Indexes for the common filters/sorts: type filter, the default list sort
    # (created_at DESC), the approver lookup in get_by_user, and redeemed_at
    # (archive job + monthly summaries).
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vouchers_voucher_type ON vouchers(voucher_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vouchers_created_at ON vouchers(created_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vouchers_approver ON vouchers(approver_user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vouchers_redeemed_at ON vouchers(redeemed_at)')

    # Link voucher to the form submission that created it
    cursor.execute('''
        DO $$ BEGIN
            ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS form_submission_id INT REFERENCES form_submissions(id);
        EXCEPTION WHEN others THEN NULL;
        END $$;
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vouchers_form_submission ON vouchers(form_submission_id) WHERE form_submission_id IS NOT NULL')

    # Soft-delete support: superadmin deletes set deleted_at instead of removing the row
    cursor.execute('''
        DO $$ BEGIN
            ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;
        EXCEPTION WHEN others THEN NULL;
        END $$;
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vouchers_deleted_at ON vouchers(deleted_at) WHERE deleted_at IS NULL')

    # Full persistence (design doc §6.B1): activation anchor + client identifiers.
    # start_date/client_cif are new; client_email is a safety net for fresh DBs
    # (already added out-of-band on staging/local — see design doc §5.1).
    cursor.execute('''
        DO $$ BEGIN
            ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS start_date DATE;
        EXCEPTION WHEN others THEN NULL;
        END $$;
    ''')
    cursor.execute('''
        DO $$ BEGIN
            ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS client_cif VARCHAR(20);
        EXCEPTION WHEN others THEN NULL;
        END $$;
    ''')
    cursor.execute('''
        DO $$ BEGIN
            ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS client_email VARCHAR(255);
        EXCEPTION WHEN others THEN NULL;
        END $$;
    ''')

    # redeemer_signature: captured by the public (QR) redeem flow. Was added
    # out-of-band on staging/local; declare it here so a fresh DB has it and
    # public redeem doesn't 500 with "column does not exist".
    cursor.execute('''
        DO $$ BEGIN
            ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS redeemer_signature TEXT;
        EXCEPTION WHEN others THEN NULL;
        END $$;
    ''')

    # Add 'archived' to voucher status constraint
    cursor.execute('''
        DO $$ BEGIN
            ALTER TABLE vouchers DROP CONSTRAINT IF EXISTS chk_voucher_status;
            ALTER TABLE vouchers ADD CONSTRAINT chk_voucher_status
                CHECK (status IN ('draft', 'pending_approval', 'approved', 'active', 'rejected', 'redeemed', 'expired', 'archived'));
        END $$;
    ''')

    # Ensure approval flow steps use context_approver (not specific_user)
    cursor.execute('''
        UPDATE approval_steps SET approver_type = 'context_approver'
        WHERE approver_type = 'specific_user' AND approver_user_id IS NULL
          AND flow_id IN (SELECT id FROM approval_flows WHERE entity_type IN ('voucher', 'form_submission'))
    ''')

    # Seed the voucher-approval flow idempotently (previously DB-only / admin-UI
    # created — a fresh DB had neither, so ApprovalEngine.submit('voucher', ...)
    # would raise NoMatchingFlowError). WHERE NOT EXISTS makes this a no-op
    # where the flow already exists (staging/prod).
    cursor.execute('''
        INSERT INTO approval_flows (name, slug, entity_type, is_active, priority, created_by)
        SELECT 'Voucher Approval', 'voucher-approval', 'voucher', TRUE, 1, 1
        WHERE NOT EXISTS (SELECT 1 FROM approval_flows WHERE slug = 'voucher-approval')
    ''')
    cursor.execute('''
        INSERT INTO approval_steps (flow_id, name, step_order, approver_type, notify_on_pending, notify_on_decision)
        SELECT f.id, 'Manager Approval', 1, 'context_approver', TRUE, TRUE
        FROM approval_flows f
        WHERE f.slug = 'voucher-approval'
          AND NOT EXISTS (SELECT 1 FROM approval_steps s WHERE s.flow_id = f.id)
    ''')

    # ── Service Catalog ─────────────────────────────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS voucher_service_catalog (
            id SERIAL PRIMARY KEY,
            company_id INT NOT NULL REFERENCES companies(id),
            service_code VARCHAR(50),
            name VARCHAR(255) NOT NULL,
            price NUMERIC(12,2) NOT NULL,
            currency VARCHAR(10) DEFAULT 'LEI',
            category VARCHAR(100),
            is_active BOOLEAN DEFAULT TRUE,
            sort_order INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vsc_company_active ON voucher_service_catalog(company_id, is_active)')

    # Seed default services for company 16 (AUTOWORLD S.R.L.) — legacy table
    cursor.execute('SELECT COUNT(*) AS cnt FROM voucher_service_catalog WHERE company_id = 16')
    if cursor.fetchone()['cnt'] == 0:
        seed_services = [
            ('SVC-OIL', 'Oil change', 900),
            ('SVC-TIRE', 'Tire rotation', 200),
            ('SVC-BRK', 'Brake inspection', 350),
            ('SVC-AIR', 'Air filter replacement', 150),
            ('SVC-COOL', 'Coolant flush', 400),
            ('SVC-BAT', 'Battery check', 100),
            ('SVC-WHL', 'Wheel alignment', 300),
            ('SVC-CLN', 'Interior cleaning', 250),
        ]
        for idx, (code, name, price) in enumerate(seed_services):
            cursor.execute('''
                INSERT INTO voucher_service_catalog (company_id, service_code, name, price, currency, sort_order)
                VALUES (16, %s, %s, %s, 'LEI', %s)
            ''', (code, name, price, idx))
        logger.info('Seeded %d default service catalog items for company 16', len(seed_services))

    # ── Master Service Catalog (new structure) ──────────
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS service_catalog (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL UNIQUE,
            category VARCHAR(100),
            is_active BOOLEAN DEFAULT TRUE,
            sort_order INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS service_catalog_pricing (
            id SERIAL PRIMARY KEY,
            service_id INT NOT NULL REFERENCES service_catalog(id),
            company_id INT NOT NULL REFERENCES companies(id),
            service_code VARCHAR(50),
            price NUMERIC(12,2) NOT NULL,
            currency VARCHAR(10) DEFAULT 'LEI',
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(service_id, company_id)
        )
    ''')
    # department: used across the service-catalog pricing CRUD/queries. Was
    # added out-of-band; declare it here so those endpoints work on a fresh DB.
    cursor.execute('''
        DO $$ BEGIN
            ALTER TABLE service_catalog_pricing ADD COLUMN IF NOT EXISTS department VARCHAR(100);
        EXCEPTION WHEN others THEN NULL;
        END $$;
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_scp_service ON service_catalog_pricing(service_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_scp_company ON service_catalog_pricing(company_id, is_active)')

    # Migrate data from voucher_service_catalog → service_catalog + service_catalog_pricing
    cursor.execute('SELECT COUNT(*) AS cnt FROM service_catalog')
    if cursor.fetchone()['cnt'] == 0:
        # Check if there is legacy data to migrate
        cursor.execute('SELECT COUNT(*) AS cnt FROM voucher_service_catalog')
        legacy_count = cursor.fetchone()['cnt']
        if legacy_count > 0:
            # Insert unique service names into service_catalog
            cursor.execute('''
                INSERT INTO service_catalog (name, category, is_active, sort_order)
                SELECT DISTINCT ON (name)
                    name, category, is_active, sort_order
                FROM voucher_service_catalog
                ORDER BY name, id
                ON CONFLICT (name) DO NOTHING
            ''')
            # Insert company-specific pricing into service_catalog_pricing
            cursor.execute('''
                INSERT INTO service_catalog_pricing (service_id, company_id, service_code, price, currency, is_active)
                SELECT sc.id, vsc.company_id, vsc.service_code, vsc.price, vsc.currency, vsc.is_active
                FROM voucher_service_catalog vsc
                JOIN service_catalog sc ON sc.name = vsc.name
                ON CONFLICT (service_id, company_id) DO NOTHING
            ''')
            logger.info('Migrated %d legacy service catalog entries to new tables', legacy_count)
        else:
            # Seed master services for company 16
            seed_services = [
                ('Oil change', 'Maintenance', 0, 'SVC-OIL', 900),
                ('Tire rotation', 'Maintenance', 1, 'SVC-TIRE', 200),
                ('Brake inspection', 'Maintenance', 2, 'SVC-BRK', 350),
                ('Air filter replacement', 'Maintenance', 3, 'SVC-AIR', 150),
                ('Coolant flush', 'Maintenance', 4, 'SVC-COOL', 400),
                ('Battery check', 'Maintenance', 5, 'SVC-BAT', 100),
                ('Wheel alignment', 'Maintenance', 6, 'SVC-WHL', 300),
                ('Interior cleaning', 'Detailing', 7, 'SVC-CLN', 250),
                ('Exterior wash', 'Detailing', 8, 'SVC-WASH', 120),
                ('AC service', 'Maintenance', 9, 'SVC-AC', 500),
                ('Diagnostic scan', 'Diagnostics', 10, 'SVC-DIAG', 200),
                ('Transmission fluid change', 'Maintenance', 11, 'SVC-TRANS', 600),
            ]
            for name, category, sort_order, code, price in seed_services:
                cursor.execute('''
                    INSERT INTO service_catalog (name, category, sort_order)
                    VALUES (%s, %s, %s)
                    RETURNING id
                ''', (name, category, sort_order))
                svc_id = cursor.fetchone()['id']
                cursor.execute('''
                    INSERT INTO service_catalog_pricing (service_id, company_id, service_code, price, currency)
                    VALUES (%s, 16, %s, %s, 'LEI')
                ''', (svc_id, code, price))
            logger.info('Seeded %d master services with company 16 pricing', len(seed_services))

    # ── service_items_value column on vouchers ────────
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'vouchers' AND column_name = 'service_items_value'
            ) THEN
                ALTER TABLE vouchers ADD COLUMN service_items_value NUMERIC(12,2);
            END IF;
        END $$;
    ''')

    # ── Admin edit audit trail ──────────────────────────
    # Records who changed what when an admin uses the full-edit power
    # (status/benefit/dates overrides). One row per edit; ``changes`` is a
    # {column: {old, new}} JSON diff of the fields that actually changed.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS voucher_audit_log (
            id SERIAL PRIMARY KEY,
            voucher_id INT NOT NULL REFERENCES vouchers(id),
            actor_user_id INT REFERENCES users(id),
            action VARCHAR(30) NOT NULL,
            changes JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_voucher_audit_voucher ON voucher_audit_log(voucher_id)')

    # ── Redeem rate-limiting (brute-force / enumeration protection) ──
    # Append-only log of code lookup/redeem *attempts*. The API throttles the
    # code-based endpoints by IP, by authenticated user and per voucher code.
    # Only FAILED attempts are recorded, so a legitimate redemption never
    # counts toward a limit. Pruned after 7 days by a scheduled cleanup job.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS voucher_redeem_attempts (
            id SERIAL PRIMARY KEY,
            ip VARCHAR(64),
            user_id INT,
            voucher_code VARCHAR(32),
            outcome VARCHAR(16) NOT NULL DEFAULT 'fail',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vra_ip_time ON voucher_redeem_attempts(ip, created_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vra_user_time ON voucher_redeem_attempts(user_id, created_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vra_code_time ON voucher_redeem_attempts(voucher_code, created_at)')

    # ── Voucher issue motives (admin-configurable) ──────
    # A global, admin-managed list of reasons shown in the issue form's Notes
    # picker. The chosen label (or free text via "Other") is stored in
    # vouchers.notes as before — no voucher-row schema change.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS voucher_motives (
            id SERIAL PRIMARY KEY,
            label VARCHAR(120) NOT NULL UNIQUE,
            sort_order INT DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_voucher_motives_active ON voucher_motives(is_active, sort_order)')
    cursor.execute('SELECT COUNT(*) AS cnt FROM voucher_motives')
    if cursor.fetchone()['cnt'] == 0:
        for i, label in enumerate(['Fidelizare client', 'Compensare', 'Promoție', 'Cadou']):
            cursor.execute(
                'INSERT INTO voucher_motives (label, sort_order) VALUES (%s, %s) ON CONFLICT (label) DO NOTHING',
                (label, i),
            )

    # ── V2 Permissions ──────────────────────────────────
    cursor.execute("SELECT COUNT(*) as cnt FROM permissions_v2 WHERE module_key = 'vouchers'")
    if cursor.fetchone()['cnt'] == 0:
        voucher_perms = [
            # Accounting Vouchers section
            ('vouchers', 'Vouchers', 'bi-ticket', 'accounting', 'Accounting Vouchers', 'view', 'View', 'View voucher tracking in Accounting', False, 1),
            ('vouchers', 'Vouchers', 'bi-ticket', 'accounting', 'Accounting Vouchers', 'redeem', 'Redeem', 'Redeem vouchers in Accounting', False, 2),
            ('vouchers', 'Vouchers', 'bi-ticket', 'accounting', 'Accounting Vouchers', 'export', 'Export', 'Export vouchers CSV', False, 3),
            # Profile Vouchers tab
            ('vouchers', 'Vouchers', 'bi-ticket', 'profile', 'Profile Vouchers', 'view', 'View', 'View My Vouchers tab in Profile', False, 4),
            # Form (Issue) Vouchers
            ('vouchers', 'Vouchers', 'bi-ticket', 'form', 'Issue Vouchers', 'view', 'View', 'Access voucher issuance form', False, 5),
        ]
        for p in voucher_perms:
            cursor.execute('''
                INSERT INTO permissions_v2 (module_key, module_label, module_icon,
                                           entity_key, entity_label, action_key, action_label,
                                           description, is_scope_based, sort_order)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (module_key, entity_key, action_key) DO NOTHING
            ''', p)

        # Admin gets all voucher permissions
        cursor.execute('''
            INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
            SELECT r.id, p.id, 'all', TRUE
            FROM roles r
            CROSS JOIN permissions_v2 p
            WHERE r.name = 'Admin' AND p.module_key = 'vouchers'
            ON CONFLICT (role_id, permission_id) DO NOTHING
        ''')

        # Manager gets all voucher permissions
        cursor.execute('''
            INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
            SELECT r.id, p.id, 'all', TRUE
            FROM roles r
            CROSS JOIN permissions_v2 p
            WHERE r.name = 'Manager' AND p.module_key = 'vouchers'
            ON CONFLICT (role_id, permission_id) DO NOTHING
        ''')

        # User gets view + form (issue) only
        cursor.execute('''
            INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
            SELECT r.id, p.id, 'all', TRUE
            FROM roles r
            CROSS JOIN permissions_v2 p
            WHERE r.name = 'User' AND p.module_key = 'vouchers'
            AND p.action_key = 'view'
            ON CONFLICT (role_id, permission_id) DO NOTHING
        ''')

        logger.info('Voucher V2 permissions seeded')

    # ── Add edit/reissue/delete permissions (idempotent) ──
    new_perms = [
        ('vouchers', 'Vouchers', 'bi-ticket', 'accounting', 'Accounting Vouchers', 'edit', 'Edit', 'Edit voucher details', False, 6),
        ('vouchers', 'Vouchers', 'bi-ticket', 'accounting', 'Accounting Vouchers', 'reissue', 'Reissue', 'Reissue a voucher as new', False, 7),
        ('vouchers', 'Vouchers', 'bi-ticket', 'accounting', 'Accounting Vouchers', 'delete', 'Delete', 'Delete vouchers', False, 8),
    ]
    for p in new_perms:
        cursor.execute('''
            INSERT INTO permissions_v2 (module_key, module_label, module_icon,
                                       entity_key, entity_label, action_key, action_label,
                                       description, is_scope_based, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (module_key, entity_key, action_key) DO NOTHING
        ''', p)

    # Grant new permissions to Admin + Manager
    for role_name in ('Admin', 'Manager'):
        cursor.execute('''
            INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
            SELECT r.id, p.id, 'all', TRUE
            FROM roles r
            CROSS JOIN permissions_v2 p
            WHERE r.name = %s AND p.module_key = 'vouchers'
              AND p.action_key IN ('edit', 'reissue', 'delete')
            ON CONFLICT (role_id, permission_id) DO NOTHING
        ''', (role_name,))

    # Viewer gets profile.view + form.view (issue from profile, no Forms section)
    cursor.execute('''
        INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
        SELECT r.id, p.id, 'all', TRUE
        FROM roles r
        CROSS JOIN permissions_v2 p
        WHERE r.name = 'Viewer' AND p.module_key = 'vouchers'
          AND ((p.entity_key = 'profile' AND p.action_key = 'view')
            OR (p.entity_key = 'form' AND p.action_key = 'view'))
        ON CONFLICT (role_id, permission_id) DO UPDATE SET granted = TRUE
    ''')

    conn.commit()
    logger.info('Vouchers schema created/updated')
