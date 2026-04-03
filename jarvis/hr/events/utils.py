"""HR Events Utility Functions — Bonus Lock System."""
from datetime import date
from typing import Optional, Tuple

# Default lock day (can be overridden via Settings)
DEFAULT_LOCK_DAY = 5


def get_lock_day() -> int:
    """
    Get the configured lock day from database settings.
    Falls back to DEFAULT_LOCK_DAY if not configured.
    Returns 0 when locking is disabled.
    """
    try:
        from core.notifications.repositories import NotificationRepository
        settings = NotificationRepository().get_settings()
        lock_day = settings.get('hr_bonus_lock_day')
        if lock_day is not None:
            return int(lock_day)
    except Exception:
        pass
    return DEFAULT_LOCK_DAY


def get_bonus_lock_deadline(year: int, month: int) -> Optional[date]:
    """
    Get the deadline date for a bonus month.
    Returns None when lock_day is 0 (locking disabled).
    """
    lock_day = get_lock_day()
    if lock_day <= 0:
        return None
    if month == 12:
        return date(year + 1, 1, lock_day)
    return date(year, month + 1, lock_day)


def is_bonus_month_locked(year: int, month: int) -> bool:
    """
    Check if a bonus month is locked (past the edit deadline).
    Returns False when locking is disabled (lock_day = 0).
    """
    deadline = get_bonus_lock_deadline(year, month)
    if deadline is None:
        return False
    return date.today() > deadline


def get_lock_status(year: int, month: int) -> dict:
    """
    Get comprehensive lock status information for a bonus month.
    """
    deadline = get_bonus_lock_deadline(year, month)

    if deadline is None:
        return {
            'locked': False,
            'deadline': None,
            'deadline_display': '—',
            'days_remaining': None,
            'message': 'Locking disabled',
        }

    today = date.today()
    days_remaining = (deadline - today).days
    locked = today > deadline

    if locked:
        message = f"Locked since {deadline.strftime('%d.%m.%Y')}"
    elif days_remaining == 0:
        message = "Last day to edit! Locks at midnight."
    elif days_remaining == 1:
        message = "1 day remaining"
    else:
        message = f"{days_remaining} days remaining"

    return {
        'locked': locked,
        'deadline': deadline.isoformat(),
        'deadline_display': deadline.strftime('%d.%m.%Y'),
        'days_remaining': days_remaining,
        'message': message
    }


def can_edit_bonus(year: int, month: int, user_role: str) -> Tuple[bool, str]:
    """
    Check if a user can edit a bonus for the given month.

    Admin users can always edit regardless of lock status.
    Other users can only edit if the month is not locked.
    Everyone can edit when locking is disabled (lock_day = 0).
    """
    if user_role == 'Admin':
        return True, "Admin override"

    if is_bonus_month_locked(year, month):
        deadline = get_bonus_lock_deadline(year, month)
        return False, f"Locked since {deadline.strftime('%d.%m.%Y')}"

    return True, "Within edit window"
