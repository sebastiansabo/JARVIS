-- BioStar 2 Connector: Fix Event Dedup Key
-- Migration: 002_fix_event_dedup_key.sql
-- Created: 2026-03-09
-- Description: BioStar recycles event IDs when its log rotates.
--   The old unique index on biostar_event_id alone causes new events
--   to collide with old events that had the same ID months ago.
--   Fix: use composite (biostar_event_id, event_datetime::date) so
--   the same event ID on different days is allowed.

-- Drop the old unique index
DROP INDEX IF EXISTS idx_biostar_punch_dedup;

-- Create new composite unique index
CREATE UNIQUE INDEX IF NOT EXISTS idx_biostar_punch_dedup
    ON biostar_punch_logs(biostar_event_id, (event_datetime::date));

-- ============================================================
-- ROLLBACK
-- ============================================================
-- DROP INDEX IF EXISTS idx_biostar_punch_dedup;
-- CREATE UNIQUE INDEX IF NOT EXISTS idx_biostar_punch_dedup
--     ON biostar_punch_logs(biostar_event_id);
