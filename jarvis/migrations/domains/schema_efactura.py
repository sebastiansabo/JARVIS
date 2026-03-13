"""e-Factura schema: efactura_* tables."""
import psycopg2
import psycopg2.errors


def create_schema_efactura(conn, cursor):
    """Create e-Factura tables."""
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
