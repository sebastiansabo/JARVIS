-- Migration: Add invoice storage tables for Facturare state machine
-- Date: 2026-06-11
-- Description: Creates invoice, invoice_line, invoice_link, eurofib_export tables

-- ── Enum types ──────────────────────────────────────────────────

DO $$ BEGIN
    CREATE TYPE invoice_type_enum AS ENUM ('PROFORMA', 'ADVANCE', 'STORNO', 'FINAL');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE invoice_state_enum AS ENUM ('DRAFT', 'ISSUED', 'PAID', 'CANCELLED');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE invoice_link_type_enum AS ENUM ('REVERSES', 'PRECEDES', 'REPLACES');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ── invoice ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS facturare_invoices (
    id              SERIAL PRIMARY KEY,
    cod_comanda     VARCHAR(50) NOT NULL,
    invoice_type    invoice_type_enum NOT NULL DEFAULT 'PROFORMA',
    invoice_state   invoice_state_enum NOT NULL DEFAULT 'DRAFT',
    invoice_number  INTEGER,
    issued_date     DATE,
    customer_id     INTEGER NOT NULL REFERENCES crm_clients(id),
    supplier_id     INTEGER NOT NULL REFERENCES companies(id),
    total_amount_eur NUMERIC(12,2) NOT NULL DEFAULT 0,
    total_amount_ron NUMERIC(12,2) NOT NULL DEFAULT 0,
    kurs_applied    NUMERIC(6,4),
    currency        VARCHAR(3) NOT NULL DEFAULT 'EUR',
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by      INTEGER REFERENCES users(id),
    notes           TEXT,

    CONSTRAINT ck_invoice_number_range CHECK (invoice_number IS NULL OR (invoice_number >= 1 AND invoice_number <= 999999999))
);

-- Partial unique indexes: only PROFORMA/STORNO/FINAL are 1-per-cod_comanda.
-- ADVANCE allows 1..3 per cod_comanda (enforced in application layer).
CREATE UNIQUE INDEX IF NOT EXISTS uq_comanda_proforma ON facturare_invoices(cod_comanda) WHERE invoice_type = 'PROFORMA';
CREATE UNIQUE INDEX IF NOT EXISTS uq_comanda_storno ON facturare_invoices(cod_comanda) WHERE invoice_type = 'STORNO';
CREATE UNIQUE INDEX IF NOT EXISTS uq_comanda_final ON facturare_invoices(cod_comanda) WHERE invoice_type = 'FINAL';

CREATE INDEX IF NOT EXISTS idx_facturare_invoices_cod_comanda ON facturare_invoices(cod_comanda);
CREATE INDEX IF NOT EXISTS idx_facturare_invoices_type ON facturare_invoices(invoice_type);
CREATE INDEX IF NOT EXISTS idx_facturare_invoices_state ON facturare_invoices(invoice_state);
CREATE INDEX IF NOT EXISTS idx_facturare_invoices_customer ON facturare_invoices(customer_id);
CREATE INDEX IF NOT EXISTS idx_facturare_invoices_supplier ON facturare_invoices(supplier_id);

-- ── invoice_line ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS facturare_invoice_lines (
    id              SERIAL PRIMARY KEY,
    invoice_id      INTEGER NOT NULL REFERENCES facturare_invoices(id) ON DELETE CASCADE,
    line_number     INTEGER NOT NULL,
    vin             VARCHAR(50) NOT NULL,
    model           VARCHAR(100) NOT NULL,
    culoare         VARCHAR(50),
    list_price_eur  NUMERIC(12,2) NOT NULL DEFAULT 0,
    selling_price_eur NUMERIC(12,2) NOT NULL DEFAULT 0,
    qty             INTEGER NOT NULL DEFAULT 1,
    advance_amount_eur NUMERIC(12,2) NOT NULL DEFAULT 0,
    rest_amount_eur NUMERIC(12,2) NOT NULL DEFAULT 0,
    line_total_eur  NUMERIC(12,2) NOT NULL,
    storno_flag     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_invoice_line_number UNIQUE (invoice_id, line_number)
);

CREATE INDEX IF NOT EXISTS idx_facturare_invoice_lines_invoice ON facturare_invoice_lines(invoice_id);

-- ── invoice_link (state transitions) ────────────────────────────

CREATE TABLE IF NOT EXISTS facturare_invoice_links (
    id                  SERIAL PRIMARY KEY,
    source_invoice_id   INTEGER NOT NULL REFERENCES facturare_invoices(id) ON DELETE CASCADE,
    target_invoice_id   INTEGER NOT NULL REFERENCES facturare_invoices(id) ON DELETE CASCADE,
    link_type           invoice_link_type_enum NOT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_no_self_link CHECK (source_invoice_id != target_invoice_id),
    CONSTRAINT uq_invoice_link UNIQUE (source_invoice_id, target_invoice_id, link_type)
);

CREATE INDEX IF NOT EXISTS idx_facturare_invoice_links_source ON facturare_invoice_links(source_invoice_id);
CREATE INDEX IF NOT EXISTS idx_facturare_invoice_links_target ON facturare_invoice_links(target_invoice_id);

-- ── eurofib_export ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS facturare_eurofib_exports (
    id              SERIAL PRIMARY KEY,
    export_date     DATE NOT NULL,
    invoice_ids     INTEGER[] NOT NULL,
    supplier_id     INTEGER NOT NULL REFERENCES companies(id),
    xlsx_blob       BYTEA NOT NULL,
    exported_by     INTEGER REFERENCES users(id),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    checksum        VARCHAR(64),

    CONSTRAINT uq_eurofib_export_date_supplier UNIQUE (export_date, supplier_id)
);
