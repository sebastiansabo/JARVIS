"""Core schema: invoices, allocations, invoice_templates, dept_structure,
companies, structure_nodes, structure_node_members, connectors, connector_sync_log.
"""
import psycopg2
import psycopg2.errors


def create_schema_core(conn, cursor):
    """Create core tables and seed initial data."""
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
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            line_items JSONB,
            invoice_type TEXT DEFAULT 'standard'
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

    # Add parent_company_id and display_order for hierarchical holding structure
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'companies' AND column_name = 'parent_company_id') THEN
                ALTER TABLE companies ADD COLUMN parent_company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL;
                ALTER TABLE companies ADD COLUMN display_order INTEGER DEFAULT 0;
                CREATE INDEX IF NOT EXISTS idx_companies_parent_id ON companies(parent_company_id);
                ALTER TABLE companies ADD CONSTRAINT chk_no_self_parent CHECK (parent_company_id != id);
            END IF;
        END $$;
    ''')

    # Add logo_url to companies for configurable brand/company logos
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'companies' AND column_name = 'logo_url') THEN
                ALTER TABLE companies ADD COLUMN logo_url TEXT;
            END IF;
        END $$;
    ''')

    # Structure nodes (generic 5-level organigram tree under each company)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS structure_nodes (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            parent_id INTEGER REFERENCES structure_nodes(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            level INTEGER NOT NULL DEFAULT 1 CHECK (level BETWEEN 1 AND 5),
            has_team BOOLEAN NOT NULL DEFAULT FALSE,
            display_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sn_company ON structure_nodes(company_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sn_parent ON structure_nodes(parent_id)')

    # Structure node members (responsables + team per organigram node)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS structure_node_members (
            id SERIAL PRIMARY KEY,
            node_id INTEGER NOT NULL REFERENCES structure_nodes(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'team' CHECK (role IN ('responsable', 'team')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT structure_node_members_unique UNIQUE (node_id, user_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_snm_node ON structure_node_members(node_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_snm_user ON structure_node_members(user_id)')

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

    # Seed ANAF connector if not exists
    cursor.execute("SELECT id FROM connectors WHERE connector_type = 'anaf'")
    if not cursor.fetchone():
        cursor.execute('''
            INSERT INTO connectors (connector_type, name, status, config, credentials)
            VALUES ('anaf', 'ANAF Public API', 'connected',
                    '{"api_endpoint": "https://webservicesp.anaf.ro/PlatitorTvaRest/api/v8/ws/tva", "timeout_seconds": 5, "cache_hours": 24}'::jsonb,
                    '{}'::jsonb)
        ''')

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
