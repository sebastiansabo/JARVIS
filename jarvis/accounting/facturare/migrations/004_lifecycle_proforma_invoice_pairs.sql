-- Migration 004: Change lifecycle from PROFORMA→ADVANCE→STORNO→FINAL
-- to paired PROFORMA/INVOICE model:
--   PROFORMA 1..N → INVOICE 1..N (paired) → STORNO → FINAL
-- Date: 2026-06-11

-- Drop old tables (clean slate — no production data yet)
DROP TABLE IF EXISTS facturare_eurofib_exports CASCADE;
DROP TABLE IF EXISTS facturare_invoice_links CASCADE;
DROP TABLE IF EXISTS facturare_invoice_lines CASCADE;
DROP TABLE IF EXISTS facturare_invoices CASCADE;
DROP TABLE IF EXISTS facturare_pdf_notes CASCADE;

-- Drop old enum and recreate
DROP TYPE IF EXISTS invoice_type_enum CASCADE;
CREATE TYPE invoice_type_enum AS ENUM ('PROFORMA', 'INVOICE', 'STORNO', 'FINAL');

-- Recreate state enum (unchanged)
DROP TYPE IF EXISTS invoice_state_enum CASCADE;
CREATE TYPE invoice_state_enum AS ENUM ('DRAFT', 'ISSUED', 'PAID', 'CANCELLED');

DROP TYPE IF EXISTS invoice_link_type_enum CASCADE;
CREATE TYPE invoice_link_type_enum AS ENUM ('REVERSES', 'PRECEDES', 'REPLACES');

-- ── facturare_invoices ──────────────────────────────────────────

CREATE TABLE facturare_invoices (
    id              SERIAL PRIMARY KEY,
    contract_ref    VARCHAR(100) NOT NULL,
    anexa_ref       VARCHAR(100) NOT NULL,
    invoice_type    invoice_type_enum NOT NULL DEFAULT 'PROFORMA',
    invoice_state   invoice_state_enum NOT NULL DEFAULT 'DRAFT',
    sequence_number INTEGER NOT NULL DEFAULT 1,  -- 1st proforma, 2nd proforma, etc.
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

    CONSTRAINT ck_invoice_number_range CHECK (invoice_number IS NULL OR (invoice_number >= 1 AND invoice_number <= 9999999))
);

-- STORNO and FINAL are 1-per-anexa; PROFORMA and INVOICE allow multiple
CREATE UNIQUE INDEX uq_anexa_storno ON facturare_invoices(contract_ref, anexa_ref) WHERE invoice_type = 'STORNO';
CREATE UNIQUE INDEX uq_anexa_final  ON facturare_invoices(contract_ref, anexa_ref) WHERE invoice_type = 'FINAL';
-- Each proforma/invoice sequence_number is unique within an anexa
CREATE UNIQUE INDEX uq_anexa_proforma_seq ON facturare_invoices(contract_ref, anexa_ref, sequence_number) WHERE invoice_type = 'PROFORMA';
CREATE UNIQUE INDEX uq_anexa_invoice_seq  ON facturare_invoices(contract_ref, anexa_ref, sequence_number) WHERE invoice_type = 'INVOICE';

CREATE INDEX idx_fi_contract_anexa ON facturare_invoices(contract_ref, anexa_ref);
CREATE INDEX idx_fi_type           ON facturare_invoices(invoice_type);
CREATE INDEX idx_fi_customer       ON facturare_invoices(customer_id);
CREATE INDEX idx_fi_supplier       ON facturare_invoices(supplier_id);

-- ── facturare_invoice_lines ─────────────────────────────────────

CREATE TABLE facturare_invoice_lines (
    id                  SERIAL PRIMARY KEY,
    invoice_id          INTEGER NOT NULL REFERENCES facturare_invoices(id) ON DELETE CASCADE,
    line_number         INTEGER NOT NULL,
    nr_comanda          VARCHAR(50),
    vin                 VARCHAR(50) NOT NULL,
    model               VARCHAR(100) NOT NULL,
    culoare             VARCHAR(50),
    list_price_eur      NUMERIC(12,2) NOT NULL DEFAULT 0,
    selling_price_eur   NUMERIC(12,2) NOT NULL DEFAULT 0,
    qty                 INTEGER NOT NULL DEFAULT 1,
    advance_amount_eur  NUMERIC(12,2) NOT NULL DEFAULT 0,
    rest_amount_eur     NUMERIC(12,2) NOT NULL DEFAULT 0,
    line_total_eur      NUMERIC(12,2) NOT NULL,
    storno_flag         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_invoice_line_number UNIQUE (invoice_id, line_number)
);

CREATE INDEX idx_fil_invoice ON facturare_invoice_lines(invoice_id);

-- ── facturare_invoice_links ─────────────────────────────────────

CREATE TABLE facturare_invoice_links (
    id                  SERIAL PRIMARY KEY,
    source_invoice_id   INTEGER NOT NULL REFERENCES facturare_invoices(id) ON DELETE CASCADE,
    target_invoice_id   INTEGER NOT NULL REFERENCES facturare_invoices(id) ON DELETE CASCADE,
    link_type           invoice_link_type_enum NOT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_no_self_link CHECK (source_invoice_id != target_invoice_id),
    CONSTRAINT uq_invoice_link UNIQUE (source_invoice_id, target_invoice_id, link_type)
);

CREATE INDEX idx_fll_source ON facturare_invoice_links(source_invoice_id);
CREATE INDEX idx_fll_target ON facturare_invoice_links(target_invoice_id);

-- ── facturare_eurofib_exports ───────────────────────────────────

CREATE TABLE facturare_eurofib_exports (
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

-- ── facturare_pdf_notes ─────────────────────────────────────────

CREATE TABLE facturare_pdf_notes (
    id           SERIAL PRIMARY KEY,
    level        VARCHAR(20) NOT NULL CHECK (level IN ('client', 'contract', 'anexa')),
    customer_id  INTEGER REFERENCES crm_clients(id),
    contract_ref VARCHAR(100),
    anexa_ref    VARCHAR(100),
    note_text    TEXT NOT NULL DEFAULT '',
    updated_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by   INTEGER REFERENCES users(id)
);

CREATE UNIQUE INDEX uq_pdfnote_client   ON facturare_pdf_notes(customer_id)                         WHERE level = 'client';
CREATE UNIQUE INDEX uq_pdfnote_contract ON facturare_pdf_notes(customer_id, contract_ref)           WHERE level = 'contract';
CREATE UNIQUE INDEX uq_pdfnote_anexa    ON facturare_pdf_notes(customer_id, contract_ref, anexa_ref) WHERE level = 'anexa';
