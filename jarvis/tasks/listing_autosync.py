"""Env-gated listing auto-push: re-push due + stale listings, for BOTH
platforms (Shopify and Autovit — Task 5 generalized the originally
Shopify-only sweep to also cover Autovit).

Disabled by default (ENABLE_LISTING_AUTOSYNC unset/false) — staging runs the
same scheduler as prod (see reference_staging_runs_prod_scheduler_real_emails),
so this must never fire against the real Shopify store / Autovit account
unless explicitly turned on in that environment's config.

Note on the `taxo_map` parameter name (Shopify only): it is kept for
interface stability with the schedule/tick plumbing, but it actually carries
the full publish context `ShopifyConnector.publish()` needs — `{'field_map',
'value_map', 'config'}` — not the product-taxonomy dimension map (that's a
separate, unrelated TaxonomyMapRepository used only by the manual
taxonomy-editor UI). See `_taxo_map()` below. The Autovit side's
`taxonomy_map` parameter (e.g. on `resync_autovit_vehicle`) is the REAL
CarPark -> Autovit dimension map (`AutovitTaxonomyRepository.get_map()`) —
same name, different shape; don't confuse the two.

Autovit account scope: unlike Shopify's config-driven single account,
Autovit is multi-account in principle, but this auto-sweep is scoped to the
PRIMARY account only (first row from `ConnectorRepository.get_all_by_type
('autovit')`) — a deliberate scope decision, not an oversight, mirroring the
Shopify single-account pattern (`_get_single_account`).
"""
import logging
import os
import threading
from datetime import datetime, timezone, timedelta

from carpark.connectors.listing_freshness import compute_listing_freshness
from carpark.connectors.cadence import cadence_to_minutes
from carpark.connectors.shopify.service import build_shopify_connector
from carpark.connectors.shopify.routes import _pub_repo, _get_single_account, _config, _parse_json
from carpark.connectors.shopify.schema_repository import SchemaRepository
from carpark.connectors.autovit.freshness import autovit_sweep_stale, compute_autovit_freshness
from carpark.connectors.autovit.service import republish_vehicle
from carpark.connectors.autovit.taxonomy_repository import AutovitTaxonomyRepository
from carpark.repositories.listing_schedule_repository import ListingScheduleRepository
from carpark.repositories.vehicle_repository import VehicleRepository
from carpark.repositories.photo_repository import PhotoRepository
from carpark.repositories.vehicle_photo_repository import VehiclePhotoRepository
from carpark.repositories.autovit_listing_repository import AutovitListingRepository
from core.connectors.repositories.connector_repository import ConnectorRepository

logger = logging.getLogger('jarvis.carpark.listing_autosync')

PLATFORM_TYPE = 'shopify'
AUTOVIT_PLATFORM_TYPE = 'autovit'


def _env_gate() -> bool:
    """Platform-level gate: env var only. Controls whether the autosync job is
    even registered/reachable in this environment (see cleanup._register_listing_autosync,
    which must stay env-only so the job is scheduled whenever this is on)."""
    return os.environ.get('ENABLE_LISTING_AUTOSYNC', '').lower() == 'true'


def _config_autosync_enabled() -> bool:
    """Runtime kill switch: the Shopify connector's config flag, DB-backed so it can
    be flipped without a redeploy. Fails CLOSED (False) on any error — this drives a
    push to the live storefront, so a config/DB read failure must skip the tick
    rather than risk an unintended marketplace sync; a missing flag on a healthy read
    still defaults on (True), and the skipped tick simply retries on the next run."""
    try:
        account = _get_single_account()
        if not account:
            return True
        cfg = _parse_json(account, 'config')
        return cfg.get('autosync_enabled', True)
    except Exception:
        logger.exception('_config_autosync_enabled: failed to read connector config; failing closed')
        return False


def autosync_enabled() -> bool:
    return _env_gate() and _config_autosync_enabled()


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


