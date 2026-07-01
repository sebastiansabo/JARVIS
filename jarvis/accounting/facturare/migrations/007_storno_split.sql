-- Migration 007: Add STORNO_SPLIT invoice type and SPLITS link type for per-car EuroFib export
-- Date: 2026-06-29
-- Description: Add STORNO_SPLIT to invoice_type_enum, SPLITS to invoice_link_type_enum, relax invoice_number to 9 digits

-- Add STORNO_SPLIT to invoice_type_enum
ALTER TYPE invoice_type_enum ADD VALUE IF NOT EXISTS 'STORNO_SPLIT';

-- Add SPLITS to invoice_link_type_enum
ALTER TYPE invoice_link_type_enum ADD VALUE IF NOT EXISTS 'SPLITS';

-- Relax invoice_number CHECK from 7 to 9 digits for split numbering
ALTER TABLE facturare_invoices DROP CONSTRAINT IF EXISTS ck_invoice_number_range;
ALTER TABLE facturare_invoices ADD CONSTRAINT ck_invoice_number_range
    CHECK (invoice_number IS NULL OR (invoice_number >= 1 AND invoice_number <= 999999999));
