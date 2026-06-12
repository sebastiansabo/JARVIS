-- Migration 002: Refactor invoice storage — cod_comanda → contract_ref + anexa_ref
-- Each Anexa within a Contract has its own independent lifecycle.
-- Each line has its own nr_comanda (order number per vehicle).
-- Date: 2026-06-11

-- Drop old tables (cascade handles links/lines)
DROP TABLE IF EXISTS facturare_eurofib_exports CASCADE;
DROP TABLE IF EXISTS facturare_invoice_links CASCADE;
DROP TABLE IF EXISTS facturare_invoice_lines CASCADE;
DROP TABLE IF EXISTS facturare_invoices CASCADE;

-- ── facturare_invoices (lifecycle grouped by contract_ref + anexa_ref) ───

CREATE TABLE facturare_invoices (
    id              SERIAL PRIMARY KEY,
    contract_ref    VARCHAR(100) NOT NULL,
    anexa_ref       VARCHAR(100) NOT NULL,
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

    CONSTRAINT ck_invoice_number_range CHECK (invoice_number IS NULL OR (invoice_number >= 1 AND invoice_number <= 9999999))
);

-- Partial unique indexes: PROFORMA/STORNO/FINAL are 1-per-anexa, ADVANCE allows 1..3
CREATE UNIQUE INDEX uq_anexa_proforma ON facturare_invoices(contract_ref, anexa_ref) WHERE invoice_type = 'PROFORMA';
CREATE UNIQUE INDEX uq_anexa_storno   ON facturare_invoices(contract_ref, anexa_ref) WHERE invoice_type = 'STORNO';
CREATE UNIQUE INDEX uq_anexa_final    ON facturare_invoices(contract_ref, anexa_ref) WHERE invoice_type = 'FINAL';

CREATE INDEX idx_fi_contract_anexa ON facturare_invoices(contract_ref, anexa_ref);
CREATE INDEX idx_fi_type           ON facturare_invoices(invoice_type);
CREATE INDEX idx_fi_state          ON facturare_invoices(invoice_state);
CREATE INDEX idx_fi_customer       ON facturare_invoices(customer_id);
CREATE INDEX idx_fi_supplier       ON facturare_invoices(supplier_id);

-- ── facturare_invoice_lines (each line = one vehicle with its own nr_comanda) ─

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

-- ── facturare_invoice_links (state transitions) ─────────────────

CREATE TABLE facturare_invoice_links (
    id                  SERIAL PRIMARY KEY,
    source_invoice_id   INTEGER NOT NULL REFERENCES facturare_invoices(id) ON DELETE CASCADE,
    target_invoice_id   INTEGER NOT NULL REFERENCES facturare_invoices(id) ON DELETE CASCADE,
    link_type           invoice_link_type_enum NOT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_no_self_link CHECK (source_invoice_id != target_invoice_id),
    CONSTRAINT uq_invoice_link UNIQUE (source_invoice_id, target_invoice_id, link_type)
);

CREATE INDEX idx_fil_source ON facturare_invoice_links(source_invoice_id);
CREATE INDEX idx_fil_target ON facturare_invoice_links(target_invoice_id);

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
