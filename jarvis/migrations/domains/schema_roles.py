"""Roles schema: roles, users, permissions v1+v2, seeding."""
import psycopg2
import psycopg2.errors


def create_schema_roles(conn, cursor):
    """Create roles, users, and permission tables."""
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
        ('can_access_statements', 'FALSE'),
        ('can_access_digest', 'FALSE'),
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
            ('ai_agent', 'AI Agent', 'bi-robot', 'settings', 'Settings', 'edit', 'Edit', 'Modify AI agent configuration', FALSE, 7),

            -- AI Agent RAG Source permissions (per-source access control)
            ('ai_agent', 'AI Agent', 'bi-robot', 'rag_source', 'RAG Sources', 'invoice', 'Invoices', 'Access invoice data in AI chat', FALSE, 10),
            ('ai_agent', 'AI Agent', 'bi-robot', 'rag_source', 'RAG Sources', 'company', 'Companies', 'Access company data in AI chat', FALSE, 11),
            ('ai_agent', 'AI Agent', 'bi-robot', 'rag_source', 'RAG Sources', 'department', 'Departments', 'Access department data in AI chat', FALSE, 12),
            ('ai_agent', 'AI Agent', 'bi-robot', 'rag_source', 'RAG Sources', 'employee', 'Employees', 'Access employee data in AI chat', FALSE, 13),
            ('ai_agent', 'AI Agent', 'bi-robot', 'rag_source', 'RAG Sources', 'transaction', 'Bank Transactions', 'Access bank transaction data in AI chat', FALSE, 14),
            ('ai_agent', 'AI Agent', 'bi-robot', 'rag_source', 'RAG Sources', 'efactura', 'e-Factura', 'Access e-Factura data in AI chat', FALSE, 15),
            ('ai_agent', 'AI Agent', 'bi-robot', 'rag_source', 'RAG Sources', 'event', 'HR Events', 'Access HR event data in AI chat', FALSE, 16),
            ('ai_agent', 'AI Agent', 'bi-robot', 'rag_source', 'RAG Sources', 'marketing', 'Marketing Projects', 'Access marketing project data in AI chat', FALSE, 17),
            ('ai_agent', 'AI Agent', 'bi-robot', 'rag_source', 'RAG Sources', 'approval', 'Approvals', 'Access approval data in AI chat', FALSE, 18),
            ('ai_agent', 'AI Agent', 'bi-robot', 'rag_source', 'RAG Sources', 'tag', 'Tags', 'Access tag data in AI chat', FALSE, 19),
            ('ai_agent', 'AI Agent', 'bi-robot', 'rag_source', 'RAG Sources', 'crm_client', 'CRM Clients', 'Access CRM client data in AI chat', FALSE, 20),
            ('ai_agent', 'AI Agent', 'bi-robot', 'rag_source', 'RAG Sources', 'car_dossier', 'Car Dossiers', 'Access car deal data in AI chat', FALSE, 21),

            -- Sales / CRM Module
            ('sales', 'Sales', 'bi-graph-up', 'module', 'Sales Module', 'access', 'Access', 'Access Sales / CRM module', FALSE, 1),
            ('sales', 'Sales', 'bi-graph-up', 'clients', 'Clients', 'view', 'View', 'View client list', FALSE, 2),
            ('sales', 'Sales', 'bi-graph-up', 'clients', 'Clients', 'edit', 'Edit', 'Edit client data', FALSE, 3),
            ('sales', 'Sales', 'bi-graph-up', 'clients', 'Clients', 'delete', 'Delete', 'Delete clients', FALSE, 4),
            ('sales', 'Sales', 'bi-graph-up', 'clients', 'Clients', 'merge', 'Merge', 'Merge duplicate clients', FALSE, 5),
            ('sales', 'Sales', 'bi-graph-up', 'clients', 'Clients', 'export', 'Export', 'Export client data', FALSE, 6),
            ('sales', 'Sales', 'bi-graph-up', 'deals', 'Deals', 'view', 'View', 'View deal list', FALSE, 7),
            ('sales', 'Sales', 'bi-graph-up', 'deals', 'Deals', 'edit', 'Edit', 'Edit deal data', FALSE, 8),
            ('sales', 'Sales', 'bi-graph-up', 'deals', 'Deals', 'delete', 'Delete', 'Delete deals', FALSE, 9),
            ('sales', 'Sales', 'bi-graph-up', 'deals', 'Deals', 'export', 'Export', 'Export deal data', FALSE, 10),
            ('sales', 'Sales', 'bi-graph-up', 'import', 'Import', 'access', 'Access', 'Import CRM data from files', FALSE, 11)
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

    # Migration: Add hr.pontaje_adjustments permissions (for schedule adjustment feature)
    pontaje_adj_perms = [
        ('hr', 'HR', 'bi-people-fill', 'pontaje_adjustments', 'Pontaje Adjustments', 'view', 'View', 'View schedule adjustment history', False, 20),
        ('hr', 'HR', 'bi-people-fill', 'pontaje_adjustments', 'Pontaje Adjustments', 'edit', 'Edit', 'Adjust employee punch records to schedule', False, 21),
    ]
    for p in pontaje_adj_perms:
        cursor.execute('''
            INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (module_key, entity_key, action_key) DO NOTHING
        ''', p)
    # Grant to Admin role by default
    cursor.execute('''
        INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
        SELECT r.id, p.id, 'all', TRUE
        FROM roles r
        CROSS JOIN permissions_v2 p
        WHERE r.name = 'Admin'
        AND p.module_key = 'hr' AND p.entity_key = 'pontaje_adjustments'
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

    # Migration: Add RAG source permissions if they don't exist (for existing databases)
    rag_source_perms = [
        ('ai_agent', 'AI Agent', 'bi-robot', 'rag_source', 'RAG Sources', 'invoice', 'Invoices', 'Access invoice data in AI chat', False, 10),
        ('ai_agent', 'AI Agent', 'bi-robot', 'rag_source', 'RAG Sources', 'company', 'Companies', 'Access company data in AI chat', False, 11),
        ('ai_agent', 'AI Agent', 'bi-robot', 'rag_source', 'RAG Sources', 'department', 'Departments', 'Access department data in AI chat', False, 12),
        ('ai_agent', 'AI Agent', 'bi-robot', 'rag_source', 'RAG Sources', 'employee', 'Employees', 'Access employee data in AI chat', False, 13),
        ('ai_agent', 'AI Agent', 'bi-robot', 'rag_source', 'RAG Sources', 'transaction', 'Bank Transactions', 'Access bank transaction data in AI chat', False, 14),
        ('ai_agent', 'AI Agent', 'bi-robot', 'rag_source', 'RAG Sources', 'efactura', 'e-Factura', 'Access e-Factura data in AI chat', False, 15),
        ('ai_agent', 'AI Agent', 'bi-robot', 'rag_source', 'RAG Sources', 'event', 'HR Events', 'Access HR event data in AI chat', False, 16),
        ('ai_agent', 'AI Agent', 'bi-robot', 'rag_source', 'RAG Sources', 'marketing', 'Marketing Projects', 'Access marketing project data in AI chat', False, 17),
        ('ai_agent', 'AI Agent', 'bi-robot', 'rag_source', 'RAG Sources', 'approval', 'Approvals', 'Access approval data in AI chat', False, 18),
        ('ai_agent', 'AI Agent', 'bi-robot', 'rag_source', 'RAG Sources', 'tag', 'Tags', 'Access tag data in AI chat', False, 19),
    ]
    for p in rag_source_perms:
        cursor.execute('''
            INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (module_key, entity_key, action_key) DO NOTHING
        ''', p)
    # Grant all RAG source permissions to Admin and Manager roles
    cursor.execute('''
        INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
        SELECT r.id, p.id, 'all', TRUE
        FROM roles r
        CROSS JOIN permissions_v2 p
        WHERE r.name IN ('Admin', 'Manager')
        AND p.module_key = 'ai_agent' AND p.entity_key = 'rag_source'
        ON CONFLICT (role_id, permission_id) DO NOTHING
    ''')

    # Seed bilant permissions_v2 if not already present
    cursor.execute("SELECT COUNT(*) as cnt FROM permissions_v2 WHERE module_key = 'bilant'")
    if cursor.fetchone()['cnt'] == 0:
        bilant_perms = [
            ('bilant', 'Bilant', 'bi-clipboard-data', 'templates', 'Templates', 'view', 'View', 'View bilant templates', False, 1),
            ('bilant', 'Bilant', 'bi-clipboard-data', 'templates', 'Templates', 'edit', 'Edit', 'Create, edit, delete and import templates', False, 2),
            ('bilant', 'Bilant', 'bi-clipboard-data', 'generations', 'Generations', 'view', 'View', 'View balance sheet generations', False, 3),
            ('bilant', 'Bilant', 'bi-clipboard-data', 'generations', 'Generations', 'create', 'Create', 'Upload balanta and generate balance sheets', False, 4),
            ('bilant', 'Bilant', 'bi-clipboard-data', 'generations', 'Generations', 'delete', 'Delete', 'Delete balance sheet generations', False, 5),
            ('bilant', 'Bilant', 'bi-clipboard-data', 'generations', 'Generations', 'export', 'Export', 'Download Excel, PDF, XML and TXT exports', False, 6),
            ('bilant', 'Bilant', 'bi-clipboard-data', 'ai_analysis', 'AI Analysis', 'access', 'Access', 'Generate AI financial analysis', False, 7),
            ('bilant', 'Bilant', 'bi-clipboard-data', 'chart_of_accounts', 'Chart of Accounts', 'view', 'View', 'View chart of accounts', False, 8),
            ('bilant', 'Bilant', 'bi-clipboard-data', 'chart_of_accounts', 'Chart of Accounts', 'edit', 'Edit', 'Manage chart of accounts entries', False, 9),
        ]
        for p in bilant_perms:
            cursor.execute('''
                INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (module_key, entity_key, action_key) DO NOTHING
            ''', p)
        # Grant all bilant permissions to Admin
        cursor.execute('''
            INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
            SELECT r.id, p.id, 'all', TRUE
            FROM roles r
            CROSS JOIN permissions_v2 p
            WHERE r.name = 'Admin' AND p.module_key = 'bilant'
            ON CONFLICT (role_id, permission_id) DO NOTHING
        ''')
        # Grant view/create/export to Manager
        cursor.execute('''
            INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
            SELECT r.id, p.id, 'all', TRUE
            FROM roles r
            CROSS JOIN permissions_v2 p
            WHERE r.name = 'Manager' AND p.module_key = 'bilant'
              AND p.action_key IN ('view', 'create', 'export', 'access')
            ON CONFLICT (role_id, permission_id) DO NOTHING
        ''')
        # Grant view to User
        cursor.execute('''
            INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
            SELECT r.id, p.id, 'all', TRUE
            FROM roles r
            CROSS JOIN permissions_v2 p
            WHERE r.name = 'User' AND p.module_key = 'bilant'
              AND p.action_key = 'view'
            ON CONFLICT (role_id, permission_id) DO NOTHING
        ''')
        # Grant view to Viewer
        cursor.execute('''
            INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
            SELECT r.id, p.id, 'all', TRUE
            FROM roles r
            CROSS JOIN permissions_v2 p
            WHERE r.name = 'Viewer' AND p.module_key = 'bilant'
              AND p.action_key = 'view'
            ON CONFLICT (role_id, permission_id) DO NOTHING
        ''')
        conn.commit()

    # Migration: Add Sales/CRM permissions if not already present
    cursor.execute("SELECT COUNT(*) as cnt FROM permissions_v2 WHERE module_key = 'sales'")
    if cursor.fetchone()['cnt'] == 0:
        sales_perms = [
            ('sales', 'Sales', 'bi-graph-up', 'module', 'Sales Module', 'access', 'Access', 'Access Sales / CRM module', False, 1),
            ('sales', 'Sales', 'bi-graph-up', 'clients', 'Clients', 'view', 'View', 'View client list', False, 2),
            ('sales', 'Sales', 'bi-graph-up', 'clients', 'Clients', 'edit', 'Edit', 'Edit client data', False, 3),
            ('sales', 'Sales', 'bi-graph-up', 'clients', 'Clients', 'delete', 'Delete', 'Delete clients', False, 4),
            ('sales', 'Sales', 'bi-graph-up', 'clients', 'Clients', 'merge', 'Merge', 'Merge duplicate clients', False, 5),
            ('sales', 'Sales', 'bi-graph-up', 'clients', 'Clients', 'export', 'Export', 'Export client data', False, 6),
            ('sales', 'Sales', 'bi-graph-up', 'deals', 'Deals', 'view', 'View', 'View deal list', False, 7),
            ('sales', 'Sales', 'bi-graph-up', 'deals', 'Deals', 'edit', 'Edit', 'Edit deal data', False, 8),
            ('sales', 'Sales', 'bi-graph-up', 'deals', 'Deals', 'delete', 'Delete', 'Delete deals', False, 9),
            ('sales', 'Sales', 'bi-graph-up', 'deals', 'Deals', 'export', 'Export', 'Export deal data', False, 10),
            ('sales', 'Sales', 'bi-graph-up', 'import', 'Import', 'access', 'Access', 'Import CRM data from files', False, 11),
        ]
        for p in sales_perms:
            cursor.execute('''
                INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (module_key, entity_key, action_key) DO NOTHING
            ''', p)
        # Grant all Sales permissions to Admin
        cursor.execute('''
            INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
            SELECT r.id, p.id, 'all', TRUE
            FROM roles r
            CROSS JOIN permissions_v2 p
            WHERE r.name = 'Admin' AND p.module_key = 'sales'
            ON CONFLICT (role_id, permission_id) DO NOTHING
        ''')
        # Grant view/access/export to Manager
        cursor.execute('''
            INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
            SELECT r.id, p.id, 'all', TRUE
            FROM roles r
            CROSS JOIN permissions_v2 p
            WHERE r.name = 'Manager' AND p.module_key = 'sales'
              AND p.action_key IN ('access', 'view', 'edit', 'export', 'merge')
            ON CONFLICT (role_id, permission_id) DO NOTHING
        ''')
        # Grant view/access to User
        cursor.execute('''
            INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
            SELECT r.id, p.id, 'all', TRUE
            FROM roles r
            CROSS JOIN permissions_v2 p
            WHERE r.name = 'User' AND p.module_key = 'sales'
              AND p.action_key IN ('access', 'view')
            ON CONFLICT (role_id, permission_id) DO NOTHING
        ''')
        conn.commit()

    # Migration: Add CRM RAG source permissions if not already present
    crm_rag_perms = [
        ('ai_agent', 'AI Agent', 'bi-robot', 'rag_source', 'RAG Sources', 'crm_client', 'CRM Clients', 'Access CRM client data in AI chat', False, 20),
        ('ai_agent', 'AI Agent', 'bi-robot', 'rag_source', 'RAG Sources', 'car_dossier', 'Car Dossiers', 'Access car deal data in AI chat', False, 21),
    ]
    for p in crm_rag_perms:
        cursor.execute('''
            INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (module_key, entity_key, action_key) DO NOTHING
        ''', p)
    # Grant CRM RAG sources to Admin and Manager
    cursor.execute('''
        INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
        SELECT r.id, p.id, 'all', TRUE
        FROM roles r
        CROSS JOIN permissions_v2 p
        WHERE r.name IN ('Admin', 'Manager')
          AND p.module_key = 'ai_agent' AND p.entity_key = 'rag_source'
          AND p.action_key IN ('crm_client', 'car_dossier')
        ON CONFLICT (role_id, permission_id) DO NOTHING
    ''')

    # Migration: Add hr.pontaje.view_original and hr.pontaje.view_adjusted permissions
    cursor.execute("ALTER TABLE roles ADD COLUMN IF NOT EXISTS can_view_original_punches BOOLEAN DEFAULT FALSE")
    cursor.execute("ALTER TABLE roles ADD COLUMN IF NOT EXISTS can_view_adjusted_punches BOOLEAN DEFAULT FALSE")
    pontaje_view_perms = [
        ('hr', 'HR', 'bi-people-fill', 'pontaje', 'Pontaje', 'view_original', 'View Original Punches', 'See actual/raw punch in/out times', False, 22),
        ('hr', 'HR', 'bi-people-fill', 'pontaje', 'Pontaje', 'view_adjusted', 'View Adjusted Punches', 'See corrected punch in/out times', False, 23),
    ]
    for p in pontaje_view_perms:
        cursor.execute('''
            INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (module_key, entity_key, action_key) DO NOTHING
        ''', p)
    # Grant to Admin and Manager by default
    cursor.execute('''
        INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
        SELECT r.id, p.id, 'all', TRUE
        FROM roles r
        CROSS JOIN permissions_v2 p
        WHERE r.name IN ('Admin', 'Manager')
          AND p.module_key = 'hr' AND p.entity_key = 'pontaje'
          AND p.action_key IN ('view_original', 'view_adjusted')
        ON CONFLICT (role_id, permission_id) DO NOTHING
    ''')
    # Sync booleans for existing roles
    cursor.execute("UPDATE roles SET can_view_original_punches = TRUE, can_view_adjusted_punches = TRUE WHERE name IN ('Admin', 'Manager')")

    # Migration: Add hr.pontaje.adjust_punches permission (correct/adjust employee punches)
    cursor.execute("ALTER TABLE roles ADD COLUMN IF NOT EXISTS can_adjust_punches BOOLEAN DEFAULT FALSE")
    pontaje_adjust_perms = [
        ('hr', 'HR', 'bi-people-fill', 'pontaje', 'Pontaje', 'adjust_punches', 'Adjust Punches', 'Correct/adjust employee punch records (individual and bulk)', False, 24),
    ]
    for p in pontaje_adjust_perms:
        cursor.execute('''
            INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (module_key, entity_key, action_key) DO NOTHING
        ''', p)
    cursor.execute('''
        INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
        SELECT r.id, p.id, 'all', TRUE
        FROM roles r
        CROSS JOIN permissions_v2 p
        WHERE r.name IN ('Admin', 'Manager')
          AND p.module_key = 'hr' AND p.entity_key = 'pontaje'
          AND p.action_key = 'adjust_punches'
        ON CONFLICT (role_id, permission_id) DO NOTHING
    ''')
    cursor.execute("UPDATE roles SET can_adjust_punches = TRUE WHERE name IN ('Admin', 'Manager')")

    conn.commit()

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


def _seed_missing_permissions_v2(cursor, conn):
    """Add permissions_v2 entries for modules that were missing coverage.

    Uses ON CONFLICT DO NOTHING so it's safe to run repeatedly.
    After inserting permissions, seeds default role_permissions_v2 for all roles.
    """
    new_perms = [
        # ── DMS Module ──
        ('dms', 'Documents', 'bi-folder2-open', 'categories', 'Categories', 'view', 'View', 'View document categories', False, 1),
        ('dms', 'Documents', 'bi-folder2-open', 'categories', 'Categories', 'manage', 'Manage', 'Create, edit, delete categories', False, 2),
        ('dms', 'Documents', 'bi-folder2-open', 'documents', 'Documents', 'view', 'View', 'View documents', True, 3),
        ('dms', 'Documents', 'bi-folder2-open', 'documents', 'Documents', 'create', 'Create', 'Create new documents', True, 4),
        ('dms', 'Documents', 'bi-folder2-open', 'documents', 'Documents', 'edit', 'Edit', 'Edit documents', True, 5),
        ('dms', 'Documents', 'bi-folder2-open', 'documents', 'Documents', 'delete', 'Delete', 'Delete documents', True, 6),
        ('dms', 'Documents', 'bi-folder2-open', 'documents', 'Documents', 'export', 'Export', 'Export documents', False, 7),
        ('dms', 'Documents', 'bi-folder2-open', 'files', 'Files', 'upload', 'Upload', 'Upload file attachments', False, 8),
        ('dms', 'Documents', 'bi-folder2-open', 'files', 'Files', 'download', 'Download', 'Download file attachments', False, 9),
        ('dms', 'Documents', 'bi-folder2-open', 'files', 'Files', 'delete', 'Delete', 'Delete file attachments', False, 10),
        ('dms', 'Documents', 'bi-folder2-open', 'parties', 'Parties', 'view', 'View', 'View document parties', False, 11),
        ('dms', 'Documents', 'bi-folder2-open', 'parties', 'Parties', 'manage', 'Manage', 'Create, edit, delete parties', False, 12),
        ('dms', 'Documents', 'bi-folder2-open', 'suppliers', 'Suppliers', 'view', 'View', 'View suppliers', True, 13),
        ('dms', 'Documents', 'bi-folder2-open', 'suppliers', 'Suppliers', 'edit', 'Edit', 'Edit suppliers', True, 14),
        ('dms', 'Documents', 'bi-folder2-open', 'suppliers', 'Suppliers', 'delete', 'Delete', 'Delete suppliers', False, 15),
        ('dms', 'Documents', 'bi-folder2-open', 'suppliers', 'Suppliers', 'sync', 'Sync ANAF', 'Sync supplier data from ANAF', False, 16),
        ('dms', 'Documents', 'bi-folder2-open', 'extraction', 'AI Extraction', 'execute', 'Execute', 'Run AI document extraction', False, 17),
        ('dms', 'Documents', 'bi-folder2-open', 'signatures', 'Signatures', 'view', 'View', 'View signature status', False, 18),
        ('dms', 'Documents', 'bi-folder2-open', 'signatures', 'Signatures', 'manage', 'Manage', 'Update signature status', False, 19),
        ('dms', 'Documents', 'bi-folder2-open', 'drive_sync', 'Drive Sync', 'manage', 'Manage', 'Sync documents with Google Drive', False, 20),

        # ── HR Module (missing entities) ──
        ('hr', 'HR', 'bi-people-fill', 'employees', 'Employees', 'view', 'View', 'View employee list', True, 30),
        ('hr', 'HR', 'bi-people-fill', 'employees', 'Employees', 'edit', 'Edit', 'Edit employee data', True, 31),
        ('hr', 'HR', 'bi-people-fill', 'employees', 'Employees', 'delete', 'Delete', 'Delete employees', False, 32),
        ('hr', 'HR', 'bi-people-fill', 'structure', 'Structure', 'view', 'View', 'View company/department structure', False, 33),
        ('hr', 'HR', 'bi-people-fill', 'structure', 'Structure', 'edit', 'Edit', 'Edit company/department structure', False, 34),
        ('hr', 'HR', 'bi-people-fill', 'bonus_types', 'Bonus Types', 'view', 'View', 'View bonus types', False, 35),
        ('hr', 'HR', 'bi-people-fill', 'bonus_types', 'Bonus Types', 'manage', 'Manage', 'Create, edit, delete bonus types', False, 36),
        ('hr', 'HR', 'bi-people-fill', 'team_pontaje', 'Team Pontaje', 'view', 'View', 'View team attendance overview', True, 37),
        ('hr', 'HR', 'bi-people-fill', 'team_pontaje', 'Team Pontaje', 'edit', 'Edit', 'Edit team punch records', True, 38),

        # ── Marketing Module (missing entities) ──
        ('marketing', 'Marketing', 'bi-megaphone', 'objectives', 'OKR / Objectives', 'view', 'View', 'View objectives and key results', True, 20),
        ('marketing', 'Marketing', 'bi-megaphone', 'objectives', 'OKR / Objectives', 'manage', 'Manage', 'Create, edit, delete objectives', True, 21),
        ('marketing', 'Marketing', 'bi-megaphone', 'simulator', 'Budget Simulator', 'view', 'View', 'View campaign simulator', False, 22),
        ('marketing', 'Marketing', 'bi-megaphone', 'simulator', 'Budget Simulator', 'edit', 'Edit', 'Configure simulator benchmarks', False, 23),
        ('marketing', 'Marketing', 'bi-megaphone', 'social', 'Collaboration', 'view', 'View', 'View members, comments, files', True, 24),
        ('marketing', 'Marketing', 'bi-megaphone', 'social', 'Collaboration', 'manage', 'Manage', 'Add members, post comments, upload files', True, 25),
        ('marketing', 'Marketing', 'bi-megaphone', 'events', 'Event Links', 'manage', 'Manage', 'Link/unlink HR events to projects', False, 26),
        ('marketing', 'Marketing', 'bi-megaphone', 'dms_links', 'DMS Links', 'manage', 'Manage', 'Link/unlink DMS documents to projects', False, 27),

        # ── System/Core (missing entities) ──
        ('system', 'System', 'bi-gear-fill', 'tags', 'Tags', 'view', 'View', 'View tags and tag groups', False, 20),
        ('system', 'System', 'bi-gear-fill', 'tags', 'Tags', 'manage', 'Manage', 'Create, edit, delete tags and auto-tag rules', False, 21),
        ('system', 'System', 'bi-gear-fill', 'presets', 'Presets', 'view', 'View', 'View saved presets', False, 22),
        ('system', 'System', 'bi-gear-fill', 'presets', 'Presets', 'manage', 'Manage', 'Create, edit, delete presets', False, 23),
        ('system', 'System', 'bi-gear-fill', 'organization', 'Organization', 'view', 'View', 'View companies, brands, departments', False, 24),
        ('system', 'System', 'bi-gear-fill', 'organization', 'Organization', 'edit', 'Edit', 'Manage companies, brands, departments, VAT', False, 25),
        ('system', 'System', 'bi-gear-fill', 'notifications', 'Notifications', 'view', 'View', 'View notifications', False, 26),
        ('system', 'System', 'bi-gear-fill', 'notifications', 'Notifications', 'manage', 'Manage', 'Configure notification settings', False, 27),
        ('system', 'System', 'bi-gear-fill', 'signatures', 'Signature Requests', 'view', 'View', 'View signature requests', False, 28),
        ('system', 'System', 'bi-gear-fill', 'signatures', 'Signature Requests', 'manage', 'Manage', 'Create and manage signature requests', False, 29),
        ('system', 'System', 'bi-gear-fill', 'drive', 'Drive / Files', 'upload', 'Upload', 'Upload files and attachments', False, 30),
        ('system', 'System', 'bi-gear-fill', 'drive', 'Drive / Files', 'download', 'Download', 'Download files and attachments', False, 31),

        # ── Connectors (Biostar) ──
        ('connectors', 'Connectors', 'bi-plug', 'biostar', 'Biostar', 'view', 'View', 'View Biostar config and employees', False, 1),
        ('connectors', 'Connectors', 'bi-plug', 'biostar', 'Biostar', 'edit', 'Edit', 'Edit Biostar configuration', False, 2),
        ('connectors', 'Connectors', 'bi-plug', 'biostar', 'Biostar', 'sync', 'Sync', 'Sync users from Biostar', False, 3),
        ('connectors', 'Connectors', 'bi-plug', 'biostar', 'Biostar', 'manage', 'Manage', 'Map schedules, manage blacklist', False, 4),
    ]

    for p in new_perms:
        cursor.execute('''
            INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label,
                                        action_key, action_label, description, is_scope_based, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (module_key, entity_key, action_key) DO NOTHING
        ''', p)

    # Now seed role_permissions_v2 for all new permissions that don't have entries yet
    cursor.execute('SELECT id, name FROM roles')
    roles_list = cursor.fetchall()

    # Collect IDs of newly inserted permissions (those without role_permissions_v2 entries)
    cursor.execute('''
        SELECT p.id, p.module_key, p.entity_key, p.action_key, p.is_scope_based
        FROM permissions_v2 p
        WHERE NOT EXISTS (
            SELECT 1 FROM role_permissions_v2 rp WHERE rp.permission_id = p.id
        )
    ''')
    new_perm_rows = cursor.fetchall()

    for role in roles_list:
        role_id = role['id']
        role_name = role['name']

        for perm in new_perm_rows:
            perm_id = perm['id']
            action = perm['action_key']
            module = perm['module_key']
            entity = perm['entity_key']

            if role_name == 'Admin':
                scope = 'all'
            elif role_name == 'Manager':
                if module == 'system' and entity in ('tags', 'presets', 'organization', 'notifications', 'signatures', 'drive'):
                    scope = 'all'
                elif module == 'connectors':
                    scope = 'deny'
                elif action == 'delete':
                    scope = 'department'
                else:
                    scope = 'all'
            elif role_name == 'User':
                if module in ('system', 'connectors'):
                    scope = 'deny'
                elif action in ('delete', 'export', 'manage', 'sync'):
                    scope = 'deny'
                elif action in ('view', 'create', 'upload', 'download'):
                    scope = 'own'
                elif action == 'edit':
                    scope = 'own'
                else:
                    scope = 'deny'
            else:  # Viewer
                if action in ('view', 'download'):
                    scope = 'own'
                else:
                    scope = 'deny'

            granted = scope != 'deny'
            cursor.execute('''
                INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (role_id, permission_id) DO NOTHING
            ''', (role_id, perm_id, scope, granted))

    conn.commit()


def _seed_mobile_permissions_v2(cursor, conn):
    """Add mobile.access and missing module.access v2 permissions.

    Adds:
    - module.access entries for digest, approvals, forms (missing from initial seed)
    - mobile.access entries for all mobile-eligible modules
    Uses ON CONFLICT DO NOTHING so it's safe to run repeatedly.
    """
    new_perms = [
        # ── Missing module.access entries ──
        ('digest',    'Digest',     'bi-newspaper',      'module', 'Digest Module',    'access', 'Access', 'Access Digest channels',    False, 1),
        ('approvals', 'Approvals',  'bi-check2-square',  'module', 'Approvals Module', 'access', 'Access', 'Access Approvals module',   False, 1),
        ('forms',     'Forms',      'bi-ui-checks-grid', 'module', 'Forms Module',     'access', 'Access', 'Access Forms module',       False, 1),

        # ── Mobile access entries (entity_key='mobile') ──
        ('approvals',  'Approvals',  'bi-check2-square',  'mobile', 'Mobile', 'access', 'Mobile Access', 'Show Approvals in mobile app',  False, 50),
        ('forms',      'Forms',      'bi-ui-checks-grid', 'mobile', 'Mobile', 'access', 'Mobile Access', 'Show Forms in mobile app',      False, 50),
        ('ai_agent',   'AI Agent',   'bi-robot',          'mobile', 'Mobile', 'access', 'Mobile Access', 'Show AI Agent in mobile app',   False, 50),
        ('marketing',  'Marketing',  'bi-megaphone',      'mobile', 'Mobile', 'access', 'Mobile Access', 'Show Calendar in mobile app',   False, 50),
        ('digest',     'Digest',     'bi-newspaper',      'mobile', 'Mobile', 'access', 'Mobile Access', 'Show Digest in mobile app',     False, 50),
        ('accounting', 'Accounting', 'bi-calculator',     'mobile', 'Mobile', 'access', 'Mobile Access', 'Show Invoices in mobile app',   False, 50),
    ]

    for p in new_perms:
        cursor.execute('''
            INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label,
                                        action_key, action_label, description, is_scope_based, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (module_key, entity_key, action_key) DO NOTHING
        ''', p)

    # Seed role_permissions_v2 for new permissions that don't have entries yet
    cursor.execute('SELECT id, name FROM roles')
    roles_list = cursor.fetchall()

    cursor.execute('''
        SELECT p.id, p.module_key, p.entity_key, p.action_key
        FROM permissions_v2 p
        WHERE NOT EXISTS (
            SELECT 1 FROM role_permissions_v2 rp WHERE rp.permission_id = p.id
        )
          AND ((p.entity_key = 'module' AND p.action_key = 'access'
                AND p.module_key IN ('digest', 'approvals', 'forms'))
               OR (p.entity_key = 'mobile' AND p.action_key = 'access'))
    ''')
    new_perm_rows = cursor.fetchall()

    for role in roles_list:
        role_id = role['id']
        role_name = role['name']

        for perm in new_perm_rows:
            perm_id = perm['id']
            entity = perm['entity_key']

            if role_name == 'Admin':
                scope = 'all'
            elif entity == 'mobile':
                # Mobile access defaults to 'all' for all roles (backward compat)
                scope = 'all'
            elif role_name in ('Manager', 'User'):
                # Module access for approvals/forms/digest — all roles currently see these
                scope = 'all'
            else:  # Viewer
                scope = 'deny'

            granted = scope != 'deny'
            cursor.execute('''
                INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (role_id, permission_id) DO NOTHING
            ''', (role_id, perm_id, scope, granted))

    conn.commit()
