"""Holiday auto-populate task — ensures current year + next year are always in DB."""
import logging

logger = logging.getLogger('jarvis.tasks.holidays')


def populate_holidays():
    """Ensure public_holidays table has current year + next year data.

    Runs daily at 00:30. Idempotent — skips if already populated.
    """
    try:
        from datetime import date
        from core.utils.holidays_repository import HolidayRepository

        repo = HolidayRepository()
        current_year = date.today().year

        for yr in [current_year, current_year + 1]:
            repo.ensure_year_populated(yr)

        logger.info(f"Holiday population check complete for {current_year} and {current_year + 1}")
    except Exception as e:
        logger.error(f"Holiday population failed: {e}", exc_info=True)
