-- Migration 006: EuroFib venituri rules for FINAL invoices + text templates
-- Date: 2026-06-26
-- Description: Add facturare_venituri_rules table and text_template column for invoice configuration

-- ── Venituri rules table ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS facturare_venituri_rules (
    id              SERIAL PRIMARY KEY,
    supplier_id     INTEGER NOT NULL REFERENCES companies(id),
    comanda_prefix  VARCHAR(5) NOT NULL,
    konto_venituri  VARCHAR(20) NOT NULL,
    kostenstelle    VARCHAR(20) NOT NULL,
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by      INTEGER REFERENCES users(id),

    CONSTRAINT uq_venituri_supplier_prefix UNIQUE (supplier_id, comanda_prefix)
);

-- Seed: AW International (id=10)
INSERT INTO facturare_venituri_rules (supplier_id, comanda_prefix, konto_venituri, kostenstelle)
VALUES
    (10, '5', '707127', '0215'),   -- PKW
    (10, '3', '707128', '0216')    -- LNF
ON CONFLICT DO NOTHING;

-- Seed: AW Premium (id=11)
INSERT INTO facturare_venituri_rules (supplier_id, comanda_prefix, konto_venituri, kostenstelle)
VALUES
    (11, '*', '707132', '0314')    -- Audi (wildcard)
ON CONFLICT DO NOTHING;

-- ── Text template column on konto_config ──────────────────────────
ALTER TABLE facturare_konto_config
    ADD COLUMN IF NOT EXISTS text_template VARCHAR(100);

-- Seed text templates for existing rows
UPDATE facturare_konto_config SET text_template = 'avans {model} {comanda}'
    WHERE invoice_type = 'INVOICE' AND text_template IS NULL;
UPDATE facturare_konto_config SET text_template = 'storno avans {model} {comanda}'
    WHERE invoice_type = 'STORNO' AND text_template IS NULL;
UPDATE facturare_konto_config SET text_template = '{model} {comanda}'
    WHERE invoice_type = 'FINAL' AND text_template IS NULL;
