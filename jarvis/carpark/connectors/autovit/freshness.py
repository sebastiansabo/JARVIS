# jarvis/carpark/connectors/autovit/freshness.py
"""Pure freshness classifier for an Autovit listing row (mirrors listing_freshness.py
for Shopify). No DB access — callers pass the listing dict, the vehicle's
`updated_at`, and an aware `now`.
"""
from datetime import datetime

from carpark.connectors.listing_freshness import _aware

_INACTIVE_STATUSES = ('removed_by_user', 'removed_by_moderator', 'disabled', 'inactive')


def compute_autovit_freshness(listing, vehicle_updated_at, now: datetime) -> str:
    if not listing or not listing.get('external_advert_id'):
        return 'not_published'
    status = (listing.get('status') or '').lower()
    if status == 'error':
        return 'error'
    if status in _INACTIVE_STATUSES:
        return 'inactive'
    if status == 'expired':
        return 'expired'
    if status == 'moderation':
        return 'moderation'
    if status == 'unpaid':
        return 'draft'
    if status == 'active':
        last_published_at = _aware(listing.get('last_published_at'))
        updated_at = _aware(vehicle_updated_at)
        if last_published_at is None or (updated_at and updated_at > last_published_at):
            return 'stale'
        return 'up_to_date'
    return 'not_published'


def autovit_sweep_stale(listing, vehicle_updated_at, now: datetime) -> bool:
    if not listing:
        return False
    status = (listing.get('status') or '').lower()
    if status not in ('active', 'unpaid'):
        return False
    last_published_at = _aware(listing.get('last_published_at'))
    updated_at = _aware(vehicle_updated_at)
    return last_published_at is None or bool(updated_at and updated_at > last_published_at)