def resync_autovit_vehicle(account: dict, vehicle: dict, taxonomy_map: dict, now) -> str:
    """Autovit counterpart of `resync_shopify_vehicle`. Freshness is decided
    by `autovit_sweep_stale` (active/unpaid + stale by last_published_at —
    Task 2); when not stale, `compute_autovit_freshness` supplies the human
    reason for the 'skipped (<reason>)' result (not_published/up_to_date/
    inactive/expired/moderation/error/draft).

    The actual push goes through `republish_vehicle` (Task 4) — the SAME
    required-dimension 422 guard a manual publish gets: an unmapped REQUIRED
    taxonomy dimension (make/model/body_type/fuel_type/color) is reported as
    'skipped: unmapped <dim>' WITHOUT ever calling Autovit. A 'missing'
    (assembled-but-invalid advert) result is reported the same defensive way
    rather than falling through to an uninformative 'error: None'.
    """
    listing = AutovitListingRepository().get(vehicle['id'], account['id'])
    if not autovit_sweep_stale(listing, vehicle.get('updated_at'), now):
        reason = compute_autovit_freshness(listing, vehicle.get('updated_at'), now)
        return f'skipped ({reason})'
    photos = VehiclePhotoRepository().urls(vehicle['id'])
    res = republish_vehicle(account, vehicle, photos, taxonomy_map, now=now)
    if res.get('success'):
        return 'pushed'
    if res.get('unmapped_required'):
        return 'skipped: unmapped ' + ', '.join(res['unmapped_required'])
    if res.get('missing'):
        return 'skipped: missing ' + ', '.join(res['missing'])
    return f"error: {res.get('error')}"


def _instant_resync_worker(vehicle_id: int) -> None:
    try:
        connector = build_shopify_connector()
        if not connector:
            return
        vehicle = VehicleRepository().get_by_id(vehicle_id)
        if not vehicle:
            return
        resync_shopify_vehicle(connector, _pub_repo, PhotoRepository(),
                               _taxo_map(), vehicle, datetime.now(timezone.utc))
    except Exception:
        logger.exception('instant resync failed for vehicle %s', vehicle_id)


def maybe_instant_resync(vehicle_id: int) -> None:
    if not autosync_enabled():
        return
    sch = ListingScheduleRepository().get(vehicle_id, 'shopify')
    if not sch or not sch.get('enabled') or sch.get('cadence') != 'instant':
        return
    threading.Thread(target=_instant_resync_worker, args=(vehicle_id,), daemon=True).start()


def listing_autosync_tick() -> None:
    """Shared env/config gate, then one due-processing pass per platform —
    Shopify (unchanged logic) followed by Autovit (Task 5). Each pass is
    independent: an empty/unavailable Shopify side never blocks the Autovit
    pass and vice versa, and a missing account on either side degrades to
    marking its own due rows 'skipped (...)' rather than raising."""
    if not autosync_enabled():
        return
    now = datetime.now(timezone.utc)
    srepo = ListingScheduleRepository()

    due = srepo.list_due(PLATFORM_TYPE, now)
    if due:
        connector = build_shopify_connector()
        if not connector:
            logger.warning('listing_autosync: no Shopify account configured; %d due skipped', len(due))
        else:
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

    due_av = srepo.list_due(AUTOVIT_PLATFORM_TYPE, now)
    if due_av:
        accounts = ConnectorRepository().get_all_by_type(AUTOVIT_PLATFORM_TYPE)
        account = accounts[0] if accounts else None
        if not account:
            logger.warning('listing_autosync: no Autovit account configured; %d due skipped', len(due_av))
            for sch in due_av:
                srepo.mark_run(sch['id'], now + timedelta(hours=4), 'skipped (no account)')
        else:
            tmap = AutovitTaxonomyRepository().get_map()
            vrepo_av = VehicleRepository()
            for sch in due_av:
                try:
                    vehicle = vrepo_av.get_by_id(sch['vehicle_id'])
                    if not vehicle:
                        srepo.mark_run(sch['id'], None, 'skipped (no vehicle)')
                        continue
                    result = resync_autovit_vehicle(account, vehicle, tmap, now)
                    mins = cadence_to_minutes(sch['cadence'])
                    nxt = now + timedelta(minutes=mins) if mins else None
                    srepo.mark_run(sch['id'], nxt, result)
                except Exception as e:
                    logger.exception('listing_autosync (autovit) failed for schedule %s', sch.get('id'))
                    srepo.mark_run(sch['id'], now + timedelta(hours=4), f'error: {e}')
