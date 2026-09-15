# jarvis/carpark/connectors/listing_freshness.py
"""Pure freshness classifier for a vehicle listing row (platform-agnostic)."""
from datetime import datetime


def compute_listing_freshness(listing, vehicle_updated_at, now: datetime) -> str:
    if not listing or not listing.get('external_listing_id'):
        return 'not_published'
    status = (listing.get('status') or '').lower()
    if status == 'error':
        return 'error'
    if status in ('archived', 'inactive'):
        return 'inactive'
    expires_at = listing.get('expires_at')
    if expires_at and expires_at < now:
        return 'expired'
    if status == 'published':
        last_sync = listing.get('last_sync')
        if last_sync is None or (vehicle_updated_at and vehicle_updated_at > last_sync):
            return 'stale'
        return 'up_to_date'
    return status or 'not_published'
