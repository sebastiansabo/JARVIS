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

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_facturare_gen_type
        ON facturare_generations(gen_type)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_facturare_gen_created
        ON facturare_generations(created_at DESC)
    """)

    conn.commit()
    logger.info('Facturare generations schema created/verified')
