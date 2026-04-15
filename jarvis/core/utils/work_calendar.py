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
                    Useful for current-month calculations.

    Returns:
        int: Number of working days
    """
    _holiday_repo.ensure_year_populated(year)
    holidays = _holiday_repo.get_holidays_for_month(year, month)
    holiday_dates = set()
    for h in holidays:
        d = h['date']
        if isinstance(d, str):
            d = date.fromisoformat(d)
        holiday_dates.add(d)

    first = date(year, month, 1)
    if month == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)

    if up_to_date and up_to_date < last:
        last = up_to_date

    count = 0
    d = first
    while d <= last:
        if d.weekday() < 5 and d not in holiday_dates:
            count += 1
        d += timedelta(days=1)
    return count
