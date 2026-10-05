# jarvis/carpark/connectors/listing_freshness.py
"""Pure freshness classifier for a vehicle listing row (platform-agnostic)."""
from datetime import datetime, timezone


def _aware(dt):
    """Coerce a datetime (or ISO string) to tz-aware UTC.

    DB columns (carpark_vehicles.updated_at, carpark_vehicle_listings.expires_at/
    last_sync) should be TIMESTAMP → naive datetime, but in prod the listings
    columns can come back as ISO STRINGS (the column drifted to TEXT and
    PublishingService wrote datetime.isoformat() values). `dt.tzinfo` then raised
    AttributeError, 500-ing GET /shopify/api/vehicles/<id>/status after a publish.
    Parse strings here (naive → UTC), and treat an unparseable string as unknown
    (None) rather than crashing. The caller passes an aware `now`; normalize both
    sides to aware UTC before comparing.
    """
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except ValueError:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def compute_listing_freshness(listing, vehicle_updated_at, now: datetime) -> str:
    if not listing or not listing.get('external_listing_id'):
        return 'not_published'
    status = (listing.get('status') or '').lower()
    if status == 'error':
        return 'error'
    if status in ('archived', 'inactive'):
        return 'inactive'
    now = _aware(now)
    expires_at = _aware(listing.get('expires_at'))
    if expires_at and expires_at < now:
        return 'expired'
    if status == 'published':
        last_sync = _aware(listing.get('last_sync'))
        vehicle_updated_at = _aware(vehicle_updated_at)
        if last_sync is None or (vehicle_updated_at and vehicle_updated_at > last_sync):
            return 'stale'
        return 'up_to_date'
    return 'not_published'
