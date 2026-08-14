-- Migration 005: Proper entity hierarchy — Contract → Anexa → Invoices
-- Contracts and Anexas become first-class entities.
-- Vehicle lines move from invoices to anexas.
-- Date: 2026-06-11

-- Drop old tables (clean slate — no production data yet)
DROP TABLE IF EXISTS facturare_eurofib_exports CASCADE;
DROP TABLE IF EXISTS facturare_invoice_links CASCADE;
DROP TABLE IF EXISTS facturare_invoice_lines CASCADE;
DROP TABLE IF EXISTS facturare_invoices CASCADE;
DROP TABLE IF EXISTS facturare_pdf_notes CASCADE;

-- Recreate enums (idempotent)
DROP TYPE IF EXISTS invoice_type_enum CASCADE;
CREATE TYPE invoice_type_enum AS ENUM ('PROFORMA', 'INVOICE', 'STORNO', 'FINAL');
DROP TYPE IF EXISTS invoice_state_enum CASCADE;
CREATE TYPE invoice_state_enum AS ENUM ('DRAFT', 'ISSUED', 'PAID', 'CANCELLED');
DROP TYPE IF EXISTS invoice_link_type_enum CASCADE;
CREATE TYPE invoice_link_type_enum AS ENUM ('REVERSES', 'PRECEDES', 'REPLACES');

-- ── Contracts ───────────────────────────────────────────────────

CREATE TABLE facturare_contracts (
    id              SERIAL PRIMARY KEY,
    contract_ref    VARCHAR(100) NOT NULL,
    supplier_id     INTEGER NOT NULL REFERENCES companies(id),
    customer_id     INTEGER NOT NULL REFERENCES crm_clients(id),
    contract_date   DATE,
    responsible     VARCHAR(100),
    notes           TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by      INTEGER REFERENCES users(id),

    CONSTRAINT uq_contract_ref_supplier UNIQUE (contract_ref, supplier_id)
);

CREATE INDEX idx_fc_supplier ON facturare_contracts(supplier_id);
CREATE INDEX idx_fc_customer ON facturare_contracts(customer_id);

-- ── Anexas (within a contract) ──────────────────────────────────

CREATE TABLE facturare_anexas (
    id              SERIAL PRIMARY KEY,
    contract_id     INTEGER NOT NULL REFERENCES facturare_contracts(id) ON DELETE CASCADE,
    anexa_number    INTEGER NOT NULL,
    notes           TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by      INTEGER REFERENCES users(id),

    CONSTRAINT uq_contract_anexa UNIQUE (contract_id, anexa_number)
);

CREATE INDEX idx_fa_contract ON facturare_anexas(contract_id);

-- ── Anexa lines (vehicles — live on the anexa, not on invoices) ─

CREATE TABLE facturare_anexa_lines (
    id                  SERIAL PRIMARY KEY,
    anexa_id            INTEGER NOT NULL REFERENCES facturare_anexas(id) ON DELETE CASCADE,
    line_number         INTEGER NOT NULL,
    nr_comanda          VARCHAR(50),
    vin                 VARCHAR(50),
    model               VARCHAR(100) NOT NULL,
    culoare             VARCHAR(50),
    list_price_eur      NUMERIC(12,2) NOT NULL DEFAULT 0,
    selling_price_eur   NUMERIC(12,2) NOT NULL DEFAULT 0,
    qty                 INTEGER NOT NULL DEFAULT 1,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_anexa_line UNIQUE (anexa_id, line_number)
);

CREATE INDEX idx_fal_anexa ON facturare_anexa_lines(anexa_id);

-- ── Invoices (lighter — reference anexa, just amount + metadata) ─

CREATE TABLE facturare_invoices (
    id              SERIAL PRIMARY KEY,
    anexa_id        INTEGER NOT NULL REFERENCES facturare_anexas(id) ON DELETE CASCADE,
    invoice_type    invoice_type_enum NOT NULL DEFAULT 'PROFORMA',
    invoice_state   invoice_state_enum NOT NULL DEFAULT 'DRAFT',
    sequence_number INTEGER NOT NULL DEFAULT 1,
    invoice_number  INTEGER,
    issued_date     DATE,
    total_amount_eur NUMERIC(12,2) NOT NULL DEFAULT 0,
    total_amount_ron NUMERIC(12,2) NOT NULL DEFAULT 0,
    kurs_applied    NUMERIC(6,4),
    currency        VARCHAR(3) NOT NULL DEFAULT 'EUR',
    intocmit_de     VARCHAR(100),
    notes           TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by      INTEGER REFERENCES users(id),

    CONSTRAINT ck_invoice_number_range CHECK (invoice_number IS NULL OR (invoice_number >= 1 AND invoice_number <= 999999999))
);

-- One STORNO and FINAL per anexa; PROFORMA and INVOICE allow multiple
CREATE UNIQUE INDEX uq_anexa_storno ON facturare_invoices(anexa_id) WHERE invoice_type = 'STORNO';
CREATE UNIQUE INDEX uq_anexa_final  ON facturare_invoices(anexa_id) WHERE invoice_type = 'FINAL';
CREATE UNIQUE INDEX uq_anexa_proforma_seq ON facturare_invoices(anexa_id, sequence_number) WHERE invoice_type = 'PROFORMA';
CREATE UNIQUE INDEX uq_anexa_invoice_seq  ON facturare_invoices(anexa_id, sequence_number) WHERE invoice_type = 'INVOICE';

CREATE INDEX idx_fi_anexa ON facturare_invoices(anexa_id);
CREATE INDEX idx_fi_type  ON facturare_invoices(invoice_type);

-- ── Invoice links (state transitions) ───────────────────────────

CREATE TABLE facturare_invoice_links (
    id                  SERIAL PRIMARY KEY,
    source_invoice_id   INTEGER NOT NULL REFERENCES facturare_invoices(id) ON DELETE CASCADE,
    target_invoice_id   INTEGER NOT NULL REFERENCES facturare_invoices(id) ON DELETE CASCADE,
    link_type           invoice_link_type_enum NOT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_no_self_link CHECK (source_invoice_id != target_invoice_id),
    CONSTRAINT uq_invoice_link UNIQUE (source_invoice_id, target_invoice_id, link_type)
);

-- ── EuroFib exports ─────────────────────────────────────────────

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

-- ── PDF notes (stacked: client / contract / anexa) ──────────────

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
