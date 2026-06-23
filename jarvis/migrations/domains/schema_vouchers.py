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
                CHECK (status IN ('draft', 'pending_approval', 'approved', 'active', 'rejected', 'redeemed', 'expired'));
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
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'chk_validity_months'
            ) THEN
                ALTER TABLE vouchers ADD CONSTRAINT chk_validity_months
                CHECK (validity_months IN (1, 3, 6, 12, 24));
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

    # Seed default services for company 16 (AUTOWORLD S.R.L.)
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

    conn.commit()
    logger.info('Vouchers schema created/updated')
