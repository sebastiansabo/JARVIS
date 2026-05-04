"""Repository for public_holidays table queries."""
from core.base_repository import BaseRepository


class HolidayRepository(BaseRepository):

    def get_holidays_for_year(self, year: int):
        """Return all holidays for a year as list of dicts."""
        return self.query_all(
            'SELECT date, name, holiday_type FROM public_holidays WHERE year = %s ORDER BY date',
            (year,)
        )

    def get_holidays_for_month(self, year: int, month: int):
        """Return holidays in a specific month as list of dicts."""
        return self.query_all('''
            SELECT date, name, holiday_type FROM public_holidays
            WHERE year = %s AND EXTRACT(MONTH FROM date) = %s
            ORDER BY date
        ''', (year, month))

    def is_holiday(self, check_date) -> bool:
        """Check if a specific date is a holiday."""
        row = self.query_one(
            'SELECT 1 FROM public_holidays WHERE date = %s', (check_date,)
        )
        return row is not None

    def ensure_year_populated(self, year: int):
        """Ensure holidays for a year exist in the DB. Idempotent."""
        row = self.query_one(
            'SELECT COUNT(*) AS cnt FROM public_holidays WHERE year = %s', (year,)
        )
        if row and int(row['cnt']) > 0:
            return

        from core.utils.holidays import get_all_holidays
        holidays = get_all_holidays(year)
        for dt, name, htype in holidays:
            self.execute(
                """INSERT INTO public_holidays (date, name, year, holiday_type)
                   VALUES (%s, %s, %s, %s) ON CONFLICT (date, name) DO NOTHING""",
                (dt, name, year, htype)
            )
