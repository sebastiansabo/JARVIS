-- e-Factura Connector - Company ID Integration
-- Migration: 003_add_company_id.sql
-- Created: 2026-01-26
-- Description: Add company_id to link efactura_invoices to JARVIS companies table

-- Add column to link invoice to JARVIS company
ALTER TABLE efactura_invoices
ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id);

-- Add index for filtering by company
CREATE INDEX IF NOT EXISTS idx_efactura_invoices_company
    ON efactura_invoices(company_id);

-- Add comment for documentation
COMMENT ON COLUMN efactura_invoices.company_id IS 'Reference to companies table - auto-identified by matching cif_owner against companies.vat';
