"""HR schema: hr.events, hr.event_bonuses, hr.bonus_types."""
import psycopg2
import psycopg2.errors


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
        END $$
    ''')

    # HR indexes (hr.employees table removed - using users table now)
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hr_events_dates ON hr.events(start_date, end_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hr_bonuses_employee ON hr.event_bonuses(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hr_bonuses_event ON hr.event_bonuses(event_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hr_bonuses_year_month ON hr.event_bonuses(year, month)')
    conn.commit()

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
