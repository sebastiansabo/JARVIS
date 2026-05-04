"""Work calendar utilities — working day calculations."""

from datetime import date, timedelta

from core.utils.holidays_repository import HolidayRepository

_holiday_repo = HolidayRepository()


def get_working_days(year, month, up_to_date=None):
    """Count weekdays in a month minus public holidays.

    Args:
        year: Calendar year
        month: Calendar month (1-12)
        up_to_date: If given, only count working days up to this date (inclusive).

    Returns:
        int: Number of working days
    """
    first = date(year, month, 1)
    if month == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)

    if up_to_date and up_to_date < last:
        last = up_to_date

    return get_working_days_range(first, last)


def get_working_days_range(start_date, end_date):
    """Count weekdays minus public holidays in an arbitrary date range.

    Args:
        start_date: First day (inclusive)
        end_date: Last day (inclusive)

    Returns:
        int: Number of working days
    """
    if start_date > end_date:
        return 0

    # Collect holidays for all months in the range
    holiday_dates = set()
    cursor = date(start_date.year, start_date.month, 1)
    end_month = date(end_date.year, end_date.month, 1)
    while cursor <= end_month:
        _holiday_repo.ensure_year_populated(cursor.year)
        holidays = _holiday_repo.get_holidays_for_month(cursor.year, cursor.month)
        for h in holidays:
            d = h['date']
            if isinstance(d, str):
                d = date.fromisoformat(d)
            holiday_dates.add(d)
        # Next month
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)

    count = 0
    d = start_date
    while d <= end_date:
        if d.weekday() < 5 and d not in holiday_dates:
            count += 1
        d += timedelta(days=1)
    return count
