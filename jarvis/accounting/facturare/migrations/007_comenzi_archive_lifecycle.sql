-- Migration 007: delayed auto-archive lifecycle for anexas + contracts.
-- Applied MANUALLY via psql per DB (localhost -> staging -> prod). Idempotent.
-- Date: 2026-08-17

-- Anexa archive lifecycle
ALTER TABLE facturare_anexas    ADD COLUMN IF NOT EXISTS archive_after TIMESTAMP;
ALTER TABLE facturare_anexas    ADD COLUMN IF NOT EXISTS archived_at   TIMESTAMP;
-- Defensive: these were added by ad-hoc DDL historically and appear in no migration.
ALTER TABLE facturare_anexas    ADD COLUMN IF NOT EXISTS archived      BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE facturare_anexas    ADD COLUMN IF NOT EXISTS status        VARCHAR(20) NOT NULL DEFAULT 'NEW';
ALTER TABLE facturare_invoices  ADD COLUMN IF NOT EXISTS archived      BOOLEAN NOT NULL DEFAULT FALSE;

-- Contract archive lifecycle (entirely new)
ALTER TABLE facturare_contracts ADD COLUMN IF NOT EXISTS archived      BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE facturare_contracts ADD COLUMN IF NOT EXISTS archive_after TIMESTAMP;
ALTER TABLE facturare_contracts ADD COLUMN IF NOT EXISTS archived_at   TIMESTAMP;

-- Scheduler lookup indexes (partial: only rows with a pending deadline)
CREATE INDEX IF NOT EXISTS idx_fa_archive_after ON facturare_anexas(archive_after)    WHERE archive_after IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_fc_archive_after ON facturare_contracts(archive_after) WHERE archive_after IS NOT NULL;
