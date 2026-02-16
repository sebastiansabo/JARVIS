"""Database schema initialization.

Contains all CREATE TABLE, ALTER TABLE, CREATE INDEX statements
and seed data for the JARVIS database.

Called by database.init_db() on module import.
"""
import psycopg2
import psycopg2.errors


def create_schema(conn, cursor):
    """Create all database tables, indexes, and seed data.

    Args:
        conn: Database connection (for commit/rollback)
        cursor: Database cursor from get_cursor(conn)
    """
    # PostgreSQL table definitions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invoices (
            id SERIAL PRIMARY KEY,
            supplier TEXT NOT NULL,
            invoice_template TEXT,
            invoice_number TEXT NOT NULL UNIQUE,
            invoice_date DATE NOT NULL,
            invoice_value NUMERIC(15,2) NOT NULL,
            currency TEXT DEFAULT 'RON',
            value_ron NUMERIC(15,2),
            value_eur NUMERIC(15,2),
            exchange_rate NUMERIC(10,6),
            drive_link TEXT,
            comment TEXT,
            status TEXT DEFAULT 'new',
            deleted_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Add status column if it doesn't exist (migration)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'invoices' AND column_name = 'status') THEN
                ALTER TABLE invoices ADD COLUMN status TEXT DEFAULT 'new';
            END IF;
        END $$;
    ''')

    # Add payment_status column if it doesn't exist (migration)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'invoices' AND column_name = 'payment_status') THEN
                ALTER TABLE invoices ADD COLUMN payment_status TEXT DEFAULT 'not_paid';
            END IF;
        END $$;
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS allocations (
            id SERIAL PRIMARY KEY,
            invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
            company TEXT NOT NULL,
            brand TEXT,
            department TEXT NOT NULL,
            subdepartment TEXT,
            allocation_percent NUMERIC(7,4) NOT NULL,
            allocation_value NUMERIC(15,2) NOT NULL,
            responsible TEXT,
            reinvoice_to TEXT,
            reinvoice_brand TEXT,
            reinvoice_department TEXT,
            reinvoice_subdepartment TEXT,
            locked BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invoice_templates (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            template_type TEXT DEFAULT 'fixed',
            supplier TEXT,
            supplier_vat TEXT,
            customer_vat TEXT,
            currency TEXT DEFAULT 'RON',
            description TEXT,
            invoice_number_regex TEXT,
            invoice_date_regex TEXT,
            invoice_value_regex TEXT,
            date_format TEXT DEFAULT '%Y-%m-%d',
            supplier_regex TEXT,
            supplier_vat_regex TEXT,
            customer_vat_regex TEXT,
            currency_regex TEXT,
            sample_invoice_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS department_structure (
            id SERIAL PRIMARY KEY,
            company TEXT NOT NULL,
            brand TEXT,
            department TEXT NOT NULL,
            subdepartment TEXT,
            manager TEXT,
            marketing TEXT,
            responsable_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            manager_ids INTEGER[],
            marketing_ids INTEGER[],
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Add manager_ids, marketing_ids, and cc_email columns if they don't exist
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'department_structure' AND column_name = 'manager_ids') THEN
                ALTER TABLE department_structure ADD COLUMN manager_ids INTEGER[];
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'department_structure' AND column_name = 'marketing_ids') THEN
                ALTER TABLE department_structure ADD COLUMN marketing_ids INTEGER[];
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'department_structure' AND column_name = 'cc_email') THEN
                ALTER TABLE department_structure ADD COLUMN cc_email TEXT;
            END IF;
        END $$;
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS companies (
            id SERIAL PRIMARY KEY,
            company TEXT NOT NULL UNIQUE,
            brands TEXT,
            vat TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS connectors (
            id SERIAL PRIMARY KEY,
            connector_type TEXT NOT NULL,
            name TEXT NOT NULL,
            status TEXT DEFAULT 'disconnected',
            config JSONB DEFAULT '{}',
            credentials JSONB DEFAULT '{}',
            last_sync TIMESTAMP,
            last_error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS connector_sync_log (
            id SERIAL PRIMARY KEY,
            connector_id INTEGER NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
            sync_type TEXT NOT NULL,
            status TEXT NOT NULL,
            invoices_found INTEGER DEFAULT 0,
            invoices_imported INTEGER DEFAULT 0,
            error_message TEXT,
            details JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ============== BANK STATEMENT TABLES ==============

    # Bank statements - tracks uploaded statement files
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bank_statements (
            id SERIAL PRIMARY KEY,
            filename TEXT NOT NULL,
            file_hash TEXT,
            company_name TEXT,
            company_cui TEXT,
            account_number TEXT,
            period_from DATE,
            period_to DATE,
            total_transactions INTEGER DEFAULT 0,
            new_transactions INTEGER DEFAULT 0,
            duplicate_transactions INTEGER DEFAULT 0,
            uploaded_by INTEGER REFERENCES users(id),
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Index for duplicate detection by file hash
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_statements_hash ON bank_statements(file_hash)')

    # Vendor mappings for bank statement transaction matching
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vendor_mappings (
            id SERIAL PRIMARY KEY,
            pattern TEXT NOT NULL,
            supplier_name TEXT NOT NULL,
            supplier_vat TEXT,
            template_id INTEGER REFERENCES invoice_templates(id) ON DELETE SET NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Bank statement transactions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bank_statement_transactions (
            id SERIAL PRIMARY KEY,
            statement_id INTEGER REFERENCES bank_statements(id) ON DELETE SET NULL,
            statement_file TEXT,
            company_name TEXT,
            company_cui TEXT,
            account_number TEXT,
            transaction_date DATE,
            value_date DATE,
            description TEXT,
            vendor_name TEXT,
            matched_supplier TEXT,
            amount NUMERIC(15,2),
            currency TEXT DEFAULT 'RON',
            original_amount NUMERIC(15,2),
            original_currency TEXT,
            exchange_rate NUMERIC(10,6),
            auth_code TEXT,
            card_number TEXT,
            transaction_type TEXT,
            invoice_id INTEGER REFERENCES invoices(id) ON DELETE SET NULL,
            status TEXT DEFAULT 'pending',
            merged_into_id INTEGER REFERENCES bank_statement_transactions(id) ON DELETE SET NULL,
            is_merged_result BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Add statement_id column if it doesn't exist (for existing databases)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'bank_statement_transactions' AND column_name = 'statement_id'
            ) THEN
                ALTER TABLE bank_statement_transactions
                ADD COLUMN statement_id INTEGER REFERENCES bank_statements(id) ON DELETE SET NULL;
            END IF;
        END $$;
    ''')

    # Add invoice matching columns for auto-match feature
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'bank_statement_transactions' AND column_name = 'suggested_invoice_id') THEN
                ALTER TABLE bank_statement_transactions ADD COLUMN suggested_invoice_id INTEGER REFERENCES invoices(id) ON DELETE SET NULL;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'bank_statement_transactions' AND column_name = 'match_confidence') THEN
                ALTER TABLE bank_statement_transactions ADD COLUMN match_confidence NUMERIC(5,4);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'bank_statement_transactions' AND column_name = 'match_method') THEN
                ALTER TABLE bank_statement_transactions ADD COLUMN match_method TEXT;
            END IF;
        END $$;
    ''')

    # Add merge columns for transaction merging feature
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'bank_statement_transactions' AND column_name = 'merged_into_id') THEN
                ALTER TABLE bank_statement_transactions ADD COLUMN merged_into_id INTEGER REFERENCES bank_statement_transactions(id) ON DELETE SET NULL;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'bank_statement_transactions' AND column_name = 'is_merged_result') THEN
                ALTER TABLE bank_statement_transactions ADD COLUMN is_merged_result BOOLEAN DEFAULT FALSE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'bank_statement_transactions' AND column_name = 'merged_dates_display') THEN
                ALTER TABLE bank_statement_transactions ADD COLUMN merged_dates_display TEXT;
            END IF;
        END $$;
    ''')

    # Indexes for bank_statement_transactions table
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_status ON bank_statement_transactions(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_date ON bank_statement_transactions(transaction_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_supplier ON bank_statement_transactions(matched_supplier)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_transactions_company ON bank_statement_transactions(company_cui)')
    # Unique constraint to prevent duplicate transactions
    # Note: If upgrading, drop old index first: DROP INDEX IF EXISTS idx_unique_transaction;
    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_transaction
        ON bank_statement_transactions (company_cui, account_number, transaction_date, amount, currency, description)
        WHERE company_cui IS NOT NULL
          AND transaction_date IS NOT NULL
          AND amount IS NOT NULL
          AND description IS NOT NULL
    ''')

    # Roles table - defines permission sets
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS roles (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            can_add_invoices BOOLEAN DEFAULT FALSE,
            can_edit_invoices BOOLEAN DEFAULT FALSE,
            can_delete_invoices BOOLEAN DEFAULT FALSE,
            can_view_invoices BOOLEAN DEFAULT FALSE,
            can_access_accounting BOOLEAN DEFAULT FALSE,
            can_access_settings BOOLEAN DEFAULT FALSE,
            can_access_connectors BOOLEAN DEFAULT FALSE,
            can_access_templates BOOLEAN DEFAULT FALSE,
            can_access_hr BOOLEAN DEFAULT FALSE,
            is_hr_manager BOOLEAN DEFAULT FALSE,
            can_access_efactura BOOLEAN DEFAULT FALSE,
            can_access_statements BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Add new columns to roles table if they don't exist (migration for existing databases)
    for col_name, col_default in [
        ('can_access_hr', 'FALSE'),
        ('is_hr_manager', 'FALSE'),
        ('can_access_efactura', 'FALSE'),
        ('can_access_statements', 'FALSE')
    ]:
        cursor.execute(f'''
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                              WHERE table_name = 'roles' AND column_name = '{col_name}') THEN
                    ALTER TABLE roles ADD COLUMN {col_name} BOOLEAN DEFAULT {col_default};
                END IF;
            END $$;
        ''')

    # Users table - references role
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT,
            password_hash TEXT,
            role_id INTEGER REFERENCES roles(id),
            is_active BOOLEAN DEFAULT TRUE,
            last_login TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Add password_hash, last_login, and last_seen columns if they don't exist (migration)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'password_hash') THEN
                ALTER TABLE users ADD COLUMN password_hash TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'last_login') THEN
                ALTER TABLE users ADD COLUMN last_login TIMESTAMP;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'last_seen') THEN
                ALTER TABLE users ADD COLUMN last_seen TIMESTAMP;
            END IF;
        END $$;
    ''')

    # Add organizational fields to users table (migrate from responsables)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'company') THEN
                ALTER TABLE users ADD COLUMN company TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'brand') THEN
                ALTER TABLE users ADD COLUMN brand TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'department') THEN
                ALTER TABLE users ADD COLUMN department TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'subdepartment') THEN
                ALTER TABLE users ADD COLUMN subdepartment TEXT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'org_unit_id') THEN
                ALTER TABLE users ADD COLUMN org_unit_id INTEGER REFERENCES department_structure(id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'notify_on_allocation') THEN
                ALTER TABLE users ADD COLUMN notify_on_allocation BOOLEAN DEFAULT TRUE;
            END IF;
        END $$;
    ''')

    # Add can_edit_invoices column to roles table if it doesn't exist (migration)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'roles' AND column_name = 'can_edit_invoices') THEN
                ALTER TABLE roles ADD COLUMN can_edit_invoices BOOLEAN DEFAULT FALSE;
                -- Set edit permission to TRUE for Admin and Manager roles by default
                UPDATE roles SET can_edit_invoices = TRUE WHERE name IN ('Admin', 'Manager');
            END IF;
        END $$;
    ''')

    # Add can_access_hr column to roles table if it doesn't exist (HR module permission)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'roles' AND column_name = 'can_access_hr') THEN
                ALTER TABLE roles ADD COLUMN can_access_hr BOOLEAN DEFAULT FALSE;
                -- Set HR permission to TRUE for Admin role by default
                UPDATE roles SET can_access_hr = TRUE WHERE name = 'Admin';
            END IF;
        END $$;
    ''')

    # Add is_hr_manager column to roles table if it doesn't exist (HR Manager permission - bonus amounts, export, by employee)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'roles' AND column_name = 'is_hr_manager') THEN
                ALTER TABLE roles ADD COLUMN is_hr_manager BOOLEAN DEFAULT FALSE;
                -- Set HR Manager permission to TRUE for Admin role by default
                UPDATE roles SET is_hr_manager = TRUE WHERE name = 'Admin';
            END IF;
        END $$;
    ''')

    # Permissions table - defines all available permissions grouped by module
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS permissions (
            id SERIAL PRIMARY KEY,
            module_key TEXT NOT NULL,
            permission_key TEXT NOT NULL,
            label TEXT NOT NULL,
            description TEXT,
            icon TEXT,
            sort_order INTEGER DEFAULT 0,
            parent_id INTEGER REFERENCES permissions(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(module_key, permission_key)
        )
    ''')

    # Role permissions junction table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS role_permissions (
            id SERIAL PRIMARY KEY,
            role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
            granted BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(role_id, permission_id)
        )
    ''')

    # ============== Enhanced Permission System (v2) ==============
    # Supports scope-based permissions (deny, own, department, all) and matrix UI

    # Create permission scope enum type if not exists
    cursor.execute('''
        DO $$ BEGIN
            CREATE TYPE permission_scope AS ENUM ('deny', 'own', 'department', 'all');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    ''')

    # Enhanced permissions table with module/entity/action structure
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS permissions_v2 (
            id SERIAL PRIMARY KEY,
            module_key TEXT NOT NULL,
            module_label TEXT NOT NULL,
            module_icon TEXT,
            entity_key TEXT NOT NULL,
            entity_label TEXT NOT NULL,
            action_key TEXT NOT NULL,
            action_label TEXT NOT NULL,
            description TEXT,
            is_scope_based BOOLEAN DEFAULT TRUE,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(module_key, entity_key, action_key)
        )
    ''')

    # Role permissions with scope support
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS role_permissions_v2 (
            id SERIAL PRIMARY KEY,
            role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            permission_id INTEGER NOT NULL REFERENCES permissions_v2(id) ON DELETE CASCADE,
            scope permission_scope DEFAULT 'deny',
            granted BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(role_id, permission_id)
        )
    ''')

    # Seed permissions_v2 if empty
    cursor.execute('SELECT COUNT(*) as cnt FROM permissions_v2')
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute('''
            INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order) VALUES
            -- System Module
            ('system', 'System', 'bi-gear-fill', 'settings', 'Settings', 'access', 'Access', 'Access system settings', FALSE, 1),
            ('system', 'System', 'bi-gear-fill', 'settings', 'Settings', 'edit', 'Edit', 'Modify system settings', FALSE, 2),
            ('system', 'System', 'bi-gear-fill', 'users', 'Users', 'view', 'View', 'View user list', FALSE, 3),
            ('system', 'System', 'bi-gear-fill', 'users', 'Users', 'add', 'Add', 'Create new users', FALSE, 4),
            ('system', 'System', 'bi-gear-fill', 'users', 'Users', 'edit', 'Edit', 'Modify users', FALSE, 5),
            ('system', 'System', 'bi-gear-fill', 'users', 'Users', 'delete', 'Delete', 'Remove users', FALSE, 6),
            ('system', 'System', 'bi-gear-fill', 'roles', 'Roles', 'view', 'View', 'View roles', FALSE, 7),
            ('system', 'System', 'bi-gear-fill', 'roles', 'Roles', 'edit', 'Edit', 'Modify role permissions', FALSE, 8),
            ('system', 'System', 'bi-gear-fill', 'activity_logs', 'Activity Logs', 'view', 'View', 'View activity logs', FALSE, 9),
            ('system', 'System', 'bi-gear-fill', 'theme', 'Theme', 'edit', 'Edit', 'Customize theme settings', FALSE, 10),
            ('system', 'System', 'bi-gear-fill', 'structure', 'Company Structure', 'view', 'View', 'View company structure', FALSE, 11),
            ('system', 'System', 'bi-gear-fill', 'structure', 'Company Structure', 'edit', 'Edit', 'Modify company structure', FALSE, 12),

            -- Invoices Module
            ('invoices', 'Invoices', 'bi-receipt', 'records', 'Invoice Records', 'view', 'View', 'View invoices', TRUE, 1),
            ('invoices', 'Invoices', 'bi-receipt', 'records', 'Invoice Records', 'add', 'Add', 'Create new invoices', TRUE, 2),
            ('invoices', 'Invoices', 'bi-receipt', 'records', 'Invoice Records', 'edit', 'Edit', 'Modify invoices', TRUE, 3),
            ('invoices', 'Invoices', 'bi-receipt', 'records', 'Invoice Records', 'delete', 'Delete', 'Remove invoices', TRUE, 4),
            ('invoices', 'Invoices', 'bi-receipt', 'records', 'Invoice Records', 'export', 'Export', 'Export invoice data', FALSE, 5),
            ('invoices', 'Invoices', 'bi-receipt', 'records', 'Invoice Records', 'parse', 'Parse', 'Parse invoice PDFs with AI', FALSE, 6),
            ('invoices', 'Invoices', 'bi-receipt', 'templates', 'Templates', 'view', 'View', 'View invoice templates', FALSE, 7),
            ('invoices', 'Invoices', 'bi-receipt', 'templates', 'Templates', 'edit', 'Edit', 'Modify invoice templates', FALSE, 8),
            ('invoices', 'Invoices', 'bi-receipt', 'bulk', 'Bulk Processing', 'access', 'Access', 'Access bulk invoice processor', FALSE, 9),

            -- Accounting Module
            ('accounting', 'Accounting', 'bi-calculator', 'dashboard', 'Dashboard', 'access', 'Access', 'Access accounting dashboard', FALSE, 1),
            ('accounting', 'Accounting', 'bi-calculator', 'reports', 'Reports', 'view', 'View', 'View accounting reports', TRUE, 2),
            ('accounting', 'Accounting', 'bi-calculator', 'reports', 'Reports', 'export', 'Export', 'Export reports', FALSE, 3),
            ('accounting', 'Accounting', 'bi-calculator', 'allocations', 'Allocations', 'view', 'View', 'View allocations', TRUE, 4),
            ('accounting', 'Accounting', 'bi-calculator', 'allocations', 'Allocations', 'edit', 'Edit', 'Modify allocations', TRUE, 5),
            ('accounting', 'Accounting', 'bi-calculator', 'connectors', 'Connectors', 'access', 'Access', 'Access external connectors', FALSE, 6),

            -- e-Factura Module
            ('efactura', 'e-Factura', 'bi-file-earmark-code', 'invoices', 'ANAF Invoices', 'access', 'Access', 'Access e-Factura unallocated page', FALSE, 1),
            ('efactura', 'e-Factura', 'bi-file-earmark-code', 'invoices', 'ANAF Invoices', 'view', 'View', 'View e-Factura invoices', TRUE, 2),
            ('efactura', 'e-Factura', 'bi-file-earmark-code', 'invoices', 'ANAF Invoices', 'edit', 'Edit', 'Edit invoice overrides', TRUE, 3),
            ('efactura', 'e-Factura', 'bi-file-earmark-code', 'invoices', 'ANAF Invoices', 'send', 'Send', 'Send to invoice module', FALSE, 4),
            ('efactura', 'e-Factura', 'bi-file-earmark-code', 'invoices', 'ANAF Invoices', 'delete', 'Delete', 'Delete or ignore invoices', FALSE, 5),
            ('efactura', 'e-Factura', 'bi-file-earmark-code', 'sync', 'ANAF Sync', 'execute', 'Execute', 'Sync invoices from ANAF', FALSE, 6),
            ('efactura', 'e-Factura', 'bi-file-earmark-code', 'mappings', 'Supplier Mappings', 'view', 'View', 'View supplier mappings', FALSE, 7),
            ('efactura', 'e-Factura', 'bi-file-earmark-code', 'mappings', 'Supplier Mappings', 'edit', 'Edit', 'Manage supplier mappings', FALSE, 8),
            ('efactura', 'e-Factura', 'bi-file-earmark-code', 'partner_types', 'Partner Types', 'view', 'View', 'View partner types', FALSE, 9),
            ('efactura', 'e-Factura', 'bi-file-earmark-code', 'partner_types', 'Partner Types', 'edit', 'Edit', 'Manage partner types', FALSE, 10),
            ('efactura', 'e-Factura', 'bi-file-earmark-code', 'oauth', 'OAuth Connection', 'manage', 'Manage', 'Manage ANAF OAuth connections', FALSE, 11),

            -- Bank Statements Module
            ('statements', 'Bank Statements', 'bi-bank', 'transactions', 'Transactions', 'access', 'Access', 'Access bank statements page', FALSE, 1),
            ('statements', 'Bank Statements', 'bi-bank', 'transactions', 'Transactions', 'view', 'View', 'View transactions', TRUE, 2),
            ('statements', 'Bank Statements', 'bi-bank', 'transactions', 'Transactions', 'upload', 'Upload', 'Upload bank statements', FALSE, 3),
            ('statements', 'Bank Statements', 'bi-bank', 'transactions', 'Transactions', 'reconcile', 'Reconcile', 'Create invoices from transactions', FALSE, 4),
            ('statements', 'Bank Statements', 'bi-bank', 'mappings', 'Vendor Mappings', 'view', 'View', 'View vendor mappings', FALSE, 5),
            ('statements', 'Bank Statements', 'bi-bank', 'mappings', 'Vendor Mappings', 'edit', 'Edit', 'Manage vendor mappings', FALSE, 6),

            -- HR Module (user management is in System section)
            ('hr', 'HR', 'bi-people-fill', 'module', 'HR Module', 'access', 'Access', 'Access HR module', FALSE, 1),
            ('hr', 'HR', 'bi-people-fill', 'events', 'Events', 'view', 'View', 'View events list', TRUE, 2),
            ('hr', 'HR', 'bi-people-fill', 'events', 'Events', 'add', 'Add', 'Create new events', FALSE, 3),
            ('hr', 'HR', 'bi-people-fill', 'events', 'Events', 'edit', 'Edit', 'Modify events', TRUE, 4),
            ('hr', 'HR', 'bi-people-fill', 'events', 'Events', 'delete', 'Delete', 'Delete events', FALSE, 5),
            ('hr', 'HR', 'bi-people-fill', 'bonuses', 'Bonuses', 'view', 'View', 'View bonuses', TRUE, 6),
            ('hr', 'HR', 'bi-people-fill', 'bonuses', 'Bonuses', 'view_amounts', 'View Amounts', 'View bonus amounts (HR Manager)', FALSE, 7),
            ('hr', 'HR', 'bi-people-fill', 'bonuses', 'Bonuses', 'add', 'Add', 'Create new bonuses', FALSE, 8),
            ('hr', 'HR', 'bi-people-fill', 'bonuses', 'Bonuses', 'edit', 'Edit', 'Modify bonuses', TRUE, 9),
            ('hr', 'HR', 'bi-people-fill', 'bonuses', 'Bonuses', 'delete', 'Delete', 'Delete bonuses', FALSE, 10),
            ('hr', 'HR', 'bi-people-fill', 'bonuses', 'Bonuses', 'export', 'Export', 'Export bonus data', FALSE, 11),
            ('hr', 'HR', 'bi-people-fill', 'settings', 'Settings', 'edit', 'Edit', 'Edit HR settings (lock deadline)', FALSE, 12),

            -- AI Agent Module
            ('ai_agent', 'AI Agent', 'bi-robot', 'chat', 'Chat', 'access', 'Access', 'Access AI Agent chat', FALSE, 1),
            ('ai_agent', 'AI Agent', 'bi-robot', 'chat', 'Chat', 'use', 'Use', 'Send messages to AI', FALSE, 2),
            ('ai_agent', 'AI Agent', 'bi-robot', 'models', 'Models', 'view', 'View', 'View available models', FALSE, 3),
            ('ai_agent', 'AI Agent', 'bi-robot', 'models', 'Models', 'manage', 'Manage', 'Configure model settings and API keys', FALSE, 4),
            ('ai_agent', 'AI Agent', 'bi-robot', 'rag', 'RAG', 'view', 'View', 'View RAG stats and data sources', FALSE, 5),
            ('ai_agent', 'AI Agent', 'bi-robot', 'rag', 'RAG', 'reindex', 'Reindex', 'Trigger RAG reindexing', FALSE, 6),
            ('ai_agent', 'AI Agent', 'bi-robot', 'settings', 'Settings', 'edit', 'Edit', 'Modify AI agent configuration', FALSE, 7)
        ''')

        # Set default permissions for existing roles
        # Get all roles
        cursor.execute('SELECT id, name FROM roles')
        roles_list = cursor.fetchall()

        # Get all permissions
        cursor.execute('SELECT id, module_key, entity_key, action_key, is_scope_based FROM permissions_v2')
        perms_list = cursor.fetchall()

        for role in roles_list:
            role_id = role['id']
            role_name = role['name']

            for perm in perms_list:
                perm_id = perm['id']
                is_scope = perm['is_scope_based']
                module = perm['module_key']
                entity = perm['entity_key']
                action = perm['action_key']

                # Default scope/granted based on role
                if role_name == 'Admin':
                    scope = 'all' if is_scope else 'all'
                    granted = True
                elif role_name == 'Manager':
                    if module == 'system' and entity in ('users', 'roles', 'theme'):
                        scope = 'deny'
                        granted = False
                    elif action == 'delete':
                        scope = 'department' if is_scope else 'department'
                        granted = True
                    else:
                        scope = 'all' if is_scope else 'all'
                        granted = True
                elif role_name == 'User':
                    if module == 'system':
                        scope = 'deny'
                        granted = False
                    elif action in ('delete', 'export'):
                        scope = 'deny'
                        granted = False
                    elif action in ('view', 'add'):
                        scope = 'own' if is_scope else 'own'
                        granted = True
                    elif action == 'edit':
                        scope = 'own' if is_scope else 'own'
                        granted = True
                    else:
                        scope = 'deny'
                        granted = False
                else:  # Viewer
                    if action == 'view' or action == 'access':
                        scope = 'own' if is_scope else 'own'
                        granted = True
                    else:
                        scope = 'deny'
                        granted = False

                cursor.execute('''
                    INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (role_id, permission_id) DO NOTHING
                ''', (role_id, perm_id, scope, granted))

    # Migration: Add hr.settings.edit permission if it doesn't exist (for existing databases)
    cursor.execute('''
        INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order)
        VALUES ('hr', 'HR', 'bi-people-fill', 'settings', 'Settings', 'edit', 'Edit', 'Edit HR settings (lock deadline)', FALSE, 12)
        ON CONFLICT (module_key, entity_key, action_key) DO NOTHING
    ''')
    # Add role_permissions_v2 entries for the new permission (Admin gets it by default)
    cursor.execute('''
        INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
        SELECT r.id, p.id, 'all', TRUE
        FROM roles r
        CROSS JOIN permissions_v2 p
        WHERE r.name = 'Admin'
        AND p.module_key = 'hr' AND p.entity_key = 'settings' AND p.action_key = 'edit'
        ON CONFLICT (role_id, permission_id) DO NOTHING
    ''')

    # Migration: Add AI Agent permissions if they don't exist (for existing databases)
    ai_agent_perms = [
        ('ai_agent', 'AI Agent', 'bi-robot', 'chat', 'Chat', 'access', 'Access', 'Access AI Agent chat', False, 1),
        ('ai_agent', 'AI Agent', 'bi-robot', 'chat', 'Chat', 'use', 'Use', 'Send messages to AI', False, 2),
        ('ai_agent', 'AI Agent', 'bi-robot', 'models', 'Models', 'view', 'View', 'View available models', False, 3),
        ('ai_agent', 'AI Agent', 'bi-robot', 'models', 'Models', 'manage', 'Manage', 'Configure model settings and API keys', False, 4),
        ('ai_agent', 'AI Agent', 'bi-robot', 'rag', 'RAG', 'view', 'View', 'View RAG stats and data sources', False, 5),
        ('ai_agent', 'AI Agent', 'bi-robot', 'rag', 'RAG', 'reindex', 'Reindex', 'Trigger RAG reindexing', False, 6),
        ('ai_agent', 'AI Agent', 'bi-robot', 'settings', 'Settings', 'edit', 'Edit', 'Modify AI agent configuration', False, 7),
    ]
    for p in ai_agent_perms:
        cursor.execute('''
            INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (module_key, entity_key, action_key) DO NOTHING
        ''', p)
    # Grant all AI Agent permissions to Admin role
    cursor.execute('''
        INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
        SELECT r.id, p.id, 'all', TRUE
        FROM roles r
        CROSS JOIN permissions_v2 p
        WHERE r.name = 'Admin'
        AND p.module_key = 'ai_agent'
        ON CONFLICT (role_id, permission_id) DO NOTHING
    ''')
    # Grant chat access/use to Manager and User roles
    cursor.execute('''
        INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
        SELECT r.id, p.id, 'all', TRUE
        FROM roles r
        CROSS JOIN permissions_v2 p
        WHERE r.name IN ('Manager', 'User')
        AND p.module_key = 'ai_agent' AND p.entity_key = 'chat'
        ON CONFLICT (role_id, permission_id) DO NOTHING
    ''')

    # Seed default permissions if table is empty
    cursor.execute('SELECT COUNT(*) as cnt FROM permissions')
    if cursor.fetchone()['cnt'] == 0:
        # Insert module permissions
        cursor.execute('''
            INSERT INTO permissions (module_key, permission_key, label, description, icon, sort_order) VALUES
            -- System module
            ('system', 'settings', 'Settings Access', 'Access to system settings and configuration', 'bi-gear', 1),
            ('system', 'activity_logs', 'Activity Logs', 'View user activity logs', 'bi-clock-history', 2),

            -- Invoices module
            ('invoices', 'view', 'View Invoices', 'View invoice list and details', 'bi-eye', 1),
            ('invoices', 'add', 'Add Invoices', 'Create new invoices', 'bi-plus-circle', 2),
            ('invoices', 'edit', 'Edit Invoices', 'Modify existing invoices', 'bi-pencil', 3),
            ('invoices', 'delete', 'Delete Invoices', 'Remove invoices from system', 'bi-trash', 4),

            -- Accounting module
            ('accounting', 'dashboard', 'Dashboard Access', 'Access accounting dashboard', 'bi-calculator', 1),
            ('accounting', 'export', 'Export Data', 'Export accounting data', 'bi-download', 2),
            ('accounting', 'templates', 'Templates', 'Manage invoice templates', 'bi-file-earmark-text', 3),
            ('accounting', 'connectors', 'Connectors', 'Manage external connectors', 'bi-plug', 4),

            -- HR module
            ('hr', 'access', 'Access HR', 'Access HR module', 'bi-people', 1),
            ('hr', 'manager', 'HR Manager', 'View bonus amounts, export, employee details', 'bi-person-badge', 2)
        ''')

        # Set parent_id for HR manager (child of HR access)
        cursor.execute('''
            UPDATE permissions
            SET parent_id = (SELECT id FROM permissions WHERE module_key = 'hr' AND permission_key = 'access')
            WHERE module_key = 'hr' AND permission_key = 'manager'
        ''')

        # Sync existing role permissions to new table
        cursor.execute('SELECT id, name FROM roles')
        roles = cursor.fetchall()

        for role in roles:
            role_id = role['id']
            # Get current boolean permissions
            cursor.execute('SELECT * FROM roles WHERE id = %s', (role_id,))
            r = cursor.fetchone()

            # Map old columns to new permission keys
            permission_map = {
                ('system', 'settings'): r.get('can_access_settings', False),
                ('invoices', 'view'): r.get('can_view_invoices', False),
                ('invoices', 'add'): r.get('can_add_invoices', False),
                ('invoices', 'edit'): r.get('can_edit_invoices', False),
                ('invoices', 'delete'): r.get('can_delete_invoices', False),
                ('accounting', 'dashboard'): r.get('can_access_accounting', False),
                ('accounting', 'templates'): r.get('can_access_templates', False),
                ('accounting', 'connectors'): r.get('can_access_connectors', False),
                ('hr', 'access'): r.get('can_access_hr', False),
                ('hr', 'manager'): r.get('is_hr_manager', False),
            }

            for (module_key, perm_key), granted in permission_map.items():
                if granted:
                    cursor.execute('''
                        INSERT INTO role_permissions (role_id, permission_id, granted)
                        SELECT %s, id, TRUE FROM permissions
                        WHERE module_key = %s AND permission_key = %s
                        ON CONFLICT (role_id, permission_id) DO NOTHING
                    ''', (role_id, module_key, perm_key))

    # Insert default roles if they don't exist
    cursor.execute('''
        INSERT INTO roles (name, description, can_add_invoices, can_edit_invoices, can_delete_invoices, can_view_invoices,
                          can_access_accounting, can_access_settings, can_access_connectors, can_access_templates)
        VALUES
            ('Admin', 'Full access to all features', TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE),
            ('Manager', 'Can manage invoices and view reports', TRUE, TRUE, TRUE, TRUE, TRUE, FALSE, TRUE, TRUE),
            ('User', 'Can add and view invoices', TRUE, FALSE, FALSE, TRUE, TRUE, FALSE, FALSE, FALSE),
            ('Viewer', 'Read-only access to invoices', FALSE, FALSE, FALSE, TRUE, TRUE, FALSE, FALSE, FALSE)
        ON CONFLICT (name) DO NOTHING
    ''')

    # NOTE: responsables table has been migrated to users table - this table is no longer used
    # All responsable data is now stored in the users table with organizational fields
    # (company, brand, department, subdepartment, notify_on_allocation)

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
            status TEXT DEFAULT 'active' CHECK (status IN ('active', 'coming_soon', 'hidden')),
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Insert default module menu items if table is empty
    cursor.execute('SELECT COUNT(*) as cnt FROM module_menu_items')
    if cursor.fetchone()['cnt'] == 0:
        # Insert parent modules first
        cursor.execute('''
            INSERT INTO module_menu_items (module_key, name, description, icon, url, color, status, sort_order)
            VALUES
                ('accounting', 'Accounting', 'Invoices, Budgets, Statements', 'bi-calculator', '/accounting', '#0d6efd', 'active', 1),
                ('hr', 'HR', 'Events, Bonuses, Employees', 'bi-people', '/hr/events/', '#9c27b0', 'active', 2),
                ('sales', 'Sales', 'Orders, Customers, Reports', 'bi-cart3', '#', '#dc3545', 'coming_soon', 3),
                ('aftersales', 'After Sales', 'Service, Warranty, Support', 'bi-tools', '#', '#198754', 'coming_soon', 4),
                ('settings', 'Settings', 'System Configuration', 'bi-gear', '/settings', '#6c757d', 'active', 5)
            RETURNING id, module_key
        ''')
        parent_rows = cursor.fetchall()
        parent_ids = {row['module_key']: row['id'] for row in parent_rows}

        # Insert submenu items for Accounting
        if 'accounting' in parent_ids:
            cursor.execute('''
                INSERT INTO module_menu_items (parent_id, module_key, name, description, icon, url, color, status, sort_order)
                VALUES
                    (%s, 'accounting_dashboard', 'Dashboard', 'View invoices', 'bi-grid-1x2', '/accounting', '#0d6efd', 'active', 1),
                    (%s, 'accounting_add', 'Add Invoice', 'Create new invoice', 'bi-plus-circle', '/add-invoice', '#0d6efd', 'active', 2),
                    (%s, 'accounting_templates', 'Templates', 'Manage parsing templates', 'bi-file-earmark-code', '/templates', '#0d6efd', 'active', 3),
                    (%s, 'accounting_statements', 'Bank Statements', 'Parse statements', 'bi-bank', '/statements/', '#0d6efd', 'active', 4)
            ''', (parent_ids['accounting'], parent_ids['accounting'], parent_ids['accounting'], parent_ids['accounting']))

        # Insert submenu items for HR
        if 'hr' in parent_ids:
            cursor.execute('''
                INSERT INTO module_menu_items (parent_id, module_key, name, description, icon, url, color, status, sort_order)
                VALUES
                    (%s, 'hr_events', 'Event Bonuses', 'Manage bonuses', 'bi-gift', '/hr/events/', '#9c27b0', 'active', 1),
                    (%s, 'hr_manage_events', 'Manage Events', 'Create/edit events', 'bi-calendar-event', '/hr/events/events', '#9c27b0', 'active', 2),
                    (%s, 'hr_employees', 'Employees', 'Employee list', 'bi-person-lines-fill', '/hr/events/employees', '#9c27b0', 'active', 3)
            ''', (parent_ids['hr'], parent_ids['hr'], parent_ids['hr']))

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

    # ============== HR Module Schema ==============
    # Create separate schema for HR data isolation
    cursor.execute('CREATE SCHEMA IF NOT EXISTS hr')
    conn.commit()

    # NOTE: hr.employees table has been migrated to public.users table
    # All employee data is now stored in the users table with organizational fields
    # (company, brand, department, subdepartment, notify_on_allocation)

    # HR Events table - event definitions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hr.events (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            company TEXT,
            brand TEXT,
            description TEXT,
            created_by INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # HR Event Bonuses table - individual bonus records
    # NOTE: user_id references public.users(id) (consolidated from hr.employees)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hr.event_bonuses (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
            event_id INTEGER NOT NULL REFERENCES hr.events(id) ON DELETE CASCADE,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            participation_start DATE,
            participation_end DATE,
            bonus_days NUMERIC(3,1),
            hours_free INTEGER,
            bonus_net NUMERIC(10,2),
            details TEXT,
            allocation_month TEXT,
            bonus_type_id INTEGER,
            created_by INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # HR Bonus Types table - configurable bonus rates
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hr.bonus_types (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            amount NUMERIC(10,2) NOT NULL,
            days_per_amount NUMERIC(5,2) DEFAULT 1,
            description TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Add bonus_type_id column if not exists (migration for existing databases)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_schema = 'hr' AND table_name = 'event_bonuses'
                          AND column_name = 'bonus_type_id') THEN
                ALTER TABLE hr.event_bonuses ADD COLUMN bonus_type_id INTEGER;
            END IF;
        END $$
    ''')

    # Migration: Rename amount_per_day to amount and add days_per_amount (for existing databases)
    cursor.execute('''
        DO $$
        BEGIN
            -- Rename amount_per_day to amount if old column exists
            IF EXISTS (SELECT 1 FROM information_schema.columns
                      WHERE table_schema = 'hr' AND table_name = 'bonus_types'
                      AND column_name = 'amount_per_day') THEN
                ALTER TABLE hr.bonus_types RENAME COLUMN amount_per_day TO amount;
            END IF;
            -- Add days_per_amount column if not exists
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_schema = 'hr' AND table_name = 'bonus_types'
                          AND column_name = 'days_per_amount') THEN
                ALTER TABLE hr.bonus_types ADD COLUMN days_per_amount NUMERIC(5,2) DEFAULT 1;
            END IF;
        END $$
    ''')

    # HR indexes (hr.employees table removed - using users table now)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hr_events_dates ON hr.events(start_date, end_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hr_bonuses_employee ON hr.event_bonuses(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hr_bonuses_event ON hr.event_bonuses(event_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hr_bonuses_year_month ON hr.event_bonuses(year, month)')
    conn.commit()

    # Migrate existing single reinvoice data to new table (if not already migrated)
    cursor.execute('''
        INSERT INTO reinvoice_destinations (allocation_id, company, brand, department, subdepartment, percentage, value)
        SELECT id, reinvoice_to, reinvoice_brand, reinvoice_department, reinvoice_subdepartment, 100.0, allocation_value
        FROM allocations
        WHERE reinvoice_to IS NOT NULL AND reinvoice_to != ''
        AND NOT EXISTS (
            SELECT 1 FROM reinvoice_destinations rd WHERE rd.allocation_id = allocations.id
        )
    ''')
    conn.commit()

    # Migration: Fix invoices with subtract_vat=true but vat_rate=null
    # Calculate the implied VAT rate from invoice_value and net_value, then match to closest standard rate
    cursor.execute('''
        SELECT id, invoice_value, net_value
        FROM invoices
        WHERE subtract_vat = true AND vat_rate IS NULL AND net_value IS NOT NULL AND net_value > 0
    ''')
    invoices_to_fix = cursor.fetchall()

    if invoices_to_fix:
        # Get available VAT rates
        cursor.execute('SELECT rate FROM vat_rates WHERE is_active = true ORDER BY rate DESC')
        available_rates = [row['rate'] for row in cursor.fetchall()]

        for inv in invoices_to_fix:
            # Calculate implied VAT rate: vat_rate = (invoice_value / net_value - 1) * 100
            implied_rate = (inv['invoice_value'] / inv['net_value'] - 1) * 100

            # Find closest matching rate
            closest_rate = min(available_rates, key=lambda r: abs(r - implied_rate))

            # Update invoice with matched rate
            cursor.execute('UPDATE invoices SET vat_rate = %s WHERE id = %s', (closest_rate, inv['id']))

        conn.commit()

    # ============================================================
    # e-Factura Connector Tables
    # ============================================================

    # Company connections for e-Factura sync
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS efactura_company_connections (
            id SERIAL PRIMARY KEY,
            cif VARCHAR(20) NOT NULL UNIQUE,
            display_name VARCHAR(255) NOT NULL,
            environment VARCHAR(20) NOT NULL DEFAULT 'test',
            last_sync_at TIMESTAMP,
            last_received_cursor VARCHAR(100),
            last_sent_cursor VARCHAR(100),
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            status_message TEXT,
            config JSONB DEFAULT '{}'::JSONB,
            cert_fingerprint VARCHAR(64),
            cert_expires_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    ''')

    # e-Factura invoices
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS efactura_invoices (
            id SERIAL PRIMARY KEY,
            cif_owner VARCHAR(20) NOT NULL,
            direction VARCHAR(20) NOT NULL,
            partner_cif VARCHAR(20) NOT NULL,
            partner_name VARCHAR(500),
            invoice_number VARCHAR(100) NOT NULL,
            invoice_series VARCHAR(50),
            issue_date DATE,
            due_date DATE,
            total_amount NUMERIC(15, 2) NOT NULL DEFAULT 0,
            total_vat NUMERIC(15, 2) NOT NULL DEFAULT 0,
            total_without_vat NUMERIC(15, 2) NOT NULL DEFAULT 0,
            currency VARCHAR(3) NOT NULL DEFAULT 'RON',
            status VARCHAR(20) NOT NULL DEFAULT 'processed',
            company_id INTEGER REFERENCES companies(id),
            jarvis_invoice_id INTEGER REFERENCES invoices(id) ON DELETE SET NULL,
            xml_content TEXT,
            ignored BOOLEAN NOT NULL DEFAULT FALSE,
            deleted_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    ''')

    # Add ignored column if not exists (migration for existing databases)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'efactura_invoices' AND column_name = 'ignored'
            ) THEN
                ALTER TABLE efactura_invoices ADD COLUMN ignored BOOLEAN NOT NULL DEFAULT FALSE;
            END IF;
        END $$;
    ''')

    # Add deleted_at column if not exists (migration for existing databases - bin functionality)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'efactura_invoices' AND column_name = 'deleted_at'
            ) THEN
                ALTER TABLE efactura_invoices ADD COLUMN deleted_at TIMESTAMP;
            END IF;
        END $$;
    ''')

    # Add override columns for per-invoice Type/Department/Subdepartment
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'efactura_invoices' AND column_name = 'type_override'
            ) THEN
                ALTER TABLE efactura_invoices ADD COLUMN type_override VARCHAR(100);
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'efactura_invoices' AND column_name = 'department_override'
            ) THEN
                ALTER TABLE efactura_invoices ADD COLUMN department_override VARCHAR(255);
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'efactura_invoices' AND column_name = 'subdepartment_override'
            ) THEN
                ALTER TABLE efactura_invoices ADD COLUMN subdepartment_override VARCHAR(255);
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'efactura_invoices' AND column_name = 'department_override_2'
            ) THEN
                ALTER TABLE efactura_invoices ADD COLUMN department_override_2 VARCHAR(255);
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'efactura_invoices' AND column_name = 'subdepartment_override_2'
            ) THEN
                ALTER TABLE efactura_invoices ADD COLUMN subdepartment_override_2 VARCHAR(255);
            END IF;
        END $$;
    ''')

    # e-Factura invoice references (ANAF IDs)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS efactura_invoice_refs (
            id SERIAL PRIMARY KEY,
            invoice_id INTEGER NOT NULL REFERENCES efactura_invoices(id) ON DELETE CASCADE,
            external_system VARCHAR(20) NOT NULL DEFAULT 'anaf',
            message_id VARCHAR(100) NOT NULL,
            upload_id VARCHAR(100),
            download_id VARCHAR(100),
            xml_hash VARCHAR(64),
            signature_hash VARCHAR(64),
            raw_response_hash VARCHAR(64),
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    ''')

    # e-Factura invoice artifacts (ZIP, XML, PDF)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS efactura_invoice_artifacts (
            id SERIAL PRIMARY KEY,
            invoice_id INTEGER NOT NULL REFERENCES efactura_invoices(id) ON DELETE CASCADE,
            artifact_type VARCHAR(20) NOT NULL,
            storage_uri TEXT NOT NULL,
            original_filename VARCHAR(255),
            mime_type VARCHAR(100),
            checksum VARCHAR(64),
            size_bytes INTEGER DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    ''')

    # e-Factura sync runs tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS efactura_sync_runs (
            id SERIAL PRIMARY KEY,
            run_id VARCHAR(36) NOT NULL UNIQUE,
            company_cif VARCHAR(20) NOT NULL,
            started_at TIMESTAMP NOT NULL DEFAULT NOW(),
            finished_at TIMESTAMP,
            success BOOLEAN DEFAULT FALSE,
            direction VARCHAR(20),
            messages_checked INTEGER DEFAULT 0,
            invoices_fetched INTEGER DEFAULT 0,
            invoices_created INTEGER DEFAULT 0,
            invoices_updated INTEGER DEFAULT 0,
            invoices_skipped INTEGER DEFAULT 0,
            errors_count INTEGER DEFAULT 0,
            cursor_before VARCHAR(100),
            cursor_after VARCHAR(100),
            error_summary TEXT
        )
    ''')

    # e-Factura sync errors
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS efactura_sync_errors (
            id SERIAL PRIMARY KEY,
            run_id VARCHAR(36) NOT NULL,
            message_id VARCHAR(100),
            invoice_ref VARCHAR(100),
            error_type VARCHAR(20) NOT NULL,
            error_code VARCHAR(50),
            error_message TEXT NOT NULL,
            request_hash VARCHAR(64),
            response_hash VARCHAR(64),
            stack_trace TEXT,
            is_retryable BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    ''')

    # e-Factura OAuth tokens storage
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS efactura_oauth_tokens (
            id SERIAL PRIMARY KEY,
            cif VARCHAR(20) NOT NULL UNIQUE,
            access_token TEXT NOT NULL,
            refresh_token TEXT,
            token_type VARCHAR(20) DEFAULT 'Bearer',
            expires_at TIMESTAMP,
            scope VARCHAR(100),
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    ''')

    # Migration: rename efactura_partner_types → efactura_supplier_types
    cursor.execute('''
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'efactura_partner_types'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'efactura_supplier_types'
            ) THEN
                ALTER TABLE efactura_partner_types RENAME TO efactura_supplier_types;
            END IF;
        END $$;
    ''')

    # e-Factura supplier types - defines supplier types (Service, Merchandise, etc.)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS efactura_supplier_types (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE,
            description TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    ''')
    # Commit to ensure partner_types table exists before creating FK reference
    conn.commit()

    # e-Factura supplier mappings - maps e-Factura partner names to standardized supplier names
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS efactura_supplier_mappings (
            id SERIAL PRIMARY KEY,
            partner_name VARCHAR(255) NOT NULL,
            partner_cif VARCHAR(50),
            supplier_name VARCHAR(255) NOT NULL,
            supplier_note TEXT,
            supplier_vat VARCHAR(50),
            kod_konto VARCHAR(50),
            type_id INTEGER REFERENCES efactura_supplier_types(id),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE(partner_name, partner_cif)
        )
    ''')

    # Migration: Add kod_konto column if it doesn't exist
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'efactura_supplier_mappings' AND column_name = 'kod_konto'
            ) THEN
                ALTER TABLE efactura_supplier_mappings ADD COLUMN kod_konto VARCHAR(50);
            END IF;
        END $$;
    ''')

    # Migration: Add type_id column if it doesn't exist (legacy, will be replaced by junction table)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'efactura_supplier_mappings' AND column_name = 'type_id'
            ) THEN
                ALTER TABLE efactura_supplier_mappings ADD COLUMN type_id INTEGER REFERENCES efactura_supplier_types(id);
            END IF;
        END $$;
    ''')

    # Migration: Add department, subdepartment, and brand columns to supplier mappings
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'efactura_supplier_mappings' AND column_name = 'department'
            ) THEN
                ALTER TABLE efactura_supplier_mappings ADD COLUMN department VARCHAR(255);
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'efactura_supplier_mappings' AND column_name = 'subdepartment'
            ) THEN
                ALTER TABLE efactura_supplier_mappings ADD COLUMN subdepartment VARCHAR(255);
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'efactura_supplier_mappings' AND column_name = 'brand'
            ) THEN
                ALTER TABLE efactura_supplier_mappings ADD COLUMN brand VARCHAR(255);
            END IF;
        END $$;
    ''')

    # Commit to ensure supplier_mappings table exists before creating junction table FK
    conn.commit()

    # Junction table for many-to-many mapping between suppliers and types
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS efactura_supplier_mapping_types (
                mapping_id INTEGER NOT NULL REFERENCES efactura_supplier_mappings(id) ON DELETE CASCADE,
                type_id INTEGER NOT NULL REFERENCES efactura_supplier_types(id) ON DELETE CASCADE,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                PRIMARY KEY (mapping_id, type_id)
            )
        ''')
        conn.commit()
    except Exception as e:
        print(f"Note: efactura_supplier_mapping_types table: {e}")
        conn.rollback()

    # Migration: Move existing type_id data to junction table
    try:
        cursor.execute('''
            INSERT INTO efactura_supplier_mapping_types (mapping_id, type_id)
            SELECT id, type_id FROM efactura_supplier_mappings
            WHERE type_id IS NOT NULL
            ON CONFLICT (mapping_id, type_id) DO NOTHING
        ''')
        conn.commit()
    except Exception as e:
        conn.rollback()

    # Seed default partner types if table is empty
    cursor.execute('SELECT COUNT(*) FROM efactura_supplier_types')
    result = cursor.fetchone()
    if result['count'] == 0:
        cursor.execute('''
            INSERT INTO efactura_supplier_types (name, description) VALUES
            ('Service', 'Service-based suppliers (consultancy, IT, maintenance, etc.)'),
            ('Merchandise', 'Product/goods suppliers (inventory, parts, materials, etc.)')
        ''')

    # Migration: Add hide_in_filter column to partner_types (for "Hide Typed" filter configuration)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'efactura_supplier_types' AND column_name = 'hide_in_filter'
            ) THEN
                ALTER TABLE efactura_supplier_types ADD COLUMN hide_in_filter BOOLEAN NOT NULL DEFAULT TRUE;
            END IF;
        END $$;
    ''')

    # Create indexes for e-Factura tables
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_efactura_connections_status ON efactura_company_connections(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_efactura_invoices_owner ON efactura_invoices(cif_owner, direction)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_efactura_invoices_date ON efactura_invoices(issue_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_efactura_invoices_status ON efactura_invoices(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_efactura_invoices_jarvis ON efactura_invoices(jarvis_invoice_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_efactura_invoices_ignored ON efactura_invoices(ignored)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_efactura_invoices_deleted_at ON efactura_invoices(deleted_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_efactura_refs_message ON efactura_invoice_refs(message_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_efactura_sync_runs_cif ON efactura_sync_runs(company_cif)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_efactura_oauth_cif ON efactura_oauth_tokens(cif)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_efactura_supplier_mappings_partner ON efactura_supplier_mappings(partner_name)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_efactura_supplier_mappings_cif ON efactura_supplier_mappings(partner_cif)')

    # Enable pg_trgm extension for trigram indexes (faster ILIKE searches)
    try:
        cursor.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
        conn.commit()
    except Exception:
        conn.rollback()

    # Create trigram indexes for e-Factura invoice search fields
    try:
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_efactura_invoices_partner_name_trgm ON efactura_invoices USING gin (partner_name gin_trgm_ops)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_efactura_invoices_partner_cif_trgm ON efactura_invoices USING gin (partner_cif gin_trgm_ops)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_efactura_invoices_invoice_number_trgm ON efactura_invoices USING gin (invoice_number gin_trgm_ops)')
        conn.commit()
    except Exception:
        conn.rollback()

    # Create trigram indexes for e-Factura supplier mappings search fields
    try:
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_efactura_mappings_partner_name_trgm ON efactura_supplier_mappings USING gin (partner_name gin_trgm_ops)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_efactura_mappings_supplier_name_trgm ON efactura_supplier_mappings USING gin (supplier_name gin_trgm_ops)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_efactura_mappings_partner_cif_trgm ON efactura_supplier_mappings USING gin (partner_cif gin_trgm_ops)')
        conn.commit()
    except Exception:
        conn.rollback()

    # Unique constraint to prevent duplicate supplier mappings (case-insensitive)
    try:
        cursor.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_efactura_supplier_mappings_partner_name_unique
            ON efactura_supplier_mappings (LOWER(partner_name))
            WHERE is_active = TRUE
        ''')
        conn.commit()
    except Exception:
        conn.rollback()

    conn.commit()

    # ============== Migration: REAL → NUMERIC for financial columns ==============
    # Idempotent: ALTER TYPE on already-NUMERIC columns is a no-op that raises
    # "column is already of type" which we catch and ignore.
    _real_to_numeric_migrations = [
        ('invoices', 'invoice_value', 'NUMERIC(15,2)'),
        ('invoices', 'value_ron', 'NUMERIC(15,2)'),
        ('invoices', 'value_eur', 'NUMERIC(15,2)'),
        ('invoices', 'exchange_rate', 'NUMERIC(10,6)'),
        ('invoices', 'vat_rate', 'NUMERIC(5,2)'),
        ('invoices', 'net_value', 'NUMERIC(15,2)'),
        ('allocations', 'allocation_percent', 'NUMERIC(7,4)'),
        ('allocations', 'allocation_value', 'NUMERIC(15,2)'),
        ('bank_statement_transactions', 'amount', 'NUMERIC(15,2)'),
        ('bank_statement_transactions', 'original_amount', 'NUMERIC(15,2)'),
        ('bank_statement_transactions', 'exchange_rate', 'NUMERIC(10,6)'),
        ('bank_statement_transactions', 'match_confidence', 'NUMERIC(5,4)'),
        ('vat_rates', 'rate', 'NUMERIC(5,2)'),
        ('dropdown_options', 'opacity', 'NUMERIC(3,2)'),
        ('reinvoice_destinations', 'percentage', 'NUMERIC(7,4)'),
        ('reinvoice_destinations', 'value', 'NUMERIC(15,2)'),
    ]
    for table, column, new_type in _real_to_numeric_migrations:
        try:
            cursor.execute(f'ALTER TABLE {table} ALTER COLUMN {column} TYPE {new_type} USING {column}::{new_type}')
            conn.commit()
        except Exception:
            conn.rollback()

    # ============== Missing indexes ==============
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_role_id ON users(role_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bst_invoice_id ON bank_statement_transactions(invoice_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_invoices_payment_status ON invoices(payment_status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_notification_log_status ON notification_log(status)')
    conn.commit()

    # ============== Missing foreign keys ==============
    try:
        cursor.execute('''
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE constraint_name = 'fk_sync_errors_run_id'
                ) THEN
                    ALTER TABLE efactura_sync_errors
                    ADD CONSTRAINT fk_sync_errors_run_id
                    FOREIGN KEY (run_id) REFERENCES efactura_sync_runs(run_id);
                END IF;
            END $$;
        ''')
        conn.commit()
    except Exception:
        conn.rollback()

    # Seed initial data if tables are empty
    cursor.execute('SELECT COUNT(*) FROM department_structure')
    result = cursor.fetchone()
    if result['count'] == 0:
        _seed_department_structure(cursor)

    cursor.execute('SELECT COUNT(*) FROM companies')
    result = cursor.fetchone()
    if result['count'] == 0:
        _seed_companies(cursor)



def _seed_department_structure(cursor):
    """Seed initial department structure data."""
    structure_data = [
        ('Autoworld PLUS S.R.L.', 'Mazda', 'Sales', None, 'Roxana Biris', 'Amanda Gadalean'),
        ('Autoworld PLUS S.R.L.', 'MG Motor', 'Aftersales', 'Piese si Accesorii', 'Mihai Ploscar', 'Amanda Gadalean'),
        ('Autoworld PLUS S.R.L.', 'MG Motor', 'Aftersales', 'Reparatii Generale', 'Mihai Ploscar', 'Amanda Gadalean'),
        ('Autoworld INTERNATIONAL S.R.L.', 'Volkswagen (PKW)', 'Sales', None, 'Ovidiu Ciobanca', 'Raluca Asztalos'),
        ('Autoworld INTERNATIONAL S.R.L.', 'Volkswagen (PKW)', 'Aftersales', 'Piese si Accesorii', 'Ioan Parocescu', 'Raluca Asztalos'),
        ('Autoworld INTERNATIONAL S.R.L.', 'Volkswagen (PKW)', 'Aftersales', 'Reparatii Generale', 'Ioan Parocescu', 'Raluca Asztalos'),
        ('Autoworld INTERNATIONAL S.R.L.', 'Volkswagen Comerciale (LNF)', 'Sales', None, 'Ovidiu Ciobanca', 'Raluca Asztalos'),
        ('Autoworld INTERNATIONAL S.R.L.', 'Volkswagen Comerciale (LNF)', 'Aftersales', 'Piese si Accesorii', 'Ioan Parocescu', 'Raluca Asztalos'),
        ('Autoworld INTERNATIONAL S.R.L.', 'Volkswagen Comerciale (LNF)', 'Aftersales', 'Reparatii Generale', 'Ioan Parocescu', 'Raluca Asztalos'),
        ('Autoworld PREMIUM S.R.L.', 'Audi', 'Sales', None, 'Roger Patrasc', 'George Pop'),
        ('Autoworld PREMIUM S.R.L.', 'AAP', 'Sales', None, 'Roger Patrasc', 'George Pop'),
        ('Autoworld PREMIUM S.R.L.', 'Audi', 'Aftersales', 'Piese si Accesorii', 'Calin Duca', 'George Pop'),
        ('Autoworld PREMIUM S.R.L.', 'Audi', 'Aftersales', 'Reparatii Generale', 'Calin Duca', 'George Pop'),
        ('Autoworld PRESTIGE S.R.L.', 'Volvo', 'Sales', None, 'Madalina Morutan', 'Amanda Gadalean'),
        ('Autoworld PRESTIGE S.R.L.', 'Volvo', 'Aftersales', 'Piese si Accesorii', 'Mihai Ploscar', 'Amanda Gadalean'),
        ('Autoworld PRESTIGE S.R.L.', 'Volvo', 'Aftersales', 'Reparatii Generale', 'Mihai Ploscar', 'Amanda Gadalean'),
        ('Autoworld NEXT S.R.L.', 'DasWeltAuto', 'Sales', None, 'Ovidiu Bucur', 'Raluca Asztalos'),
        ('Autoworld NEXT S.R.L.', 'Autoworld.ro', 'Sales', None, 'Ovidiu Bucur', 'Sebastian Sabo'),
        ('Autoworld ONE S.R.L.', 'Toyota', 'Sales', None, 'Monica Niculae', 'Sebastian Sabo'),
        ('Autoworld ONE S.R.L.', None, 'Aftersales', 'Piese si Accesorii', 'Ovidiu', 'Sebastian Sabo'),
        ('Autoworld ONE S.R.L.', None, 'Aftersales', 'Reparatii Generale', 'Ovidiu', 'Sebastian Sabo'),
        ('AUTOWORLD S.R.L.', None, 'Conducere', None, 'Ioan Mezei', 'Anyone'),
        ('AUTOWORLD S.R.L.', None, 'Administrativ', None, 'Istvan Papp', 'Anyone'),
        ('AUTOWORLD S.R.L.', None, 'HR', None, 'Diana Deac', 'Anyone'),
        ('AUTOWORLD S.R.L.', None, 'Marketing', None, 'Sebastian Sabo', 'Anyone'),
        ('AUTOWORLD S.R.L.', None, 'Contabilitate', None, 'Claudia Bruslea', 'Anyone'),
    ]

    query = '''
        INSERT INTO department_structure (company, brand, department, subdepartment, manager, marketing)
        VALUES (%s, %s, %s, %s, %s, %s)
    '''
    cursor.executemany(query, structure_data)


def _seed_companies(cursor):
    """Seed initial companies with VAT data."""
    companies_data = [
        ('Autoworld PLUS S.R.L.', 'Mazda & MG', 'RO 50022994'),
        ('Autoworld INTERNATIONAL S.R.L.', 'Volkswagen', 'RO 50186890'),
        ('Autoworld PREMIUM S.R.L.', 'Audi & Audi Approved Plus', 'RO 50188939'),
        ('Autoworld PRESTIGE S.R.L.', 'Volvo', 'RO 50186920'),
        ('Autoworld NEXT S.R.L.', 'DasWeltAuto', 'RO 50186814'),
        ('Autoworld INSURANCE S.R.L.', 'Dep Asigurari - partial', 'RO 48988808'),
        ('Autoworld ONE S.R.L.', 'Toyota', 'RO 15128629'),
        ('AUTOWORLD S.R.L.', 'Admin Conta Mkt PLR', 'RO 225615'),
    ]

    query = '''
        INSERT INTO companies (company, brands, vat)
        VALUES (%s, %s, %s)
    '''
    cursor.executemany(query, companies_data)
