-- Migration: Performance indexes for frequently-queried columns
-- Date: 2026-04-13
-- Run on: staging first, then production after verification

-- ============================================================
-- users table — used in every permission check, HR scope filter
-- ============================================================

-- Composite index for company + department scope filtering (hits on nearly every HR query)
CREATE INDEX IF NOT EXISTS idx_users_company_dept
    ON users (company, department)
    WHERE is_active = TRUE;

-- company_id for L0 hierarchy queries
CREATE INDEX IF NOT EXISTS idx_users_company_id
    ON users (company_id)
    WHERE is_active = TRUE;

-- ============================================================
-- crm_deals — filtered in DealRepository.search()
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_crm_deals_contract_date
    ON crm_deals (contract_date DESC);

CREATE INDEX IF NOT EXISTS idx_crm_deals_brand
    ON crm_deals (brand);

CREATE INDEX IF NOT EXISTS idx_crm_deals_dossier_status
    ON crm_deals (dossier_status);

CREATE INDEX IF NOT EXISTS idx_crm_deals_sales_person
    ON crm_deals (sales_person);

CREATE INDEX IF NOT EXISTS idx_crm_deals_dealer_name
    ON crm_deals (dealer_name);

-- Composite for common filter combo: brand + status + date
CREATE INDEX IF NOT EXISTS idx_crm_deals_brand_status_date
    ON crm_deals (brand, dossier_status, contract_date DESC);

-- ============================================================
-- crm_clients — filtered in ClientRepository queries
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_crm_clients_is_blacklisted
    ON crm_clients (is_blacklisted);

CREATE INDEX IF NOT EXISTS idx_crm_clients_client_type
    ON crm_clients (client_type);

CREATE INDEX IF NOT EXISTS idx_crm_clients_company_id
    ON crm_clients (company_id);

-- ============================================================
-- invoices — frequent date/status range queries
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_invoices_invoice_date
    ON invoices (invoice_date DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_invoices_status
    ON invoices (status)
    WHERE deleted_at IS NULL;

-- ============================================================
-- structure_node_members — used in every org-hierarchy traversal
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_snm_user_role
    ON structure_node_members (user_id, role);

CREATE INDEX IF NOT EXISTS idx_snm_node_role
    ON structure_node_members (node_id, role);

-- ============================================================
-- company_responsables — used in L0 hierarchy checks
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_company_responsables_user_id
    ON company_responsables (user_id);
