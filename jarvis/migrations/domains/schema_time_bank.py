"""HR Time Bank schema: hr.time_bank_transactions."""


def create_schema_time_bank(conn, cursor):
    """Create Time Bank tables."""
    cursor.execute('CREATE SCHEMA IF NOT EXISTS hr')
    conn.commit()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hr.time_bank_transactions (
            id              SERIAL PRIMARY KEY,
            jarvis_user_id  INTEGER NOT NULL REFERENCES public.users(id),
            amount          NUMERIC(8,2) NOT NULL,
            tx_type         VARCHAR(50) NOT NULL,
            description     TEXT,
            reference_type  VARCHAR(50),
            reference_id    INTEGER,
            created_by      INTEGER REFERENCES public.users(id),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_tb_tx_user
        ON hr.time_bank_transactions(jarvis_user_id)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_tb_tx_ref
        ON hr.time_bank_transactions(reference_type, reference_id)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_tb_tx_type
        ON hr.time_bank_transactions(tx_type)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_tb_tx_created
        ON hr.time_bank_transactions(created_at)
    ''')

    # ── Status column (pending → approved → processed) ──
    cursor.execute("""
        DO $$ BEGIN
            ALTER TABLE hr.time_bank_transactions
                ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'approved';
        EXCEPTION WHEN duplicate_column THEN NULL;
        END $$
    """)
    cursor.execute("""
        DO $$ BEGIN
            ALTER TABLE hr.time_bank_transactions
                ADD COLUMN approved_by INTEGER REFERENCES public.users(id);
        EXCEPTION WHEN duplicate_column THEN NULL;
        END $$
    """)
    cursor.execute("""
        DO $$ BEGIN
            ALTER TABLE hr.time_bank_transactions
                ADD COLUMN approved_at TIMESTAMPTZ;
        EXCEPTION WHEN duplicate_column THEN NULL;
        END $$
    """)
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_tb_tx_status
        ON hr.time_bank_transactions(status)
    ''')

    conn.commit()
