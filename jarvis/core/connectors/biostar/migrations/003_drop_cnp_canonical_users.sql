-- Migration: 003_drop_cnp_canonical_users.sql
-- Created:   2026-04-22
-- Purpose:   CNP normalization — make users.cnp the single canonical source.
--
--   1. Backfill users.cnp from mapped Sincron employees (153 rows missing).
--   2. Drop biostar_employees.cnp (always NULL for all 337 rows).
--
-- After this migration:
--   - CNP lives ONLY in users.cnp (populated by Sincron sync)
--   - BioStar employees get CNP via JOIN: biostar_employees → users.cnp
--   - sincron_employees.cnp kept as raw API import cache for unmapped matching

-- Step 1: Backfill users.cnp from Sincron where missing.
-- Skip CNPs that already exist on another user (prevents unique violation).
UPDATE users u
SET cnp = sub.cnp,
    updated_at = NOW()
FROM (
    SELECT DISTINCT ON (se.mapped_jarvis_user_id)
           se.mapped_jarvis_user_id AS uid,
           TRIM(se.cnp) AS cnp
    FROM sincron_employees se
    WHERE se.mapped_jarvis_user_id IS NOT NULL
      AND se.is_active = TRUE
      AND se.cnp IS NOT NULL
      AND TRIM(se.cnp) != ''
      AND REPLACE(se.cnp, 'x', '') != ''
      -- Only pick CNPs not already assigned to another user
      AND NOT EXISTS (
          SELECT 1 FROM users u2
          WHERE TRIM(u2.cnp) = TRIM(se.cnp)
            AND u2.id != se.mapped_jarvis_user_id
      )
    ORDER BY se.mapped_jarvis_user_id, se.mapping_confidence DESC NULLS LAST
) sub
WHERE u.id = sub.uid
  AND (u.cnp IS NULL OR TRIM(u.cnp) = '');

-- Step 2: Drop the unused cnp column and index from biostar_employees
DROP INDEX IF EXISTS idx_biostar_employees_cnp;
ALTER TABLE biostar_employees DROP COLUMN IF EXISTS cnp;

-- ROLLBACK (manual):
--   ALTER TABLE biostar_employees ADD COLUMN IF NOT EXISTS cnp VARCHAR(20);
--   CREATE INDEX IF NOT EXISTS idx_biostar_employees_cnp
--       ON biostar_employees(cnp) WHERE cnp IS NOT NULL;
