"""Scheduled cleanup for public test-drive bookings."""
from datetime import datetime, timezone
from marketing.services.td_booking_service import TdBookingService


def expire_stale_bookings() -> int:
    """Flip pending_confirm bookings past their expires_at to 'expired' (frees the slot)."""
    return TdBookingService().expire_pending_bookings(datetime.now(timezone.utc))
