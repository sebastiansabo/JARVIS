"""Env-gated Shopify listing auto-push: re-push due + stale listings.

Disabled by default (ENABLE_LISTING_AUTOSYNC unset/false) — staging runs the
same scheduler as prod (see reference_staging_runs_prod_scheduler_real_emails),
so this must never fire against the real Shopify store unless explicitly
turned on in that environment's config.

Note on the `taxo_map` parameter name: it is kept for interface stability with
the schedule/tick plumbing, but it actually carries the full publish context
`ShopifyConnector.publish()` needs — `{'field_map', 'value_map', 'config'}` —
not the product-taxonomy dimension map (that's a separate, unrelated
TaxonomyMapRepository used only by the manual taxonomy-editor UI). See
`_taxo_map()` below.
"""
import logging
import os
from datetime import datetime, timezone, timedelta

from carpark.connectors.listing_freshness import compute_listing_freshness
from carpark.connectors.cadence import cadence_to_minutes
from carpark.connectors.shopify.service import build_shopify_connector
from carpark.connectors.shopify.routes import _pub_repo, _get_single_account, _config
from carpark.connectors.shopify.schema_repository import SchemaRepository
from carpark.repositories.listing_schedule_repository import ListingScheduleRepository
from carpark.repositories.vehicle_repository import VehicleRepository
from carpark.repositories.photo_repository import PhotoRepository

logger = logging.getLogger('jarvis.carpark.listing_autosync')

PLATFORM_TYPE = 'shopify'


def autosync_enabled() -> bool:
    return os.environ.get('ENABLE_LISTING_AUTOSYNC', '').lower() == 'true'


def _taxo_map() -> dict:
    """Build the publish context (field_map/value_map/config) for the single
    configured Shopify account. Returns {} if no account is configured (the
    caller already checked build_shopify_connector() before reaching here, so
    this should normally succeed)."""
    account = _get_single_account()
    if not account:
        return {}
    schema_repo = SchemaRepository()
    return {
        'field_map': schema_repo.get_active_field_map(),
        'value_map': schema_repo.get_value_map(),
        'config': _config(account),
    }


def resync_shopify_vehicle(connector, pub_repo, photo_repo, taxo_map, vehicle, now) -> str:
    listing = pub_repo.get_listing_by_vehicle_platform(vehicle['id'], connector.platform_id)
    fresh = compute_listing_freshness(listing, vehicle.get('updated_at'), now)
    if fresh != 'stale':
        return f'skipped ({fresh})'
    photos = photo_repo.get_by_vehicle(vehicle['id'])
    ctx = taxo_map or {}
    result = connector.publish(vehicle, photos, ctx.get('field_map'), ctx.get('value_map'), ctx.get('config'))
    return 'pushed' if result.get('success') else f"error: {result.get('error')}"


def listing_autosync_tick() -> None:
    if not autosync_enabled():
        return
    now = datetime.now(timezone.utc)
    srepo = ListingScheduleRepository()
    due = srepo.list_due(PLATFORM_TYPE, now)
    if not due:
        return
    connector = build_shopify_connector()
    if not connector:
        logger.warning('listing_autosync: no Shopify account configured; %d due skipped', len(due))
        return
    ctx = _taxo_map()
    vrepo, prepo = VehicleRepository(), PhotoRepository()
    for sch in due:
        try:
            vehicle = vrepo.get_by_id(sch['vehicle_id'])
            if not vehicle:
                srepo.mark_run(sch['id'], None, 'skipped (no vehicle)')
                continue
            result = resync_shopify_vehicle(connector, _pub_repo, prepo, ctx, vehicle, now)
            mins = cadence_to_minutes(sch['cadence'])
            nxt = now + timedelta(minutes=mins) if mins else None
            srepo.mark_run(sch['id'], nxt, result)
        except Exception as e:
            logger.exception('listing_autosync failed for schedule %s', sch.get('id'))
            srepo.mark_run(sch['id'], now + timedelta(hours=4), f'error: {e}')
