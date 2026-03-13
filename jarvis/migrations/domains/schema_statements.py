"""Bank statements schema: bank_statements, vendor_mappings, bank_statement_transactions."""
import psycopg2
import psycopg2.errors


def create_schema_statements(conn, cursor):
    """Create bank statement tables."""
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
