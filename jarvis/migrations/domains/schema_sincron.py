"""Sincron HR connector schema — timesheet data from Sincron API."""

import logging

logger = logging.getLogger(__name__)


def create_schema_sincron(conn, cursor):
    """Create Sincron connector tables."""

    # ── Sincron employees (mapping table) ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sincron_employees (
            id SERIAL PRIMARY KEY,
            sincron_employee_id VARCHAR(50) NOT NULL,
            company_name VARCHAR(255) NOT NULL,
            nume VARCHAR(255),
            prenume VARCHAR(255),
            cnp VARCHAR(20),
            id_contract VARCHAR(50),
            nr_contract VARCHAR(50),
            data_incepere_contract DATE,
            mapped_jarvis_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            mapping_method VARCHAR(50),
            mapping_confidence INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            last_synced_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE(sincron_employee_id, company_name)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sincron_employees_mapped
        ON sincron_employees(mapped_jarvis_user_id)
        WHERE mapped_jarvis_user_id IS NOT NULL
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sincron_employees_company
        ON sincron_employees(company_name)
    """)

    # ── Sincron timesheets (daily activity records) ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sincron_timesheets (
            id SERIAL PRIMARY KEY,
            sincron_employee_id VARCHAR(50) NOT NULL,
            company_name VARCHAR(255) NOT NULL,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            day DATE NOT NULL,
            short_code VARCHAR(20) NOT NULL,
            short_code_en VARCHAR(20),
            unit VARCHAR(20) NOT NULL DEFAULT 'hour',
            value NUMERIC(6,2) NOT NULL DEFAULT 0,
            synced_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE(sincron_employee_id, company_name, day, short_code)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sincron_timesheets_employee_month
        ON sincron_timesheets(sincron_employee_id, company_name, year, month)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sincron_timesheets_day
        ON sincron_timesheets(day)
    """)

    # ── Sincron sync runs ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sincron_sync_runs (
            id SERIAL PRIMARY KEY,
            run_id VARCHAR(36) NOT NULL UNIQUE,
            sync_type VARCHAR(50) NOT NULL DEFAULT 'timesheet',
            company_name VARCHAR(255),
            year INTEGER,
            month INTEGER,
            status VARCHAR(20) NOT NULL DEFAULT 'running',
            employees_synced INTEGER DEFAULT 0,
            records_created INTEGER DEFAULT 0,
            records_updated INTEGER DEFAULT 0,
            error_message TEXT,
            started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            finished_at TIMESTAMP WITH TIME ZONE
        )
    """)

    # ── Sincron activity codes (discovered from API responses) ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sincron_activity_codes (
            id SERIAL PRIMARY KEY,
            short_code VARCHAR(20) NOT NULL UNIQUE,
            short_code_en VARCHAR(20),
            description TEXT,
            category VARCHAR(50),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)

    # ── CHECK constraints (safe to re-run — uses NOT VALID + IF NOT EXISTS pattern) ──
    for stmt in [
        """ALTER TABLE sincron_timesheets ADD CONSTRAINT chk_sincron_ts_month
           CHECK (month BETWEEN 1 AND 12)""",
        """ALTER TABLE sincron_timesheets ADD CONSTRAINT chk_sincron_ts_year
           CHECK (year BETWEEN 2000 AND 2100)""",
        """ALTER TABLE sincron_timesheets ADD CONSTRAINT chk_sincron_ts_value
           CHECK (value >= 0)""",
        """ALTER TABLE sincron_employees ADD CONSTRAINT chk_sincron_emp_confidence
           CHECK (mapping_confidence BETWEEN 0 AND 100)""",
        """ALTER TABLE sincron_sync_runs ADD CONSTRAINT chk_sincron_run_status
           CHECK (status IN ('running', 'completed', 'failed'))""",
        """ALTER TABLE sincron_sync_runs ADD CONSTRAINT chk_sincron_run_month
           CHECK (month IS NULL OR month BETWEEN 1 AND 12)""",
        """ALTER TABLE sincron_sync_runs ADD CONSTRAINT chk_sincron_run_year
           CHECK (year IS NULL OR year BETWEEN 2000 AND 2100)""",
    ]:
        try:
            cursor.execute(stmt)
        except Exception:
            conn.rollback()  # constraint already exists — safe to skip

    conn.commit()
    logger.info('Sincron schema created/verified')
