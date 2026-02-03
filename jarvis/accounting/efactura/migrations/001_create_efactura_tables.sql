-- e-Factura Connector Tables
-- Migration: 001_create_efactura_tables.sql
-- Created: 2025-01-26
-- Description: Initial schema for RO e-Factura integration

-- ============================================================
-- Table: efactura_company_connections
-- Description: Companies registered for e-Factura sync
-- ============================================================

CREATE TABLE IF NOT EXISTS efactura_company_connections (
    id SERIAL PRIMARY KEY,
    cif VARCHAR(20) NOT NULL UNIQUE,  -- Company tax ID (without RO prefix)
    display_name VARCHAR(255) NOT NULL,
    environment VARCHAR(20) NOT NULL DEFAULT 'test',  -- test, production

    -- Sync state
    last_sync_at TIMESTAMP,
    last_received_cursor VARCHAR(100),  -- Pagination cursor for received messages
    last_sent_cursor VARCHAR(100),      -- Pagination cursor for sent messages

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- active, paused, error, cert_expired
    status_message TEXT,

    -- Configuration (JSON)
    config JSONB DEFAULT '{}'::JSONB,

    -- Certificate metadata (NOT the actual cert - stored in vault)
    cert_fingerprint VARCHAR(64),  -- SHA256 fingerprint
    cert_expires_at TIMESTAMP,

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for company connections
CREATE INDEX IF NOT EXISTS idx_efactura_connections_status
    ON efactura_company_connections(status);
CREATE INDEX IF NOT EXISTS idx_efactura_connections_last_sync
    ON efactura_company_connections(last_sync_at);


-- ============================================================
-- Table: efactura_invoices
-- Description: Invoice records from e-Factura
-- ============================================================

CREATE TABLE IF NOT EXISTS efactura_invoices (
    id SERIAL PRIMARY KEY,

    -- Ownership
    cif_owner VARCHAR(20) NOT NULL,  -- Company that owns this record
    direction VARCHAR(20) NOT NULL,   -- received, sent

    -- Partner info
    partner_cif VARCHAR(20) NOT NULL,
    partner_name VARCHAR(500),

    -- Invoice details
    invoice_number VARCHAR(100) NOT NULL,
    invoice_series VARCHAR(50),
    issue_date DATE,
    due_date DATE,

    -- Amounts (stored as NUMERIC for precision)
    total_amount NUMERIC(15, 2) NOT NULL DEFAULT 0,
    total_vat NUMERIC(15, 2) NOT NULL DEFAULT 0,
    total_without_vat NUMERIC(15, 2) NOT NULL DEFAULT 0,
    currency VARCHAR(3) NOT NULL DEFAULT 'RON',

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'processed',

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for invoices
CREATE INDEX IF NOT EXISTS idx_efactura_invoices_owner_direction
    ON efactura_invoices(cif_owner, direction);
CREATE INDEX IF NOT EXISTS idx_efactura_invoices_issue_date
    ON efactura_invoices(issue_date);
CREATE INDEX IF NOT EXISTS idx_efactura_invoices_partner
    ON efactura_invoices(partner_cif);
CREATE INDEX IF NOT EXISTS idx_efactura_invoices_status
    ON efactura_invoices(status);
CREATE INDEX IF NOT EXISTS idx_efactura_invoices_created
    ON efactura_invoices(created_at);


-- ============================================================
-- Table: efactura_invoice_refs
-- Description: External references from ANAF
-- ============================================================

CREATE TABLE IF NOT EXISTS efactura_invoice_refs (
    id SERIAL PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES efactura_invoices(id) ON DELETE CASCADE,

    -- ANAF identifiers
    external_system VARCHAR(20) NOT NULL DEFAULT 'anaf',
    message_id VARCHAR(100) NOT NULL,  -- ID mesaj from ANAF
    upload_id VARCHAR(100),            -- ID incarcare
    download_id VARCHAR(100),          -- ID descarcare

    -- Integrity verification
    xml_hash VARCHAR(64),              -- SHA256 of invoice XML
    signature_hash VARCHAR(64),         -- Hash of signature
    raw_response_hash VARCHAR(64),      -- Hash of ANAF response

    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Unique constraint for deduplication
CREATE UNIQUE INDEX IF NOT EXISTS idx_efactura_refs_dedup
    ON efactura_invoice_refs(message_id, external_system);

-- Index for lookups
CREATE INDEX IF NOT EXISTS idx_efactura_refs_invoice
    ON efactura_invoice_refs(invoice_id);


-- ============================================================
-- Table: efactura_invoice_artifacts
-- Description: Stored file artifacts (ZIP, XML, PDF, etc.)
-- ============================================================

CREATE TABLE IF NOT EXISTS efactura_invoice_artifacts (
    id SERIAL PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES efactura_invoices(id) ON DELETE CASCADE,

    artifact_type VARCHAR(20) NOT NULL,  -- zip, xml, pdf, signature, response
    storage_uri TEXT NOT NULL,            -- Path in storage system

    -- File metadata
    original_filename VARCHAR(255),
    mime_type VARCHAR(100),
    checksum VARCHAR(64),                 -- SHA256
    size_bytes INTEGER DEFAULT 0,

    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Unique constraint for artifact type per invoice
CREATE UNIQUE INDEX IF NOT EXISTS idx_efactura_artifacts_unique
    ON efactura_invoice_artifacts(invoice_id, artifact_type);

-- Index for lookups
CREATE INDEX IF NOT EXISTS idx_efactura_artifacts_invoice
    ON efactura_invoice_artifacts(invoice_id);


-- ============================================================
-- Table: efactura_sync_runs
-- Description: Synchronization run tracking
-- ============================================================

CREATE TABLE IF NOT EXISTS efactura_sync_runs (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL UNIQUE,  -- UUID
    company_cif VARCHAR(20) NOT NULL,

    -- Timing
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMP,

    -- Results
    success BOOLEAN DEFAULT FALSE,
    direction VARCHAR(20),  -- received, sent, both

    -- Counters
    messages_checked INTEGER DEFAULT 0,
    invoices_fetched INTEGER DEFAULT 0,
    invoices_created INTEGER DEFAULT 0,
    invoices_updated INTEGER DEFAULT 0,
    invoices_skipped INTEGER DEFAULT 0,
    errors_count INTEGER DEFAULT 0,

    -- Cursor tracking
    cursor_before VARCHAR(100),
    cursor_after VARCHAR(100),

    -- Summary
    error_summary TEXT
);

-- Indexes for sync runs
CREATE INDEX IF NOT EXISTS idx_efactura_sync_runs_cif
    ON efactura_sync_runs(company_cif);
CREATE INDEX IF NOT EXISTS idx_efactura_sync_runs_started
    ON efactura_sync_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_efactura_sync_runs_success
    ON efactura_sync_runs(success);


-- ============================================================
-- Table: efactura_sync_errors
-- Description: Error tracking during synchronization
-- ============================================================

CREATE TABLE IF NOT EXISTS efactura_sync_errors (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL,  -- FK to sync_runs (by run_id)

    -- Error context
    message_id VARCHAR(100),      -- Related ANAF message ID
    invoice_ref VARCHAR(100),     -- Invoice number if known

    -- Error details
    error_type VARCHAR(20) NOT NULL,  -- AUTH, NETWORK, VALIDATION, API, PARSE
    error_code VARCHAR(50),
    error_message TEXT NOT NULL,

    -- Debug info (hashed, never raw payloads)
    request_hash VARCHAR(64),
    response_hash VARCHAR(64),
    stack_trace TEXT,

    -- Retryability
    is_retryable BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for sync errors
CREATE INDEX IF NOT EXISTS idx_efactura_sync_errors_run
    ON efactura_sync_errors(run_id);
CREATE INDEX IF NOT EXISTS idx_efactura_sync_errors_type
    ON efactura_sync_errors(error_type);
CREATE INDEX IF NOT EXISTS idx_efactura_sync_errors_created
    ON efactura_sync_errors(created_at);


-- ============================================================
-- ROLLBACK SCRIPT (if needed)
-- ============================================================
-- DROP TABLE IF EXISTS efactura_sync_errors;
-- DROP TABLE IF EXISTS efactura_sync_runs;
-- DROP TABLE IF EXISTS efactura_invoice_artifacts;
-- DROP TABLE IF EXISTS efactura_invoice_refs;
-- DROP TABLE IF EXISTS efactura_invoices;
-- DROP TABLE IF EXISTS efactura_company_connections;
