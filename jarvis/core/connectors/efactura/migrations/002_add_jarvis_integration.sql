-- e-Factura Connector - JARVIS Integration
-- Migration: 002_add_jarvis_integration.sql
-- Created: 2026-01-26
-- Description: Add columns for JARVIS Invoice Module integration

-- Add column to track when invoice has been sent to JARVIS Invoice Module
ALTER TABLE efactura_invoices
ADD COLUMN IF NOT EXISTS jarvis_invoice_id INTEGER;

-- Add column to store XML content directly
ALTER TABLE efactura_invoices
ADD COLUMN IF NOT EXISTS xml_content TEXT;

-- Add index for finding unallocated invoices
CREATE INDEX IF NOT EXISTS idx_efactura_invoices_unallocated
    ON efactura_invoices(jarvis_invoice_id) WHERE jarvis_invoice_id IS NULL;

-- Add comment for documentation
COMMENT ON COLUMN efactura_invoices.jarvis_invoice_id IS 'Reference to main invoices table when sent to Invoice Module (NULL = unallocated)';
COMMENT ON COLUMN efactura_invoices.xml_content IS 'Full e-Factura XML content stored for PDF generation';
