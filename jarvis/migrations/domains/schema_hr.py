"""HR schema: hr.events, hr.event_bonuses, hr.bonus_types."""
import psycopg2
import psycopg2.errors


def create_event_bonus_days(conn, cursor):
    """Granular presence-day storage for event bonuses + the per-day money view.

    ``hr.event_bonus_days`` holds one row per attended *full* day and is the
    source of truth, replacing the continuous participation_start..participation_end
    window (which is kept, derived as MIN/MAX of the days, for back-compat). The
    view ``hr.v_event_bonus_days`` expands each day with its pro-rata share of the
    bonus money (uniform per-day rate = bonus_net / bonus_days) so month-scoped
    reads can report a boundary-spanning bonus under every month it touches.
    Idempotent.
    """
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hr.event_bonus_days (
            id SERIAL PRIMARY KEY,
            bonus_id INTEGER NOT NULL REFERENCES hr.event_bonuses(id) ON DELETE CASCADE,
            day DATE NOT NULL,
            UNIQUE (bonus_id, day)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hr_bonus_days_bonus ON hr.event_bonus_days(bonus_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hr_bonus_days_day ON hr.event_bonus_days(day)')
    # Optional per-day worked interval (whole hours). NULL = no interval set for
    # that day; a participant's "Event Hours" = SUM(end_hour - start_hour). This
    # is independent of hours_free (the Time-Bank perk). Idempotent.
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_schema = 'hr' AND table_name = 'event_bonus_days'
                          AND column_name = 'start_hour') THEN
                ALTER TABLE hr.event_bonus_days ADD COLUMN start_hour SMALLINT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_schema = 'hr' AND table_name = 'event_bonus_days'
                          AND column_name = 'end_hour') THEN
                ALTER TABLE hr.event_bonus_days ADD COLUMN end_hour SMALLINT;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints
                          WHERE table_schema = 'hr' AND table_name = 'event_bonus_days'
                          AND constraint_name = 'event_bonus_days_hours_chk') THEN
                ALTER TABLE hr.event_bonus_days ADD CONSTRAINT event_bonus_days_hours_chk CHECK (
                    (start_hour IS NULL OR (start_hour >= 0 AND start_hour <= 24))
                    AND (end_hour IS NULL OR (end_hour >= 0 AND end_hour <= 24))
                    AND (start_hour IS NULL OR end_hour IS NULL OR end_hour > start_hour)
                );
            END IF;
        END $$
    ''')
    cursor.execute('''
        CREATE OR REPLACE VIEW hr.v_event_bonus_days AS
        SELECT
            d.bonus_id,
            d.day,
            EXTRACT(YEAR  FROM d.day)::int AS year,
            EXTRACT(MONTH FROM d.day)::int AS month,
            eb.user_id,
            eb.event_id,
            eb.bonus_type_id,
            (eb.bonus_net / NULLIF(eb.bonus_days, 0)) AS day_net,
            eb.hours_free,
            -- hours_free is NOT split by month (credited once); attribute it to
            -- the bonus's earliest day so month rollups count it exactly once.
            (d.day = MIN(d.day) OVER (PARTITION BY d.bonus_id)) AS is_primary_day,
            -- Worked hours for THIS day (whole hours); unlike hours_free these are
            -- inherently per-day, so month rollups sum them directly.
            COALESCE(d.end_hour - d.start_hour, 0) AS day_event_hours
        FROM hr.event_bonus_days d
        JOIN hr.event_bonuses eb ON eb.id = d.bonus_id
    ''')
    conn.commit()


def backfill_event_bonus_days(conn, cursor):
    """Materialise day rows for legacy bonuses that have a participation window
    but no day rows yet: round(bonus_days) consecutive days from
    participation_start, never past participation_end. Idempotent (skips bonuses
    that already have days; ON CONFLICT DO NOTHING).
    """
    cursor.execute('''
        INSERT INTO hr.event_bonus_days (bonus_id, day)
        SELECT eb.id, gs::date
        FROM hr.event_bonuses eb
        CROSS JOIN LATERAL (
            SELECT GREATEST(1, LEAST(
                COALESCE(ROUND(eb.bonus_days)::int,
                         (eb.participation_end - eb.participation_start + 1)),
                (eb.participation_end - eb.participation_start + 1)
            )) AS d_count
        ) c
        CROSS JOIN LATERAL generate_series(
            eb.participation_start::timestamp,
            eb.participation_start::timestamp + ((c.d_count - 1) || ' days')::interval,
            interval '1 day'
        ) AS gs
        WHERE eb.participation_start IS NOT NULL
          AND eb.participation_end IS NOT NULL
          AND eb.participation_end >= eb.participation_start
          AND NOT EXISTS (
              SELECT 1 FROM hr.event_bonus_days d WHERE d.bonus_id = eb.id
          )
        ON CONFLICT (bonus_id, day) DO NOTHING
    ''')
    conn.commit()


def create_schema_hr(conn, cursor):
    """Create HR module tables."""
    # ============== HR Module Schema ==============
    # Create separate schema for HR data isolation
    cursor.execute('CREATE SCHEMA IF NOT EXISTS hr')
    conn.commit()

    # NOTE: hr.employees table has been migrated to public.users table
    # All employee data is now stored in the users table with organizational fields
    # (company, brand, department, subdepartment, notify_on_allocation)

    # HR Events table - event definitions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hr.events (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            company TEXT,
            brand TEXT,
            description TEXT,
            created_by INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # HR Event Bonuses table - individual bonus records
    # NOTE: user_id references public.users(id) (consolidated from hr.employees)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hr.event_bonuses (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
            event_id INTEGER NOT NULL REFERENCES hr.events(id) ON DELETE CASCADE,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            participation_start DATE,
            participation_end DATE,
            bonus_days NUMERIC(3,1),
            hours_free INTEGER,
            bonus_net NUMERIC(10,2),
            details TEXT,
            allocation_month TEXT,
            bonus_type_id INTEGER,
            created_by INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # HR Bonus Types table - configurable bonus rates
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hr.bonus_types (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            amount NUMERIC(10,2) NOT NULL,
            days_per_amount NUMERIC(5,2) DEFAULT 1,
            description TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Add bonus_type_id column if not exists (migration for existing databases)
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_schema = 'hr' AND table_name = 'event_bonuses'
                          AND column_name = 'bonus_type_id') THEN
                ALTER TABLE hr.event_bonuses ADD COLUMN bonus_type_id INTEGER;
            END IF;
        END $$
    ''')

    # Migration: Rename amount_per_day to amount and add days_per_amount (for existing databases)
    cursor.execute('''
        DO $$
        BEGIN
            -- Rename amount_per_day to amount if old column exists
            IF EXISTS (SELECT 1 FROM information_schema.columns
                      WHERE table_schema = 'hr' AND table_name = 'bonus_types'
                      AND column_name = 'amount_per_day') THEN
                ALTER TABLE hr.bonus_types RENAME COLUMN amount_per_day TO amount;
            END IF;
            -- Add days_per_amount column if not exists
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_schema = 'hr' AND table_name = 'bonus_types'
                          AND column_name = 'days_per_amount') THEN
                ALTER TABLE hr.bonus_types ADD COLUMN days_per_amount NUMERIC(5,2) DEFAULT 1;
            END IF;
            -- Add restricted_to_user_id column if not exists
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_schema = 'hr' AND table_name = 'bonus_types'
                          AND column_name = 'restricted_to_user_id') THEN
                ALTER TABLE hr.bonus_types ADD COLUMN restricted_to_user_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL;
            END IF;
        END $$
    ''')

    # HR indexes (hr.employees table removed - using users table now)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hr_events_dates ON hr.events(start_date, end_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hr_bonuses_employee ON hr.event_bonuses(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hr_bonuses_event ON hr.event_bonuses(event_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hr_bonuses_year_month ON hr.event_bonuses(year, month)')
    conn.commit()

    # Granular presence days: per-day storage + money view, then one-time backfill
    # of legacy bonuses from their participation window.
    create_event_bonus_days(conn, cursor)
    backfill_event_bonus_days(conn, cursor)

    # Migrate existing single reinvoice data to new table (if not already migrated)
    cursor.execute('''
        INSERT INTO reinvoice_destinations (allocation_id, company, brand, department, subdepartment, percentage, value)
        SELECT id, reinvoice_to, reinvoice_brand, reinvoice_department, reinvoice_subdepartment, 100.0, allocation_value
        FROM allocations
        WHERE reinvoice_to IS NOT NULL AND reinvoice_to != ''
        AND NOT EXISTS (
            SELECT 1 FROM reinvoice_destinations rd WHERE rd.allocation_id = allocations.id
        )
    ''')
    conn.commit()

    # Migration: Fix invoices with subtract_vat=true but vat_rate=null
    # Calculate the implied VAT rate from invoice_value and net_value, then match to closest standard rate
    cursor.execute('''
        SELECT id, invoice_value, net_value
        FROM invoices
        WHERE subtract_vat = true AND vat_rate IS NULL AND net_value IS NOT NULL AND net_value > 0
    ''')
    invoices_to_fix = cursor.fetchall()

    if invoices_to_fix:
        # Get available VAT rates
        cursor.execute('SELECT rate FROM vat_rates WHERE is_active = true ORDER BY rate DESC')
        available_rates = [row['rate'] for row in cursor.fetchall()]

        for inv in invoices_to_fix:
            # Calculate implied VAT rate: vat_rate = (invoice_value / net_value - 1) * 100
            implied_rate = (inv['invoice_value'] / inv['net_value'] - 1) * 100

            # Find closest matching rate
            closest_rate = min(available_rates, key=lambda r: abs(r - implied_rate))

            # Update invoice with matched rate
            cursor.execute('UPDATE invoices SET vat_rate = %s WHERE id = %s', (closest_rate, inv['id']))

        conn.commit()
