"""Romanian public holidays schema — pre-computed holiday dates."""
import logging

logger = logging.getLogger(__name__)


def create_schema_holidays(conn, cursor):
    """Create public_holidays table and populate current + next year."""

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS public_holidays (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL,
            name VARCHAR(100) NOT NULL,
            year INTEGER NOT NULL,
            holiday_type VARCHAR(20) NOT NULL DEFAULT 'fixed',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE(date, name)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_public_holidays_date
        ON public_holidays(date)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_public_holidays_year
        ON public_holidays(year)
    """)

    conn.commit()

    # Auto-populate current year + next year if empty
    from core.utils.holidays import get_all_holidays
    from datetime import date

    current_year = date.today().year
    for yr in [current_year, current_year + 1]:
        cursor.execute("SELECT COUNT(*) AS cnt FROM public_holidays WHERE year = %s", (yr,))
        row = cursor.fetchone()
        count = row['cnt'] if isinstance(row, dict) else row[0]
        if count == 0:
            holidays = get_all_holidays(yr)
            for dt, name, htype in holidays:
                cursor.execute("""
                    INSERT INTO public_holidays (date, name, year, holiday_type)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (date, name) DO NOTHING
                """, (dt, name, yr, htype))
            logger.info(f"Populated {len(holidays)} holidays for {yr}")

    conn.commit()
    logger.info('Public holidays schema created/verified')
