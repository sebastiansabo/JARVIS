"""Misc schema: notification_settings/log, user_events, password_reset_tokens,
user_filter_presets, tag_groups, tags, entity_tags, auto_tag_rules, vat_rates,
dropdown_options, theme_settings, module_menu_items, reinvoice_destinations.
"""
import json
import psycopg2
import psycopg2.errors


def create_schema_misc(conn, cursor):
    """Create miscellaneous tables."""
    # Notification settings table - email/SMTP configuration
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notification_settings (
            id SERIAL PRIMARY KEY,
            setting_key TEXT NOT NULL UNIQUE,
            setting_value TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Notification log table - track sent notifications
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notification_log (
            id SERIAL PRIMARY KEY,
            responsable_id INTEGER REFERENCES users(id),
            invoice_id INTEGER REFERENCES invoices(id) ON DELETE CASCADE,
            notification_type TEXT NOT NULL,
            subject TEXT,
            message TEXT,
            status TEXT DEFAULT 'pending',
            error_message TEXT,
            sent_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # User events/audit log table - tracks user actions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_events (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            user_email TEXT,
            event_type TEXT NOT NULL,
            event_description TEXT,
            entity_type TEXT,
            entity_id INTEGER,
            ip_address TEXT,
            user_agent TEXT,
            details JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Password reset tokens table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            token TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMP NOT NULL,
            used_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_token ON password_reset_tokens(token)')

    # User filter presets - named filter/column/sort presets per user per page
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_filter_presets (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            page_key VARCHAR(50) NOT NULL,
            name VARCHAR(100) NOT NULL,
            is_default BOOLEAN DEFAULT FALSE,
            preset_data JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_filter_presets_user_page ON user_filter_presets(user_id, page_key)')
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_user_filter_presets_unique_name ON user_filter_presets(user_id, page_key, LOWER(name))")

    # ============== TAGGING SYSTEM ==============
    # Tag groups - optional groupings (e.g., "Priority", "Status", "Category")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tag_groups (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            color VARCHAR(7) DEFAULT '#6c757d',
            sort_order INTEGER DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    ''')
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tag_groups_name_unique ON tag_groups(LOWER(name)) WHERE is_active = TRUE")

    # Tags - tag definitions (global or private per user)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tags (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            group_id INTEGER REFERENCES tag_groups(id) ON DELETE SET NULL,
            color VARCHAR(7) DEFAULT '#0d6efd',
            icon VARCHAR(50),
            is_global BOOLEAN NOT NULL DEFAULT FALSE,
            created_by INTEGER REFERENCES users(id) ON DELETE CASCADE,
            sort_order INTEGER DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    ''')
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tags_global_name_unique ON tags(LOWER(name)) WHERE is_global = TRUE AND is_active = TRUE")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tags_user_name_unique ON tags(created_by, LOWER(name)) WHERE is_global = FALSE AND is_active = TRUE")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tags_visibility ON tags(is_global, created_by) WHERE is_active = TRUE")

    # Entity tags - polymorphic junction table linking tags to any entity
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS entity_tags (
            id SERIAL PRIMARY KEY,
            tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            entity_type VARCHAR(30) NOT NULL,
            entity_id INTEGER NOT NULL,
            tagged_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE(tag_id, entity_type, entity_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_entity_tags_entity ON entity_tags(entity_type, entity_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_entity_tags_tag ON entity_tags(tag_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_entity_tags_tagged_by ON entity_tags(tagged_by)')

    # Seed default tag groups (only if table is empty)
    cursor.execute('SELECT COUNT(*) as cnt FROM tag_groups')
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute('''
            INSERT INTO tag_groups (name, description, color, sort_order) VALUES
                ('Priority', 'Priority level indicators', '#dc3545', 1),
                ('Status', 'Custom status markers', '#198754', 2),
                ('Category', 'Business categorization', '#0d6efd', 3)
        ''')

    # Seed default global tags (only if tags table is empty)
    cursor.execute('SELECT COUNT(*) as cnt FROM tags')
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute('''
            INSERT INTO tags (name, group_id, color, is_global, sort_order) VALUES
                ('High',   (SELECT id FROM tag_groups WHERE name='Priority'), '#dc3545', TRUE, 1),
                ('Medium', (SELECT id FROM tag_groups WHERE name='Priority'), '#fd7e14', TRUE, 2),
                ('Low',    (SELECT id FROM tag_groups WHERE name='Priority'), '#198754', TRUE, 3),
                ('Review', (SELECT id FROM tag_groups WHERE name='Status'), '#ffc107', TRUE, 1),
                ('Done',   (SELECT id FROM tag_groups WHERE name='Status'), '#198754', TRUE, 2),
                ('Urgent', NULL, '#dc3545', TRUE, 0)
        ''')

    # Auto-tag rules — rule-based automatic tag assignment
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS auto_tag_rules (
            id SERIAL PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            entity_type VARCHAR(30) NOT NULL,
            tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            conditions JSONB NOT NULL DEFAULT '[]',
            match_mode VARCHAR(10) NOT NULL DEFAULT 'all',
            is_active BOOLEAN DEFAULT TRUE,
            run_on_create BOOLEAN DEFAULT TRUE,
            created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_auto_tag_rules_entity_type ON auto_tag_rules(entity_type) WHERE is_active = TRUE')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_auto_tag_rules_tag ON auto_tag_rules(tag_id)')

    # Add match_mode column if it doesn't exist (migration)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'auto_tag_rules' AND column_name = 'match_mode') THEN
                ALTER TABLE auto_tag_rules ADD COLUMN match_mode VARCHAR(10) NOT NULL DEFAULT 'all';
            END IF;
        END $$;
    ''')

    # VAT rates table - configurable VAT percentages
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vat_rates (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            rate NUMERIC(5,2) NOT NULL,
            is_default BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Insert default VAT rates (Romanian standard rates) only if table is empty
    cursor.execute('SELECT COUNT(*) as cnt FROM vat_rates')
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute('''
            INSERT INTO vat_rates (name, rate, is_default, is_active)
            VALUES
                ('19%', 19.0, TRUE, TRUE),
                ('9%', 9.0, FALSE, TRUE),
                ('5%', 5.0, FALSE, TRUE),
                ('0%', 0.0, FALSE, TRUE)
        ''')

    # Dropdown options table - configurable dropdown values for accounting
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dropdown_options (
            id SERIAL PRIMARY KEY,
            dropdown_type TEXT NOT NULL,
            value TEXT NOT NULL,
            label TEXT NOT NULL,
            color TEXT DEFAULT NULL,
            opacity NUMERIC(3,2) DEFAULT 0.7,
            sort_order INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(dropdown_type, value)
        )
    ''')

    # Add color column if it doesn't exist (for existing databases)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'dropdown_options' AND column_name = 'color') THEN
                ALTER TABLE dropdown_options ADD COLUMN color TEXT DEFAULT NULL;
            END IF;
        END $$;
    ''')

    # Add opacity column if it doesn't exist (for existing databases)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'dropdown_options' AND column_name = 'opacity') THEN
                ALTER TABLE dropdown_options ADD COLUMN opacity NUMERIC(3,2) DEFAULT 0.7;
            END IF;
        END $$;
    ''')

    # Add min_role column for status permissions (which roles can set this status)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'dropdown_options' AND column_name = 'min_role') THEN
                ALTER TABLE dropdown_options ADD COLUMN min_role TEXT DEFAULT NULL;
                -- Set default min_role to 'Viewer' for all invoice_status options (most permissive)
                UPDATE dropdown_options SET min_role = 'Viewer' WHERE dropdown_type = 'invoice_status' AND min_role IS NULL;
            END IF;
        END $$;
    ''')

    # Add notify_on_status column for status-based notifications
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'dropdown_options' AND column_name = 'notify_on_status') THEN
                ALTER TABLE dropdown_options ADD COLUMN notify_on_status BOOLEAN DEFAULT FALSE;
            END IF;
        END $$;
    ''')

    # Insert default dropdown options if table is empty
    cursor.execute('SELECT COUNT(*) as cnt FROM dropdown_options')
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute('''
            INSERT INTO dropdown_options (dropdown_type, value, label, color, opacity, sort_order, is_active)
            VALUES
                ('invoice_status', 'new', 'New', '#0d6efd', 0.7, 1, TRUE),
                ('invoice_status', 'processed', 'Processed', '#198754', 0.7, 2, TRUE),
                ('invoice_status', 'incomplete', 'Incomplete', '#ffc107', 0.7, 3, TRUE),
                ('invoice_status', 'eronata', 'Eronata', '#dc3545', 0.7, 4, TRUE),
                ('payment_status', 'not_paid', 'Not Paid', '#dc3545', 0.7, 1, TRUE),
                ('payment_status', 'paid', 'Paid', '#198754', 0.7, 2, TRUE)
        ''')

    # Theme settings table - global theme configuration for Jarvis
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS theme_settings (
            id SERIAL PRIMARY KEY,
            theme_name TEXT NOT NULL DEFAULT 'default',
            is_active BOOLEAN DEFAULT TRUE,
            settings JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Insert default theme if table is empty
    cursor.execute('SELECT COUNT(*) as cnt FROM theme_settings')
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute('''
            INSERT INTO theme_settings (theme_name, is_active, settings)
            VALUES ('Jarvis Default', TRUE, %s)
        ''', (json.dumps({
            'light': {
                'bgBody': '#f5f5f5',
                'bgCard': '#ffffff',
                'bgTableHeader': '#f8f9fa',
                'bgTableHover': '#e3f2fd',
                'bgInput': '#ffffff',
                'textPrimary': '#212529',
                'textSecondary': '#6c757d',
                'borderColor': '#dee2e6',
                'accentPrimary': '#0d6efd',
                'accentSuccess': '#198754',
                'accentWarning': '#ffc107',
                'accentDanger': '#dc3545',
                'navbarBg': '#6c757d'
            },
            'dark': {
                'bgBody': '#1a1a2e',
                'bgCard': '#16213e',
                'bgTableHeader': '#0f3460',
                'bgTableHover': '#1f4068',
                'bgInput': '#0f3460',
                'textPrimary': '#e4e4e4',
                'textSecondary': '#a0a0a0',
                'borderColor': '#2d4a6e',
                'accentPrimary': '#64b5f6',
                'accentSuccess': '#81c784',
                'accentWarning': '#ffb74d',
                'accentDanger': '#ef5350',
                'navbarBg': 'linear-gradient(135deg, #0f3460 0%, #16213e 100%)'
            }
        }),))

    # Module menu items table - configurable navigation menu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS module_menu_items (
            id SERIAL PRIMARY KEY,
            parent_id INTEGER REFERENCES module_menu_items(id) ON DELETE CASCADE,
            module_key TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            icon TEXT DEFAULT 'bi-grid',
            url TEXT,
            color TEXT DEFAULT '#6c757d',
            status TEXT DEFAULT 'active' CHECK (status IN ('active', 'coming_soon', 'hidden', 'archived')),
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Seed module menu items from registry (single source of truth)
    from core.settings.menus.registry import sync_menu_items
    sync_menu_items(cursor)

    # Create indexes for invoice queries (most frequently accessed)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(invoice_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_invoices_date_desc ON invoices(invoice_date DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_invoices_supplier ON invoices(supplier)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_invoices_created_at ON invoices(created_at DESC)')
    # Composite index for common filtered queries (non-deleted, date ordered)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_invoices_deleted_date ON invoices(deleted_at, invoice_date DESC)')

    # Allocation indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_allocations_invoice_id ON allocations(invoice_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_allocations_company ON allocations(company)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_allocations_department ON allocations(department)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_allocations_brand ON allocations(brand)')
    # Composite index for invoice+company lookups (optimizes filtered allocation queries)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_allocations_invoice_company ON allocations(invoice_id, company)')
    # NOTE: idx_allocations_responsible_user_id is created after the column migration below

    # Partial index for non-deleted invoices ordered by date (most common query pattern)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_invoices_active_date ON invoices(invoice_date DESC) WHERE deleted_at IS NULL')

    # User events indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_events_user_id ON user_events(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_events_event_type ON user_events(event_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_events_created_at ON user_events(created_at DESC)')

    # Department structure indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_dept_structure_company ON department_structure(company)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_dept_structure_dept ON department_structure(department)')

    # Commit table creation before attempting migrations
    conn.commit()

    # Add comment column if it doesn't exist (for existing databases)
    try:
        cursor.execute('ALTER TABLE invoices ADD COLUMN comment TEXT')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add reinvoice_brand column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE allocations ADD COLUMN reinvoice_brand TEXT')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add reinvoice_department column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE allocations ADD COLUMN reinvoice_department TEXT')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add reinvoice_subdepartment column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE allocations ADD COLUMN reinvoice_subdepartment TEXT')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add comment column to allocations if it doesn't exist
    try:
        cursor.execute('ALTER TABLE allocations ADD COLUMN comment TEXT')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add value_ron column if it doesn't exist (for currency conversion)
    try:
        cursor.execute('ALTER TABLE invoices ADD COLUMN value_ron NUMERIC(15,2)')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add value_eur column if it doesn't exist (for currency conversion)
    try:
        cursor.execute('ALTER TABLE invoices ADD COLUMN value_eur NUMERIC(15,2)')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add exchange_rate column if it doesn't exist (for currency conversion)
    try:
        cursor.execute('ALTER TABLE invoices ADD COLUMN exchange_rate NUMERIC(10,6)')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add deleted_at column for soft delete (bin functionality)
    try:
        cursor.execute('ALTER TABLE invoices ADD COLUMN deleted_at TIMESTAMP')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Create index for soft delete queries
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_invoices_deleted_at ON invoices(deleted_at)')
    conn.commit()

    # Add vat_rate column if it doesn't exist (for VAT subtraction feature)
    try:
        cursor.execute('ALTER TABLE invoices ADD COLUMN vat_rate NUMERIC(5,2)')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add subtract_vat and net_value columns for VAT subtraction feature
    try:
        cursor.execute('ALTER TABLE invoices ADD COLUMN subtract_vat BOOLEAN DEFAULT FALSE')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    try:
        cursor.execute('ALTER TABLE invoices ADD COLUMN net_value NUMERIC(15,2)')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add role_id column to users table if it doesn't exist (migration from old schema)
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN role_id INTEGER REFERENCES roles(id)')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add is_active column to users table if it doesn't exist
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT TRUE')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add updated_at column to users table if it doesn't exist
    try:
        cursor.execute('ALTER TABLE users ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add responsable_id column to department_structure if it doesn't exist
    try:
        cursor.execute('ALTER TABLE department_structure ADD COLUMN responsable_id INTEGER REFERENCES users(id) ON DELETE SET NULL')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add locked column to allocations if it doesn't exist
    try:
        cursor.execute('ALTER TABLE allocations ADD COLUMN locked BOOLEAN DEFAULT FALSE')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add responsible_user_id column to allocations for faster FK-based queries
    try:
        cursor.execute('ALTER TABLE allocations ADD COLUMN responsible_user_id INTEGER REFERENCES users(id)')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Create index on responsible_user_id for fast profile queries
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_allocations_responsible_user_id ON allocations(responsible_user_id)')
    conn.commit()

    # Migrate existing responsible names to responsible_user_id
    try:
        cursor.execute('''
            UPDATE allocations a
            SET responsible_user_id = u.id
            FROM users u
            WHERE a.responsible_user_id IS NULL
              AND a.responsible IS NOT NULL
              AND LOWER(a.responsible) = LOWER(u.name)
        ''')
        conn.commit()
        print(f"Migrated {cursor.rowcount} allocations to use responsible_user_id")
    except Exception as e:
        print(f"Warning: Could not migrate responsible names to user IDs: {e}")
        conn.rollback()

    # Create reinvoice_destinations table for multi-destination reinvoicing
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reinvoice_destinations (
            id SERIAL PRIMARY KEY,
            allocation_id INTEGER NOT NULL REFERENCES allocations(id) ON DELETE CASCADE,
            company TEXT NOT NULL,
            brand TEXT,
            department TEXT,
            subdepartment TEXT,
            percentage NUMERIC(7,4) NOT NULL,
            value NUMERIC(15,2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()

    # Create index for reinvoice_destinations (using IF NOT EXISTS for reliability)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_reinvoice_dest_allocation ON reinvoice_destinations(allocation_id)')
    conn.commit()

    # Add allocation_mode column to invoices (whole = classic, per_line = multi-line)
    try:
        cursor.execute('ALTER TABLE invoices ADD COLUMN allocation_mode TEXT DEFAULT \'whole\'')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    # Add line_item_index column to allocations (NULL = whole-invoice, 0+ = line item index)
    try:
        cursor.execute('ALTER TABLE allocations ADD COLUMN line_item_index INTEGER')
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_allocations_line_item ON allocations(invoice_id, line_item_index)')
    conn.commit()
