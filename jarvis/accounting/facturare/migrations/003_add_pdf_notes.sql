-- Migration 003: Add configurable PDF notes per level (client / contract / anexa)
-- Notes stack: client + contract + anexa all appear on generated PDFs.
-- Date: 2026-06-11

CREATE TABLE IF NOT EXISTS facturare_pdf_notes (
    id           SERIAL PRIMARY KEY,
    level        VARCHAR(20) NOT NULL CHECK (level IN ('client', 'contract', 'anexa')),
    customer_id  INTEGER REFERENCES crm_clients(id),
    contract_ref VARCHAR(100),
    anexa_ref    VARCHAR(100),
    note_text    TEXT NOT NULL DEFAULT '',
    updated_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by   INTEGER REFERENCES users(id)
);

-- One note per unique level+key
CREATE UNIQUE INDEX uq_pdfnote_client   ON facturare_pdf_notes(customer_id)                         WHERE level = 'client';
CREATE UNIQUE INDEX uq_pdfnote_contract ON facturare_pdf_notes(customer_id, contract_ref)           WHERE level = 'contract';
CREATE UNIQUE INDEX uq_pdfnote_anexa    ON facturare_pdf_notes(customer_id, contract_ref, anexa_ref) WHERE level = 'anexa';

CREATE INDEX idx_pdfnotes_customer ON facturare_pdf_notes(customer_id);
