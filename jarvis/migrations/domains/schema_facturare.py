"""Facturare generations history schema."""
import logging

logger = logging.getLogger(__name__)


def create_schema_facturare(conn, cursor):
    """Create facturare_generations table for tracking emitted invoices/proformas."""

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS facturare_generations (
            id SERIAL PRIMARY KEY,
            gen_type VARCHAR(20) NOT NULL,
            job_id VARCHAR(100),
            start_no INTEGER NOT NULL,
            end_no INTEGER NOT NULL,
            line_count INTEGER NOT NULL,
            total_amount NUMERIC(14,2) NOT NULL,
            currency VARCHAR(10) DEFAULT 'EUR',
            invoice_date DATE,
            supplier_name VARCHAR(255),
            customer_name VARCHAR(255),
            customer_vat VARCHAR(100),
            intocmit_de VARCHAR(100),
            pdf_data BYTEA,
            xlsx_data BYTEA,
            generated_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)

    # Add note column (idempotent)
    cursor.execute("""
        ALTER TABLE facturare_generations
        ADD COLUMN IF NOT EXISTS note TEXT
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_facturare_gen_type
        ON facturare_generations(gen_type)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_facturare_gen_created
        ON facturare_generations(created_at DESC)
    """)

    # ── Comenzi archive lifecycle (mirror of migrations/007) ──
    cursor.execute("ALTER TABLE facturare_anexas    ADD COLUMN IF NOT EXISTS archive_after TIMESTAMP")
    cursor.execute("ALTER TABLE facturare_anexas    ADD COLUMN IF NOT EXISTS archived_at   TIMESTAMP")
    cursor.execute("ALTER TABLE facturare_anexas    ADD COLUMN IF NOT EXISTS archived      BOOLEAN NOT NULL DEFAULT FALSE")
    cursor.execute("ALTER TABLE facturare_anexas    ADD COLUMN IF NOT EXISTS status        VARCHAR(20) NOT NULL DEFAULT 'NEW'")
    cursor.execute("ALTER TABLE facturare_invoices  ADD COLUMN IF NOT EXISTS archived      BOOLEAN NOT NULL DEFAULT FALSE")
    # Per-invoice rounding mode: FALSE = whole-EUR per car (legacy default, keeps
    # already-issued documents unchanged); TRUE = keep 2 decimals per car ("zecimale").
    cursor.execute("ALTER TABLE facturare_invoices  ADD COLUMN IF NOT EXISTS round_decimals BOOLEAN NOT NULL DEFAULT FALSE")
    cursor.execute("ALTER TABLE facturare_contracts ADD COLUMN IF NOT EXISTS archived      BOOLEAN NOT NULL DEFAULT FALSE")
    cursor.execute("ALTER TABLE facturare_contracts ADD COLUMN IF NOT EXISTS archive_after TIMESTAMP")
    cursor.execute("ALTER TABLE facturare_contracts ADD COLUMN IF NOT EXISTS archived_at   TIMESTAMP")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_fa_archive_after ON facturare_anexas(archive_after) WHERE archive_after IS NOT NULL")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_fc_archive_after ON facturare_contracts(archive_after) WHERE archive_after IS NOT NULL")

    conn.commit()
    logger.info('Facturare generations schema created/verified')
