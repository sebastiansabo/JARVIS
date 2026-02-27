-- BioStar 2 Connector Tables
-- Migration: 001_create_biostar_tables.sql
-- Created: 2026-02-27
-- Description: Schema for BioStar 2 access control / T&A integration

-- ============================================================
-- Table: biostar_employees
-- Description: Cached BioStar user data with JARVIS user mapping
-- ============================================================

CREATE TABLE IF NOT EXISTS biostar_employees (
    id SERIAL PRIMARY KEY,
    biostar_user_id VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    phone VARCHAR(50),

    -- BioStar organizational data
    user_group_id VARCHAR(50),
    user_group_name VARCHAR(255),

    -- Access card data
    card_ids JSONB DEFAULT '[]'::JSONB,

    -- JARVIS user mapping
    mapped_jarvis_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    mapping_method VARCHAR(20),  -- auto_name, auto_email, manual
    mapping_confidence NUMERIC(5,2),

    -- Work schedule
    lunch_break_minutes INTEGER NOT NULL DEFAULT 60,
    working_hours NUMERIC(4,1) NOT NULL DEFAULT 8.0,
    schedule_start TIME NOT NULL DEFAULT '08:00',
    schedule_end TIME NOT NULL DEFAULT '17:00',

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'active',

    -- Timestamps
    last_synced_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_biostar_employees_name ON biostar_employees(name);
CREATE INDEX IF NOT EXISTS idx_biostar_employees_mapped ON biostar_employees(mapped_jarvis_user_id);
CREATE INDEX IF NOT EXISTS idx_biostar_employees_group ON biostar_employees(user_group_name);
CREATE INDEX IF NOT EXISTS idx_biostar_employees_status ON biostar_employees(status);


-- ============================================================
-- Table: biostar_punch_logs
-- Description: Punch / access events from BioStar
-- ============================================================

CREATE TABLE IF NOT EXISTS biostar_punch_logs (
    id SERIAL PRIMARY KEY,
    biostar_event_id VARCHAR(100) NOT NULL,
    biostar_user_id VARCHAR(50) NOT NULL,

    -- Event details
    event_datetime TIMESTAMP NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    direction VARCHAR(10),  -- IN, OUT

    -- Device info
    device_id VARCHAR(50),
    device_name VARCHAR(255),
    door_id VARCHAR(50),
    door_name VARCHAR(255),

    -- Verification method
    auth_type VARCHAR(50),

    -- Raw event data
    raw_data JSONB DEFAULT '{}'::JSONB,

    -- Timestamps
    synced_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_biostar_punch_dedup
    ON biostar_punch_logs(biostar_event_id);
CREATE INDEX IF NOT EXISTS idx_biostar_punch_user ON biostar_punch_logs(biostar_user_id);
CREATE INDEX IF NOT EXISTS idx_biostar_punch_datetime ON biostar_punch_logs(event_datetime);
CREATE INDEX IF NOT EXISTS idx_biostar_punch_direction ON biostar_punch_logs(direction);


-- ============================================================
-- Table: biostar_sync_runs
-- Description: Sync run tracking
-- ============================================================

CREATE TABLE IF NOT EXISTS biostar_sync_runs (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL UNIQUE,
    sync_type VARCHAR(20) NOT NULL,  -- users, events, full

    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMP,

    success BOOLEAN DEFAULT FALSE,

    records_fetched INTEGER DEFAULT 0,
    records_created INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    records_skipped INTEGER DEFAULT 0,
    errors_count INTEGER DEFAULT 0,

    cursor_before TIMESTAMP,
    cursor_after TIMESTAMP,

    error_summary TEXT
);

CREATE INDEX IF NOT EXISTS idx_biostar_sync_runs_started ON biostar_sync_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_biostar_sync_runs_type ON biostar_sync_runs(sync_type);


-- ============================================================
-- Table: biostar_sync_errors
-- Description: Error tracking during sync
-- ============================================================

CREATE TABLE IF NOT EXISTS biostar_sync_errors (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL,
    error_type VARCHAR(20) NOT NULL,  -- AUTH, NETWORK, API, PARSE, MAPPING
    error_code VARCHAR(50),
    error_message TEXT NOT NULL,
    biostar_user_id VARCHAR(50),
    is_retryable BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_biostar_sync_errors_run ON biostar_sync_errors(run_id);


-- ============================================================
-- Table: biostar_daily_adjustments
-- Description: Adjusted (official) daily punch-in / punch-out records
-- ============================================================

CREATE TABLE IF NOT EXISTS biostar_daily_adjustments (
    id SERIAL PRIMARY KEY,
    biostar_user_id VARCHAR(50) NOT NULL,
    date DATE NOT NULL,

    -- Original raw punches
    original_first_punch TIMESTAMP,
    original_last_punch TIMESTAMP,
    original_duration_seconds NUMERIC,

    -- Adjusted (official) punches
    adjusted_first_punch TIMESTAMP,
    adjusted_last_punch TIMESTAMP,
    adjusted_duration_seconds NUMERIC,

    -- Schedule at time of adjustment
    schedule_start TIME,
    schedule_end TIME,
    lunch_break_minutes INTEGER,
    working_hours NUMERIC(4,1),

    -- Deviation info
    deviation_minutes_in INTEGER,   -- + = late, - = early
    deviation_minutes_out INTEGER,  -- + = overtime, - = left early

    -- Meta
    adjustment_type VARCHAR(20) NOT NULL DEFAULT 'manual',  -- manual, auto
    adjusted_by INTEGER REFERENCES users(id),
    notes TEXT,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE(biostar_user_id, date)
);

CREATE INDEX IF NOT EXISTS idx_biostar_adj_user ON biostar_daily_adjustments(biostar_user_id);
CREATE INDEX IF NOT EXISTS idx_biostar_adj_date ON biostar_daily_adjustments(date);
CREATE INDEX IF NOT EXISTS idx_biostar_adj_type ON biostar_daily_adjustments(adjustment_type);


-- ============================================================
-- ROLLBACK
-- ============================================================
-- DROP TABLE IF EXISTS biostar_sync_errors;
-- DROP TABLE IF EXISTS biostar_sync_runs;
-- DROP TABLE IF EXISTS biostar_punch_logs;
-- DROP TABLE IF EXISTS biostar_employees;
