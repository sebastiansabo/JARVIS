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
            is_leave BOOLEAN NOT NULL DEFAULT FALSE,
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

    # ── Add contract_status to sincron_employees (prep for future Sincron API status field) ──
    cursor.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name = 'sincron_employees' AND column_name = 'contract_status') THEN
                ALTER TABLE sincron_employees ADD COLUMN contract_status VARCHAR(20);
            END IF;
        END $$;
    """)

    # ── Schedule fields on sincron_employees (from Sincron API norma_lucru + program) ──
    for col_stmt in [
        "ALTER TABLE sincron_employees ADD COLUMN IF NOT EXISTS norma_lucru NUMERIC(4,1)",
        "ALTER TABLE sincron_employees ADD COLUMN IF NOT EXISTS norma_lucru_time VARCHAR(100)",
        "ALTER TABLE sincron_employees ADD COLUMN IF NOT EXISTS schedule_start TIME",
        "ALTER TABLE sincron_employees ADD COLUMN IF NOT EXISTS schedule_end TIME",
        "ALTER TABLE sincron_employees ADD COLUMN IF NOT EXISTS lunch_break_minutes INTEGER",
    ]:
        cursor.execute(col_stmt)

    # ── Per-activity schedule on sincron_timesheets (program.in / program.out / pauza_masa) ──
    for col_stmt in [
        "ALTER TABLE sincron_timesheets ADD COLUMN IF NOT EXISTS program_in TIME",
        "ALTER TABLE sincron_timesheets ADD COLUMN IF NOT EXISTS program_out TIME",
        "ALTER TABLE sincron_timesheets ADD COLUMN IF NOT EXISTS program_break INTEGER",
    ]:
        cursor.execute(col_stmt)

    # ── Schedule history — monthly snapshot per employee per company ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sincron_schedule_history (
            id SERIAL PRIMARY KEY,
            sincron_employee_id VARCHAR(50) NOT NULL,
            company_name VARCHAR(255) NOT NULL,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            norma_lucru NUMERIC(4,1),
            norma_lucru_time VARCHAR(100),
            schedule_start TIME,
            schedule_end TIME,
            lunch_break_minutes INTEGER,
            synced_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE(sincron_employee_id, company_name, year, month)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sincron_sched_hist_lookup
        ON sincron_schedule_history(sincron_employee_id, company_name, year, month)
    """)

    # ── CO balance — yearly snapshot imported from HR's Raport_concedii_contracte_lunar xlsx ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sincron_co_balance (
            id SERIAL PRIMARY KEY,
            year INTEGER NOT NULL,
            company_name VARCHAR(255) NOT NULL,
            cnp VARCHAR(20),
            nume VARCHAR(255),
            prenume VARCHAR(255),
            nr_contract VARCHAR(50),
            data_incepere_contract DATE,
            departament VARCHAR(255),
            carry_prev_year       INTEGER NOT NULL DEFAULT 0,
            carry_two_years_ago   INTEGER NOT NULL DEFAULT 0,
            annual_cim            INTEGER NOT NULL DEFAULT 0,
            seniority_bonus       INTEGER NOT NULL DEFAULT 0,
            manual_adjustment     INTEGER NOT NULL DEFAULT 0,
            total_available       INTEGER GENERATED ALWAYS AS (
                carry_prev_year + carry_two_years_ago
                + annual_cim + seniority_bonus + manual_adjustment
            ) STORED,
            mapped_jarvis_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            source_file           VARCHAR(255),
            imported_by           INTEGER REFERENCES users(id) ON DELETE SET NULL,
            imported_at           TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE(year, company_name, cnp)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sincron_co_balance_user_year
        ON sincron_co_balance(mapped_jarvis_user_id, year)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sincron_co_balance_year
        ON sincron_co_balance(year)
    """)

    try:
        cursor.execute("""
            ALTER TABLE sincron_co_balance ADD CONSTRAINT chk_sincron_co_year
            CHECK (year BETWEEN 2000 AND 2100)
        """)
    except Exception:
        conn.rollback()

    # ── CO balance import runs ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sincron_co_import_runs (
            id SERIAL PRIMARY KEY,
            run_id VARCHAR(36) NOT NULL UNIQUE,
            year INTEGER NOT NULL,
            source_file VARCHAR(255),
            status VARCHAR(20) NOT NULL DEFAULT 'running',
            rows_total INTEGER DEFAULT 0,
            rows_matched INTEGER DEFAULT 0,
            rows_unmatched INTEGER DEFAULT 0,
            companies TEXT,
            error_message TEXT,
            imported_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            finished_at TIMESTAMP WITH TIME ZONE
        )
    """)

    try:
        cursor.execute("""
            ALTER TABLE sincron_co_import_runs ADD CONSTRAINT chk_sincron_co_run_status
            CHECK (status IN ('running', 'completed', 'failed'))
        """)
    except Exception:
        conn.rollback()

    # ── count_for_leave toggle — exclude micro-contracts from leave analytics ──
    cursor.execute("""
        ALTER TABLE sincron_employees
        ADD COLUMN IF NOT EXISTS count_for_leave BOOLEAN DEFAULT TRUE
    """)

    # ── company_id FK — map Sincron company_name to JARVIS companies table ──
    cursor.execute("""
        ALTER TABLE sincron_employees
        ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)
    """)
    cursor.execute("""
        UPDATE sincron_employees se
        SET company_id = c.id
        FROM companies c
        WHERE se.company_id IS NULL
          AND UPPER(se.company_name) = UPPER(c.company)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sincron_employees_company_id
        ON sincron_employees(company_id)
        WHERE company_id IS NOT NULL
    """)

    conn.commit()
    logger.info('Sincron schema created/verified')
