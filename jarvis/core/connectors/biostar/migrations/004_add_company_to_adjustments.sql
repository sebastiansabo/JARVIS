-- Migration: 004_add_company_to_adjustments.sql
-- Created: 2026-05-07
-- Description: Add company_name to biostar_daily_adjustments for per-company interval adjustments.
--              Multi-contract employees (e.g. DEAC DIANA with 8 Sincron contracts) need separate
--              adjusted punch times per company interval.

-- Add nullable company_name column
ALTER TABLE biostar_daily_adjustments ADD COLUMN IF NOT EXISTS company_name VARCHAR(255);

-- Drop old unique constraint (inline UNIQUE creates auto-named constraint)
ALTER TABLE biostar_daily_adjustments
    DROP CONSTRAINT IF EXISTS biostar_daily_adjustments_biostar_user_id_date_key;

-- New unique constraint: one adjustment per (user, date, company)
-- NULL company_name = single-contract / legacy (backwards compatible)
CREATE UNIQUE INDEX IF NOT EXISTS idx_biostar_adj_user_date_company
    ON biostar_daily_adjustments(biostar_user_id, date, COALESCE(company_name, ''));

-- Index for company-based lookups
CREATE INDEX IF NOT EXISTS idx_biostar_adj_company ON biostar_daily_adjustments(company_name)
    WHERE company_name IS NOT NULL;

-- ============================================================
-- ROLLBACK
-- ============================================================
-- DROP INDEX IF EXISTS idx_biostar_adj_company;
-- DROP INDEX IF EXISTS idx_biostar_adj_user_date_company;
-- ALTER TABLE biostar_daily_adjustments ADD CONSTRAINT biostar_daily_adjustments_biostar_user_id_date_key UNIQUE(biostar_user_id, date);
-- ALTER TABLE biostar_daily_adjustments DROP COLUMN IF EXISTS company_name;
