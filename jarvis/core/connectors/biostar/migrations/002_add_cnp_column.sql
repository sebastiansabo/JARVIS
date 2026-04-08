-- Migration: 002_add_cnp_column.sql
-- Created:   2026-04-08
-- Purpose:   Add nullable CNP column to biostar_employees so the unified
--            employee mapping service can perform CNP-based matching.
--            BioStar 2 users don't carry CNP out of the box; when a BioStar
--            custom user field is configured (BIOSTAR_CNP_CUSTOM_FIELD), the
--            sync will populate this column.
--
-- Safety:    Fully idempotent and additive. Existing rows, queries, and
--            consumers continue to work with cnp = NULL.

ALTER TABLE biostar_employees
    ADD COLUMN IF NOT EXISTS cnp VARCHAR(20);

CREATE INDEX IF NOT EXISTS idx_biostar_employees_cnp
    ON biostar_employees(cnp)
    WHERE cnp IS NOT NULL;

-- ROLLBACK (manual):
--   DROP INDEX IF EXISTS idx_biostar_employees_cnp;
--   ALTER TABLE biostar_employees DROP COLUMN IF EXISTS cnp;
