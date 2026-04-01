"""CRM schema: crm_import_batches, crm_clients, crm_deals, crm_leads."""
import psycopg2
import psycopg2.errors


def create_schema_crm(conn, cursor):
    """Create CRM / Car Sales Database tables."""
    # ── CRM / Car Sales Database ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS crm_import_batches (
            id SERIAL PRIMARY KEY,
            source_type VARCHAR(20) NOT NULL,
            filename TEXT NOT NULL,
            uploaded_by INTEGER REFERENCES users(id),
            total_rows INTEGER DEFAULT 0,
            new_rows INTEGER DEFAULT 0,
            updated_rows INTEGER DEFAULT 0,
            skipped_rows INTEGER DEFAULT 0,
            new_clients INTEGER DEFAULT 0,
            matched_clients INTEGER DEFAULT 0,
            status VARCHAR(20) DEFAULT 'processing',
            error_log JSONB DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_import_source ON crm_import_batches(source_type)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS crm_clients (
            id SERIAL PRIMARY KEY,
            display_name TEXT NOT NULL,
            name_normalized TEXT NOT NULL,
            client_type VARCHAR(20) DEFAULT 'person',
            phone TEXT,
            phone_raw TEXT,
            email TEXT,
            street TEXT,
            city TEXT,
            region TEXT,
            country TEXT DEFAULT 'Romania',
            company_name TEXT,
            responsible TEXT,
            nr_reg TEXT,
            is_blacklisted BOOLEAN DEFAULT FALSE,
            source_flags JSONB DEFAULT '{}',
            merged_into_id INTEGER REFERENCES crm_clients(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_clients_phone ON crm_clients(phone)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_clients_email ON crm_clients(email)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_clients_merged ON crm_clients(merged_into_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_clients_name ON crm_clients USING gin (name_normalized gin_trgm_ops)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS crm_deals (
            id SERIAL PRIMARY KEY,
            client_id INTEGER REFERENCES crm_clients(id) ON DELETE SET NULL,
            source VARCHAR(5) NOT NULL,
            dealer_code TEXT,
            dealer_name TEXT,
            branch TEXT,
            dossier_number TEXT,
            order_number TEXT,
            contract_date DATE,
            order_date DATE,
            delivery_date DATE,
            invoice_date DATE,
            registration_date DATE,
            entry_date DATE,
            brand TEXT,
            model_name TEXT,
            model_code TEXT,
            model_year INTEGER, order_year INTEGER,
            body_code TEXT,
            vin TEXT,
            engine_code TEXT,
            fuel_type TEXT,
            color TEXT,
            color_code TEXT,
            door_count INTEGER,
            vehicle_type TEXT,
            list_price NUMERIC(12,2),
            purchase_price_net NUMERIC(12,2),
            sale_price_net NUMERIC(12,2),
            gross_profit NUMERIC(12,2),
            discount_value NUMERIC(12,2),
            other_costs NUMERIC(12,2),
            gw_gross_value NUMERIC(12,2),
            dossier_status TEXT,
            order_status TEXT,
            contract_status TEXT,
            sales_person TEXT,
            buyer_name TEXT,
            buyer_address TEXT,
            owner_name TEXT,
            owner_address TEXT,
            customer_group TEXT,
            registration_number TEXT,
            vehicle_specs JSONB DEFAULT '{}',
            import_batch_id INTEGER REFERENCES crm_import_batches(id),
            source_row_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_deals_client ON crm_deals(client_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_deals_source ON crm_deals(source)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_deals_vin ON crm_deals(vin)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_deals_brand ON crm_deals(brand)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_deals_dossier ON crm_deals(source, dossier_number)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_deals_contract ON crm_deals(contract_date DESC)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS crm_leads (
            id SERIAL PRIMARY KEY,
            client_id INTEGER REFERENCES crm_clients(id) ON DELETE SET NULL,
            contact_name TEXT,
            person_type TEXT,
            phone TEXT,
            email TEXT,
            lead_group TEXT,
            lead_text TEXT,
            lead_added_by TEXT,
            added_date TIMESTAMP,
            responsible TEXT,
            first_contact_date TIMESTAMP,
            responsible_assigned_date TIMESTAMP,
            lead_score NUMERIC(5,1),
            lead_status TEXT,
            status_reason TEXT,
            status_notes TEXT,
            status_date TIMESTAMP,
            next_contact TIMESTAMP,
            last_activity TIMESTAMP,
            sales_advisor TEXT,
            model TEXT,
            model_of_interest TEXT,
            utm_source TEXT,
            utm_medium TEXT,
            utm_campaign TEXT,
            utm_term TEXT,
            utm_content TEXT,
            form_type TEXT,
            form_data JSONB DEFAULT '{}',
            import_batch_id INTEGER REFERENCES crm_import_batches(id),
            source_row_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_leads_client ON crm_leads(client_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_leads_status ON crm_leads(lead_status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_leads_group ON crm_leads(lead_group)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_leads_phone ON crm_leads(phone)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_crm_leads_added ON crm_leads(added_date DESC)')

    # -- Clienti import extensions --
    cursor.execute("ALTER TABLE crm_clients ADD COLUMN IF NOT EXISTS contact_person TEXT")
    cursor.execute("ALTER TABLE crm_clients ADD COLUMN IF NOT EXISTS dealer_codes TEXT[]")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS client_phones (
            id SERIAL PRIMARY KEY,
            client_id INTEGER NOT NULL REFERENCES crm_clients(id) ON DELETE CASCADE,
            phone TEXT NOT NULL,
            phone_raw TEXT,
            label TEXT DEFAULT 'main',
            is_primary BOOLEAN DEFAULT FALSE,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_client_phones_client ON client_phones(client_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_client_phones_phone ON client_phones(phone)')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_client_phones_uniq ON client_phones(client_id, phone)')

    # Enable pg_trgm for fuzzy name matching (ignore if not available)
    cursor.execute("""
        DO $$ BEGIN
            CREATE EXTENSION IF NOT EXISTS pg_trgm;
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END $$;
    """)

    conn.commit()
