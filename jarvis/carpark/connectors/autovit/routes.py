"""Autovit.ro connector API routes.

Endpoints for managing dealer account credentials, testing connections,
and retrieving advert data from Autovit.
"""
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from flask import request, jsonify
from flask_login import login_required, current_user

from . import autovit_bp
from . import taxonomy
from . import taxonomy_map
from . import taxonomy_sync
from .taxonomy_repository import AutovitTaxonomyRepository
from .client import AutovitClient, AutovitAuthError, PRODUCTION_URL, SANDBOX_URL
from .freshness import compute_autovit_freshness
from .service import republish_vehicle
from ..cadence import ensure_auto_schedule
from ..listing_status_hook import sync_listing_status as sync_listing_status_hook
from core.connectors.repositories.connector_repository import ConnectorRepository
from core.utils.api_helpers import api_login_required, admin_required
from carpark.repositories.vehicle_repository import VehicleRepository
from carpark.repositories.vehicle_photo_repository import VehiclePhotoRepository
from carpark.repositories.autovit_listing_repository import AutovitListingRepository
from carpark.services import reconcile_service
from carpark.routes.vehicles import (
    carpark_edit_required, carpark_required, _verify_vehicle_ownership, _serialize,
)

logger = logging.getLogger('jarvis.autovit.routes')

_repo = ConnectorRepository()
_vehicle_repo = VehicleRepository()
_photo_repo = VehiclePhotoRepository()
_listing_repo = AutovitListingRepository()
_taxonomy_repo = AutovitTaxonomyRepository()

CONNECTOR_TYPE = 'autovit'


def _parse_creds(connector: dict) -> dict:
    """Parse credentials from connector row."""
    creds = connector.get('credentials') or {}
    if isinstance(creds, str):
        try:
            creds = json.loads(creds)
        except (json.JSONDecodeError, TypeError):
            creds = {}
    return creds


def _parse_config(connector: dict) -> dict:
    """Parse config from connector row."""
    cfg = connector.get('config') or {}
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except (json.JSONDecodeError, TypeError):
            cfg = {}
    return cfg


def _safe_account(row: dict) -> dict:
    """Return account info with masked credentials."""
    creds = _parse_creds(row)
    cfg = _parse_config(row)
    return {
        'id': row['id'],
        'name': row.get('name', ''),
        'email': cfg.get('email', ''),
        'environment': cfg.get('environment', 'production'),
        'client_id': creds.get('client_id', ''),
        'status': row.get('status', 'disconnected'),
        'last_sync': row.get('last_sync'),
        'last_error': row.get('last_error'),
        'credential_fields': {
            'client_secret': '••••••' if creds.get('client_secret') else '',
            'password': '••••••' if creds.get('password') else '',
        },
    }


def _build_client(connector: dict) -> AutovitClient:
    """Build an AutovitClient from a connector row."""
    creds = _parse_creds(connector)
    cfg = _parse_config(connector)
    env = cfg.get('environment', 'production')
    base_url = PRODUCTION_URL if env == 'production' else SANDBOX_URL
    return AutovitClient(
        base_url=base_url,
        client_id=creds.get('client_id', ''),
        client_secret=creds.get('client_secret', ''),
        username=cfg.get('email', ''),
        password=creds.get('password', ''),
    )


# ── Account Management ──

@autovit_bp.route('/api/config', methods=['GET'])
@carpark_required
def get_accounts():
    """List all Autovit dealer accounts (credentials masked)."""
    rows = _repo.get_all_by_type(CONNECTOR_TYPE)
    return jsonify({'success': True, 'accounts': [_safe_account(r) for r in rows]})


@autovit_bp.route('/api/config/<int:account_id>', methods=['GET'])
@carpark_required
def get_account(account_id):
    """Get a single Autovit dealer account (credentials masked)."""
    connector = _repo.get(account_id)
    if not connector or connector.get('connector_type') != CONNECTOR_TYPE:
        return jsonify({'success': False, 'error': 'Account not found'}), 404
    return jsonify({'success': True, 'account': _safe_account(connector)})


@autovit_bp.route('/api/config', methods=['POST'])
@admin_required
def save_account():
    """Create or update an Autovit dealer account.

    SECURITY: @admin_required (can_access_settings) — mirrors the Shopify
    connector's save_account. Dealer-account config stores API credentials, so
    creating/updating one must not be reachable by a non-admin user.
    """
    data = request.get_json(silent=True) or {}

    email = data.get('email', '').strip()
    client_id = data.get('client_id', '').strip()
    client_secret = data.get('client_secret', '').strip()
    password = data.get('password', '').strip()
    environment = data.get('environment', 'production')
    account_id = data.get('id')  # if updating existing

    if not email or not client_id:
        return jsonify({'success': False, 'error': 'Email and Client ID are required'}), 400

    config = {'email': email, 'environment': environment}
    credentials = {'client_id': client_id}
    if client_secret:
        credentials['client_secret'] = client_secret
    if password:
        credentials['password'] = password

    if account_id:
        # Update existing
        connector = _repo.get(account_id)
        if not connector:
            return jsonify({'success': False, 'error': 'Account not found'}), 404
        # Merge credentials
        existing_creds = _parse_creds(connector)
        for k, v in credentials.items():
            if v:
                existing_creds[k] = v
        _repo.update(account_id, name=email, config=config, credentials=existing_creds)
        updated = _repo.get(account_id)
        return jsonify({'success': True, 'account': _safe_account(updated)})
    else:
        # Create new
        if not client_secret or not password:
            return jsonify({'success': False, 'error': 'Client Secret and Password are required for new accounts'}), 400
        cid = _repo.save(CONNECTOR_TYPE, email, status='disconnected',
                         config=config, credentials=credentials)
        created = _repo.get(cid)
        return jsonify({'success': True, 'account': _safe_account(created)}), 201


@autovit_bp.route('/api/config/<int:account_id>', methods=['DELETE'])
@admin_required
def delete_account(account_id):
    """Remove an Autovit dealer account. @admin_required — mirrors Shopify."""
    connector = _repo.get(account_id)
    if not connector or connector.get('connector_type') != CONNECTOR_TYPE:
        return jsonify({'success': False, 'error': 'Account not found'}), 404
    _repo.delete(account_id)
    return jsonify({'success': True})


# ── Connection Testing ──

@autovit_bp.route('/api/test-connection', methods=['POST'])
@admin_required
def test_connection():
    """Test connection for a specific account.

    @admin_required: uses the account's stored credentials, calls the external
    Autovit API and writes back the connection status — a connector-management
    action, gated with the same admin permission as save/delete.
    """
    data = request.get_json(silent=True) or {}
    account_id = data.get('account_id')

    if not account_id:
        return jsonify({'success': False, 'error': 'account_id is required'}), 400

    connector = _repo.get(account_id)
    if not connector or connector.get('connector_type') != CONNECTOR_TYPE:
        return jsonify({'success': False, 'error': 'Account not found'}), 404

    try:
        client = _build_client(connector)
        result = client.health_check()
        _repo.update(account_id, status='connected', last_error=None)
        return jsonify({'success': True, 'data': result})
    except AutovitAuthError as e:
        _repo.update(account_id, status='error', last_error=str(e))
        return jsonify({'success': False, 'error': f'Authentication failed: {e}'})
    except Exception as e:
        _repo.update(account_id, status='error', last_error=str(e))
        logger.exception('Autovit test-connection failed for account %s', account_id)
        return jsonify({'success': False, 'error': str(e)})


# ── Status ──

@autovit_bp.route('/api/status', methods=['GET'])
@carpark_required
def get_status():
    """Aggregate status across all Autovit accounts."""
    rows = _repo.get_all_by_type(CONNECTOR_TYPE)
    connected = sum(1 for r in rows if r.get('status') == 'connected')
    return jsonify({
        'success': True,
        'data': {
            'total_accounts': len(rows),
            'connected': connected,
            'has_accounts': len(rows) > 0,
        },
    })


@autovit_bp.route('/api/vehicles/<int:vehicle_id>/status', methods=['GET'])
@api_login_required
@carpark_required
def vehicle_autovit_status(vehicle_id):
    """Per-vehicle Autovit listing state (across accounts) for the Detail page.

    Previously carpark_autovit_listings was only readable in the DB — the editor
    published Autovit fire-and-forget with no visible status. This surfaces the
    stored external advert id/url, status (draft/unpaid/active/inactive/error) and
    last_error so the UI can show a chip mirroring the Shopify freshness one.

    SECURITY: gated by carpark_required (this exposes external advert URLs and
    error messages, so it must not be readable by non-CarPark users) plus the
    standard scoped ownership check (own + actable companies; Admin = any) —
    mirrors GET /vehicles/<id>.
    """
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err
    vehicle = _vehicle_repo.get_by_id(vehicle_id)
    now = datetime.now(timezone.utc)
    v_updated = vehicle.get('updated_at') if vehicle else None
    listings = []
    for l in _listing_repo.list_by_vehicle(vehicle_id):
        d = dict(l)
        d['freshness'] = compute_autovit_freshness(d, v_updated, now)
        listings.append(_serialize(d))
    return jsonify({'success': True, 'listings': listings})


@autovit_bp.route('/api/accounts/<int:account_id>/category-taxonomy', methods=['GET'])
@login_required
@carpark_required
def category_taxonomy(account_id):
    """Diagnostic: fetch the live Autovit cars-category parameter schema so param
    formats (e.g. date_registration) and derived fields (e.g. title) can be
    verified against what we send. Logs it (grep-able) and returns the JSON."""
    connector = _repo.get(account_id)
    if not connector or connector.get('connector_type') != CONNECTOR_TYPE:
        return jsonify({'success': False, 'error': 'Account not found'}), 404
    try:
        cat = _build_client(connector).get_category(taxonomy.CARS_CATEGORY_ID) or {}
    except Exception as e:
        logger.exception('Autovit category-taxonomy fetch failed')
        return jsonify({'success': False, 'error': str(e)}), 502
    logger.info('Autovit category %s taxonomy: %s',
                taxonomy.CARS_CATEGORY_ID, json.dumps(cat)[:4000])
    return jsonify({'success': True, 'category': cat})


@autovit_bp.route('/api/vehicles/<int:vehicle_id>/verify-status', methods=['POST'])
@login_required
@carpark_edit_required
def verify_vehicle_status(vehicle_id):
    """Refresh each stored Autovit listing's status from the LIVE advert.

    JARVIS publishes a draft (status 'unpaid'); once the user pays/activates the
    ad on Autovit.ro it goes 'active', but JARVIS never learned — the chip stayed
    'Draft (neplătit)'. This reads the live advert per listing and writes back its
    real status (upsert bumps last_sync), so the chip and its refresh date reflect
    reality. Powers the Detail 'Verifică status' button.
    """
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err
    refreshed = 0
    for listing in _listing_repo.list_by_vehicle(vehicle_id):
        ext_id = listing.get('external_advert_id')
        account_id = listing.get('account_id')
        if not (ext_id and account_id):
            continue
        connector = _repo.get(account_id)
        if not connector or connector.get('connector_type') != CONNECTOR_TYPE:
            continue
        try:
            # Bounded like the publish flow — a status refresh must not hang.
            # Cap client.timeout so the token fetch is bounded too (not just the read).
            client = _build_client(connector)
            client.timeout = 10
            live = client.get_account_advert(str(ext_id), timeout=10) or {}
        except Exception as e:
            logger.warning('Autovit verify-status read failed (vehicle %s advert %s): %s',
                           vehicle_id, ext_id, e)
            continue
        status = live.get('status')
        if status:
            _listing_repo.upsert(vehicle_id, account_id, status=status,
                                 external_url=live.get('url') or listing.get('external_url'),
                                 last_error=None)
            refreshed += 1
    vehicle = _vehicle_repo.get_by_id(vehicle_id)
    now = datetime.now(timezone.utc)
    v_updated = vehicle.get('updated_at') if vehicle else None
    listings = []
    for l in _listing_repo.list_by_vehicle(vehicle_id):
        d = dict(l)
        d['freshness'] = compute_autovit_freshness(d, v_updated, now)
        listings.append(_serialize(d))
    # Verify may have discovered an advert was removed/expired on Autovit, which
    # changes the live-channel count → reconcile the vehicle status (best-effort).
    sync_listing_status_hook(vehicle_id, changed_by=getattr(current_user, 'id', None))
    return jsonify({'success': True, 'refreshed': refreshed, 'listings': listings})


# ── Adverts (future) ──

@autovit_bp.route('/api/accounts/<int:account_id>/adverts', methods=['GET'])
@carpark_required
def get_adverts(account_id):
    """List adverts for a specific account."""
    connector = _repo.get(account_id)
    if not connector or connector.get('connector_type') != CONNECTOR_TYPE:
        return jsonify({'success': False, 'error': 'Account not found'}), 404

    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', 'active')

    try:
        client = _build_client(connector)
        data = client.get_adverts(page=page, status=status)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        logger.exception('Failed to fetch adverts for account %s', account_id)
        return jsonify({'success': False, 'error': str(e)})


# ── Photo Fallback (import-time only) ──

def _largest(size_map: dict) -> str:
    """Pick the largest-resolution URL from an Autovit photo size map keyed
    like {"2048x1360": url, "732x488": url} — max by width."""
    def w(k):
        try:
            return int(k.split("x")[0])
        except Exception:
            return 0
    return size_map[max(size_map, key=w)] if size_map else None


def _maybe_import_photos(client, advert, vehicle_id) -> int:
    """Seed carpark_vehicle_photos from the advert's photos, but only as a
    fallback when the vehicle has zero existing photos — never overwrites
    photos a user already curated in JARVIS. Stores the Autovit CDN URL
    directly (no download/re-hosting). Returns the number of photos added.
    """
    if _photo_repo.count(vehicle_id) > 0:
        return 0
    photos = advert.get("photos") or {}
    added = 0
    for idx, key in enumerate(sorted(photos, key=lambda k: int(k) if str(k).isdigit() else 0)):
        url = _largest(photos[key]) if isinstance(photos[key], dict) else photos[key]
        if not url:
            continue
        _photo_repo.add(vehicle_id, url=url, sort_order=idx, is_primary=(added == 0),
                        photo_type="autovit")
        added += 1
    return added


# ── Import Advert → Vehicle Catalog ──

@autovit_bp.route('/api/accounts/<int:account_id>/import-advert', methods=['POST'])
@login_required
@carpark_edit_required
def import_advert(account_id):
    """Import a single advert into the vehicle catalog.

    Upsert, "Autovit wins": if the VIN already exists in carpark_vehicles,
    UPDATE only the Autovit-owned columns (taxonomy.MERGE_FIELDS) — internal
    fields (acquisition_price, status, company_id, ...) are left untouched.
    Otherwise CREATE a new vehicle from the full mapped advert.
    """
    connector = _repo.get(account_id)
    if not connector or connector.get('connector_type') != CONNECTOR_TYPE:
        return jsonify({'success': False, 'error': 'Account not found'}), 404

    data = request.get_json(silent=True) or {}
    advert_id = data.get('advert_id')
    if not advert_id:
        return jsonify({'success': False, 'error': 'advert_id is required'}), 400

    try:
        client = _build_client(connector)
        advert = client.get_advert(str(advert_id))
    except Exception as e:
        logger.exception('Failed to fetch advert %s from account %s', advert_id, account_id)
        return jsonify({'success': False, 'error': f'Failed to fetch advert: {e}'}), 500

    vehicle_data = taxonomy.advert_to_vehicle(advert)
    if not vehicle_data.get("vin"):
        return jsonify({'success': False, 'error': 'Advert has no VIN — cannot import'}), 400
    if not vehicle_data.get("brand") or not vehicle_data.get("model"):
        return jsonify({'success': False, 'error': 'Advert missing make/model'}), 400

    try:
        existing = _vehicle_repo.get_by_vin(vehicle_data['vin'])
        uid = getattr(current_user, 'id', None)
        if existing:
            merged = {k: val for k, val in vehicle_data.items() if k in taxonomy.MERGE_FIELDS}
            _vehicle_repo.update(existing['id'], merged, updated_by=uid)
            vid, action = existing['id'], 'updated'
        else:
            if uid:
                vehicle_data['created_by'] = uid
                vehicle_data['updated_by'] = uid
            created = _vehicle_repo.create(vehicle_data)
            vid, action = created['id'], 'created'
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.exception('Failed to import advert %s into vehicle catalog', advert_id)
        return jsonify({'success': False, 'error': f'Failed to import advert: {e}'}), 500

    # Best-effort photo fallback: photos are a non-critical side effect, so a
    # photo failure must never turn an already-successful vehicle upsert into a
    # 500. Mirrors the codebase convention for best-effort side effects.
    try:
        photo_added = _maybe_import_photos(client, advert, vid)
    except Exception as e:
        logger.warning('Autovit photo import failed for vehicle %s: %s', vid, e)
        photo_added = 0

    return jsonify({'success': True, 'action': action, 'vehicle': {'id': vid},
                     'photo_added': photo_added}), 200


@autovit_bp.route('/api/accounts/<int:account_id>/import-all', methods=['POST'])
@login_required
@carpark_edit_required
def import_all(account_id):
    """Bulk-import every active advert for an account into the vehicle catalog.

    Paginates through client.get_adverts(status='active') until every page
    has been consumed, upserting each advert by VIN (same "Autovit wins"
    merge rules as import_advert). Fault-tolerant by design — progress is
    never lost:
      - A client-build failure returns 502 before any pagination.
      - A single-advert failure is recorded in `errors` and the batch
        continues to the next advert.
      - A page-fetch failure is recorded in `errors` and stops pagination,
        but the accumulated summary from prior pages is still returned (200).
    The sync-log status is 'success' when there were no errors, else
    'partial'.
    """
    connector = _repo.get(account_id)
    if not connector or connector.get('connector_type') != CONNECTOR_TYPE:
        return jsonify({'success': False, 'error': 'Account not found'}), 404

    try:
        client = _build_client(connector)
    except Exception as e:
        logger.exception('Autovit import-all: failed to build client for account %s', account_id)
        return jsonify({'success': False, 'error': str(e)}), 502

    uid = getattr(current_user, 'id', None)
    summary = {'imported': 0, 'updated': 0, 'skipped_no_vin': 0, 'photo_added': 0, 'errors': []}

    page, total_pages = 1, 1
    while page <= total_pages:
        try:
            data = client.get_adverts(page=page, status='active')
        except Exception as e:
            # A page-fetch failure must not lose the progress already made: record
            # it and stop paginating, returning the accumulated summary below.
            logger.warning('Autovit import-all: page %s fetch failed: %s', page, e)
            summary['errors'].append({'advert_id': None,
                                      'error': f'page {page} fetch failed: {e}'})
            break
        total_pages = data.get('total_pages', 1) or 1
        for ad in data.get('results', []):
            try:
                full = client.get_advert(str(ad.get('id'))) if ad.get('id') else ad
                vehicle_data = taxonomy.advert_to_vehicle(full)
                if not vehicle_data.get('vin') or not vehicle_data.get('brand') or not vehicle_data.get('model'):
                    summary['skipped_no_vin'] += 1
                    continue

                existing = _vehicle_repo.get_by_vin(vehicle_data['vin'])
                if existing:
                    merged = {k: val for k, val in vehicle_data.items() if k in taxonomy.MERGE_FIELDS}
                    _vehicle_repo.update(existing['id'], merged, updated_by=uid)
                    vid = existing['id']
                    summary['updated'] += 1
                else:
                    if uid:
                        vehicle_data['created_by'] = uid
                        vehicle_data['updated_by'] = uid
                    created = _vehicle_repo.create(vehicle_data)
                    vid = created['id']
                    summary['imported'] += 1

                summary['photo_added'] += _maybe_import_photos(client, full, vid)
            except Exception as e:
                logger.warning('Autovit import-all: advert %s failed: %s', ad.get('id'), e)
                summary['errors'].append({'advert_id': ad.get('id'), 'error': str(e)})
        page += 1

    status = 'success' if not summary['errors'] else 'partial'
    _repo.add_sync_log(account_id, 'import', status,
                       invoices_found=summary['imported'] + summary['updated'],
                       invoices_imported=summary['imported'], details=summary)
    return jsonify({'success': True, **summary})


# ── Taxonomy Mapping (Autovit Taxonomy Mapping project, Task 6) ──
#
# GET exposes the synced live-vocabulary cache (Task 5's `pull_taxonomy`
# output) + the editable CarPark-value -> Autovit-code map (Task 3's
# `get_map()`, flattened to a JSON-safe row list — its native shape keys on
# a `(source_value, make)` TUPLE, which `jsonify` cannot encode as a dict
# key) + the dimension registry, for the taxonomy admin UI. The other two
# routes are the admin actions that keep the map/cache current.

def _dimensions_payload() -> dict:
    """{dimension: {kind, param, required}} — the registry
    (`taxonomy_map.DIMENSIONS`) plus which dimensions block publish when
    unmapped (`taxonomy_map.REQUIRED_DIMENSIONS`)."""
    return {
        dim: {'kind': kind, 'param': param_name,
              'required': dim in taxonomy_map.REQUIRED_DIMENSIONS}
        for dim, (kind, param_name) in taxonomy_map.DIMENSIONS.items()
    }


def _map_rows(tmap: dict) -> list:
    """Flatten `AutovitTaxonomyRepository.get_map()`'s {dimension:
    {(source_value, make): {target_code, target_label}}} shape into a flat,
    JSON-safe row list: [{dimension, source_value, make, target_code,
    target_label}, ...]."""
    rows = []
    for dimension, entries in (tmap or {}).items():
        for (source_value, make), target in entries.items():
            rows.append({
                'dimension': dimension,
                'source_value': source_value,
                'make': make,
                'target_code': (target or {}).get('target_code'),
                'target_label': (target or {}).get('target_label'),
            })
    return rows


# carpark_vehicles column feeding each SIMPLE (single source column, not
# make-scoped, not equipment) dimension — mirrors taxonomy.vehicle_to_advert,
# the authoritative vehicle-field -> dimension wiring (`gearbox` reads the
# `transmission` column; the *Autovit param* named "transmission" is instead
# where the `drive` dimension's resolved code is EMITTED — see
# taxonomy_map.DIMENSIONS — two different things sharing a name).
# `air_conditioning_type`/`alloy_wheels_type` are intentionally excluded:
# no corresponding carpark_vehicles column exists to source them from.
_SOURCE_COLUMNS = {
    'fuel_type': 'fuel_type',
    'body_type': 'body_type',
    'color': 'color_exterior',
    'gearbox': 'transmission',
    'drive': 'drive_type',
    'pollution_standard': 'euro_standard',
}


def _source_row(tmap: dict, cache_rows: list, dimension: str,
                source_value: str, make: Optional[str] = None) -> dict:
    """One admin-UI row for a single CarPark source value: its current
    resolved Autovit target (fold-aware `taxonomy_map.resolve`, same lookup
    the publish path uses) plus top-N auto-suggest candidates
    (`taxonomy_sync.suggest`, pure/no I/O) ranked against the synced cache."""
    hit = taxonomy_map.resolve(tmap, dimension, source_value, make) or {}
    suggestions = taxonomy_sync.suggest(cache_rows, dimension, source_value, make)
    return {
        'source_value': source_value,
        'target_code': hit.get('target_code'),
        'target_label': hit.get('target_label'),
        'suggestions': [{'target_code': code, 'target_label': label, 'score': score}
                        for code, label, score in suggestions],
    }


def _sources_payload(tmap: dict, cache_rows: list) -> dict:
    """{dimension: [source_row, ...]} — every distinct, in-use CarPark value
    that needs an Autovit mapping, per dimension, each annotated with its
    current target + suggestions (`_source_row` above). `model` rows are
    additionally scoped/annotated by `make`/`resolved_make_code` (the
    RESOLVED Autovit make code for that CarPark brand — Task 3's make-
    scoping rule for `model`, mirrored here so the UI resolves/suggests
    model codes the same way the publish path does)."""
    distinct = _taxonomy_repo.distinct_source_values(_SOURCE_COLUMNS)
    sources = {
        dimension: [_source_row(tmap, cache_rows, dimension, value)
                    for value in values]
        for dimension, values in distinct.items()
    }

    sources['equipment'] = [_source_row(tmap, cache_rows, 'equipment', value)
                            for value in _taxonomy_repo.distinct_equipment()]

    makes = _taxonomy_repo.distinct_source_values({'make': 'brand'})['make']
    sources['make'] = [_source_row(tmap, cache_rows, 'make', value) for value in makes]

    model_rows = []
    for item in _taxonomy_repo.distinct_models():
        brand, model_value = item['make'], item['value']
        make_hit = taxonomy_map.resolve(tmap, 'make', brand) or {}
        resolved_make_code = make_hit.get('target_code')
        row = _source_row(tmap, cache_rows, 'model', model_value, resolved_make_code)
        row['make'] = brand
        row['resolved_make_code'] = resolved_make_code
        model_rows.append(row)
    sources['model'] = model_rows

    return sources


@autovit_bp.route('/api/taxonomy', methods=['GET'])
@carpark_required
def get_taxonomy():
    """Taxonomy admin UI data: synced cache + editable map + dimension
    registry + per-dimension distinct CarPark values needing a mapping
    (current target + auto-suggest candidates). Read-only — reachable by
    any CarPark user."""
    cache = _taxonomy_repo.get_cache()
    tmap = _taxonomy_repo.get_map()
    return jsonify({'success': True, 'cache': cache, 'map': _map_rows(tmap),
                    'dimensions': _dimensions_payload(),
                    'sources': _sources_payload(tmap, cache)})


@autovit_bp.route('/api/taxonomy/sync', methods=['POST'])
@admin_required
def sync_taxonomy():
    """Pull Autovit's LIVE category-29 taxonomy (parameters + makes + every
    make's models) and fully replace `carpark_autovit_taxonomy_cache`.

    SECURITY: @admin_required — a full sync is O(makes) network round-trips
    against the account's own credentials; gated the same as test-connection.
    """
    data = request.get_json(silent=True) or {}
    account_id = data.get('account_id')
    if not account_id:
        return jsonify({'success': False, 'error': 'account_id is required'}), 400
    connector = _repo.get(account_id)
    if not connector or connector.get('connector_type') != CONNECTOR_TYPE:
        return jsonify({'success': False, 'error': 'Account not found'}), 404
    try:
        client = _build_client(connector)
        rows = taxonomy_sync.pull_taxonomy(client)
        _taxonomy_repo.replace_cache(rows)
    except Exception as e:
        logger.exception('Autovit taxonomy sync failed for account %s', account_id)
        return jsonify({'success': False, 'error': str(e)}), 502
    by_dimension = {}
    for row in rows:
        by_dimension[row['dimension']] = by_dimension.get(row['dimension'], 0) + 1
    return jsonify({'success': True, 'synced': len(rows), 'by_dimension': by_dimension})


@autovit_bp.route('/api/taxonomy/map', methods=['PUT'])
@admin_required
def upsert_taxonomy_map():
    """Create/update a single CarPark-value -> Autovit-code mapping row."""
    data = request.get_json(silent=True) or {}
    dimension = data.get('dimension')
    source_value = data.get('source_value')
    if not dimension or source_value in (None, ''):
        return jsonify({'success': False,
                        'error': 'dimension and source_value are required'}), 400
    uid = getattr(current_user, 'id', None)
    _taxonomy_repo.upsert(dimension, source_value, data.get('make'),
                         data.get('target_code'), data.get('target_label'),
                         updated_by=uid)
    return jsonify({'success': True})


# ── Push: publish / unpublish a vehicle to Autovit (Task 8) ──

def _fill_location_contact(client, advert):
    """Backfill region/city/district/coordinates + contact on the advert from the
    account's own existing adverts when the connector config didn't provide them
    (Autovit requires location + contact on create). Best-effort — leaves the
    advert unchanged on any error."""
    need_loc = not (advert.get('region_id') and advert.get('city_id')) or 'coordinates' not in advert
    need_contact = not advert.get('contact')
    if not (need_loc or need_contact):
        return
    try:
        # Short bounds: this backfill is best-effort and runs inside the publish
        # flow — it must not eat into the ~60s gateway budget (→ 504). On timeout
        # the advert is just left without location/contact (create may then fail
        # loudly, which is better than a silent 504).
        results = (client.get_adverts(page=1, timeout=6) or {}).get('results') or []
        if not results:
            return
        src = client.get_advert(str(results[0].get('id')), timeout=6)
    except Exception:
        return
    if need_loc:
        for k in ('region_id', 'city_id', 'district_id', 'coordinates'):
            if src.get(k) is not None and advert.get(k) is None:
                advert[k] = src[k]
    if need_contact:
        c = src.get('contact') or {}
        advert['contact'] = {'person': c.get('person', ''),
                             'phones': c.get('phones') or c.get('phone_numbers') or []}


def _autovit_error_message(body: str) -> str:
    """Parse Autovit's rejection body (`{"error":{"type","message","details":
    {"params.model":"Valoare incorecta", ...}}}`, confirmed live) into an
    actionable RO message naming the offending field(s) + Autovit's own
    complaint — `str(e)` alone is just "400 Bad Request for url ...", which
    names neither.

    Never raises: an empty/unparseable/shapeless body degrades to a generic
    note rather than blowing up the already-failed publish's error path.
    """
    try:
        data = json.loads(body) if body else {}
    except (json.JSONDecodeError, TypeError):
        return 'Autovit a respins cererea (răspuns neinterpretabil).'
    err = (data or {}).get('error') or {}
    details = err.get('details') or {}
    if isinstance(details, dict) and details:
        parts = []
        for key, val in details.items():
            field = str(key).rsplit('.', 1)[-1]
            parts.append(f'câmp «{field}» invalid ({val})')
        return 'Autovit: ' + '; '.join(parts) + '.'
    msg = err.get('message') or err.get('type')
    if msg:
        return f'Autovit: {msg}'
    return 'Autovit a respins cererea.'


@autovit_bp.route('/api/accounts/<int:account_id>/publish', methods=['POST'])
@login_required
@carpark_edit_required
def publish(account_id):
    """Publish (create or update) a vehicle's advert on Autovit.

    HTTP-layer shell around `service.republish_vehicle` (Task 4): resolves the
    account/vehicle, fetches photo keys, then translates the service's result
    dict into the same responses this route always returned — 404s below,
    422 on unmapped-required taxonomy, 400 on missing fields, the unchanged
    dry_run/success JSON shapes, and 502 on an Autovit rejection.

    `dry_run=True` assembles + validates the advert payload and returns it
    without any network call — no client is built. Photos are attached as a
    presigned-URL image collection; a photo failure is recorded on the
    listing row (`last_error`) and in the response but never blocks the
    advert. After the write, the advert is read back and any params Autovit
    dropped are recorded the same way.
    """
    connector = _repo.get(account_id)
    if not connector or connector.get('connector_type') != CONNECTOR_TYPE:
        return jsonify({'success': False, 'error': 'Account not found'}), 404
    body = request.get_json(silent=True) or {}
    vehicle = _vehicle_repo.get_by_id(body.get('vehicle_id'))
    if not vehicle:
        return jsonify({'success': False, 'error': 'Vehicle not found'}), 404

    # Preload the DB-confirmed CarPark -> Autovit map ONCE and hand it to
    # republish_vehicle — every enum/equipment value is resolved against it
    # (Task 3); a miss is omitted from `params` (never raw-sent, since
    # Autovit silently drops anything that isn't one of its exact codes)
    # and reported back in `unmapped` as "<dimension>:<source_value>".
    tmap = _taxonomy_repo.get_map()
    # A photo-fetch failure here must NOT be swallowed: pre-refactor the same
    # error surfaced as a `photos:`-prefixed last_error + photos_ok=False (the
    # advert was still created). Thread it into the service as `photos_error`
    # so that visible, persisted signal is preserved — a transient DB blip on
    # the photos query can't silently publish an advert with zero photos and
    # no record anywhere that photo data was lost.
    photos, photos_error = [], None
    try:
        photos = _photo_repo.urls(vehicle['id'])
    except Exception as e:
        logger.warning('Autovit photo lookup failed for vehicle %s: %s', vehicle['id'], e)
        photos_error = f'photo lookup failed: {e}'

    result = republish_vehicle(connector, vehicle, photos, tmap,
                               dry_run=bool(body.get('dry_run')),
                               now=datetime.now(timezone.utc),
                               photos_error=photos_error)

    # An unmapped value in a REQUIRED dimension (make/model/body_type/
    # fuel_type/color) would doom the Autovit call to a 400 anyway — the
    # service blocks BEFORE spending the network round-trip; this route's job
    # is just to phrase the RO message naming exactly what needs mapping (vs.
    # Autovit's own opaque rejection).
    if result.get('unmapped_required'):
        unmapped_required = result['unmapped_required']
        return jsonify({
            'success': False,
            'error': ('Nu se poate publica: valori nemapate pentru Autovit la '
                      'câmp(uri) obligatorii — ' + ', '.join(unmapped_required) +
                      '. Mapează-le în Setări → Taxonomie Autovit înainte de publicare.'),
            'unmapped_required': unmapped_required,
        }), 422
    if result.get('missing') is not None:
        return jsonify({'success': False, 'error': 'Missing required fields',
                        'missing': result['missing']}), 400
    if result.get('dry_run'):
        return jsonify({'success': True, 'dry_run': True, 'advert': result['advert'],
                        'unmapped': result.get('unmapped', [])})
    if not result['success']:
        return jsonify({'success': False, 'error': result.get('error')}), 502

    # Task 7: default this car to a 1h auto-update schedule unless it already
    # has one (a user's explicit Manual/other choice is never overridden —
    # see ensure_auto_schedule's docstring). Kept here in the route (HTTP
    # layer), not in service.republish_vehicle, so the service core stays
    # free of scheduling side effects.
    # Best-effort: a transient DB error here must never turn an already-
    # successful publish into a reported failure (mirrors the
    # _verify_advert/_reconcile_best_effort pattern used elsewhere on this
    # hot path).
    try:
        ensure_auto_schedule(vehicle['id'], 'autovit', datetime.now(timezone.utc))
    except Exception as e:
        logger.warning('auto-schedule creation failed for vehicle %s: %s', vehicle['id'], e)

    # Car is now live on Autovit → flip READY_FOR_SALE to LISTED (best-effort).
    sync_listing_status_hook(vehicle['id'], changed_by=getattr(current_user, 'id', None))

    return jsonify({'success': True, 'external_id': result['external_id'],
                    'external_url': result['external_url'], 'status': result['status'],
                    'updated_existing': result['updated_existing'],
                    'photos_sent': result['photos_sent'],
                    'photos_ok': result['photos_ok'],
                    'photos_remote': result['photos_remote'],
                    'params_dropped': result['params_dropped'],
                    'unmapped': result['unmapped'],
                    'warnings': result['warnings']})


def _verify_advert(client: AutovitClient, advert_id, sent: dict) -> dict:
    """GET the advert back from Autovit and report which `params` keys we sent
    that Autovit did not keep, plus how many photos it holds.
    Returns {'params_dropped': [..], 'photos_remote': int|None, 'status_remote':
    str|None}. Never raises — verification must not turn a successful publish
    into a 502."""
    out = {'params_dropped': [], 'photos_remote': None, 'status_remote': None}
    if not advert_id:
        return out
    try:
        # Short bound: the verify read-back is a diagnostic — it must never push
        # the publish past the gateway's ~60s limit (→ 504). A timeout here just
        # skips the params_dropped check; the advert is already created.
        remote = client.get_account_advert(str(advert_id), timeout=8) or {}
    except Exception as e:
        logger.warning('Autovit post-publish verify failed for advert %s: %s', advert_id, e)
        return out
    remote_params = remote.get('params') or {}
    out['status_remote'] = remote.get('status')
    # Diagnostic: did Autovit apply our title on update, or keep/auto-derive its
    # own? (OTOMOTO often derives the displayed title from brand/model/params.)
    if remote.get('title') != sent.get('title'):
        logger.info('Autovit title advert=%s NOT applied: sent=%r remote=%r',
                    advert_id, sent.get('title'), remote.get('title'))
    sent_params = sent.get('params') or {}
    out['params_dropped'] = sorted(k for k in sent_params if k not in remote_params)
    photos = remote.get('photos') or remote.get('images')
    if isinstance(photos, (list, dict)):
        out['photos_remote'] = len(photos)
    if out['params_dropped']:
        logger.warning('Autovit kept advert %s but dropped params: %s',
                       advert_id, out['params_dropped'])
    return out


@autovit_bp.route('/api/accounts/<int:account_id>/unpublish', methods=['POST'])
@login_required
@carpark_edit_required
def unpublish(account_id):
    """Deactivate a vehicle's advert on Autovit (unpublish without deleting)."""
    connector = _repo.get(account_id)
    if not connector or connector.get('connector_type') != CONNECTOR_TYPE:
        return jsonify({'success': False, 'error': 'Account not found'}), 404
    body = request.get_json(silent=True) or {}
    listing = _listing_repo.get(body.get('vehicle_id'), account_id)
    if not listing or not listing.get('external_advert_id'):
        return jsonify({'success': False, 'error': 'No listing to unpublish'}), 404
    try:
        _build_client(connector).deactivate_advert(listing['external_advert_id'])
        _listing_repo.upsert(body['vehicle_id'], account_id, status='inactive')
        sync_listing_status_hook(body['vehicle_id'], changed_by=getattr(current_user, 'id', None))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 502



@autovit_bp.route('/api/accounts/<int:account_id>/delete-advert', methods=['POST'])
@login_required
@carpark_edit_required
def delete_advert(account_id):
    """Permanently delete a vehicle's Autovit advert (vs unpublish, which only
    deactivates/disables it). Re-publishing afterwards creates a NEW advert.
    Marks the listing removed_by_user so the chip flips to "Retras" → "Publică"."""
    connector = _repo.get(account_id)
    if not connector or connector.get('connector_type') != CONNECTOR_TYPE:
        return jsonify({'success': False, 'error': 'Account not found'}), 404
    body = request.get_json(silent=True) or {}
    listing = _listing_repo.get(body.get('vehicle_id'), account_id)
    if not listing or not listing.get('external_advert_id'):
        return jsonify({'success': False, 'error': 'No listing to delete'}), 404
    try:
        _build_client(connector).delete_advert(listing['external_advert_id'])
        _listing_repo.upsert(body['vehicle_id'], account_id,
                             status='removed_by_user', last_error=None)
        sync_listing_status_hook(body['vehicle_id'], changed_by=getattr(current_user, 'id', None))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 502

@autovit_bp.route('/api/reconcile', methods=['POST'])
@admin_required  # cross-account bulk op (all dealer accounts) — admin-gated, not per-editor
def reconcile_listings():
    """Scan every CONNECTED Autovit account's active adverts and link any that
    match a local vehicle by VIN but aren't linked yet — detects cars already
    published on Autovit (outside JARVIS / lost link) and connects them."""
    vehicles_by_vin = _vehicle_repo.vin_id_map()
    totals = {'scanned': 0, 'matched': 0, 'linked': 0, 'already_linked': 0, 'unmatched': 0}
    accounts = []
    for acc in _repo.get_all_by_type(CONNECTOR_TYPE):
        if (acc.get('status') or '') != 'connected':
            continue
        try:
            summary = reconcile_service.reconcile_autovit_account(
                _build_client(acc), acc['id'], vehicles_by_vin, _listing_repo)
        except Exception as e:
            logger.warning('Autovit reconcile failed for account %s: %s', acc.get('id'), e)
            accounts.append({'account_id': acc['id'], 'name': acc.get('name'), 'error': str(e)})
            continue
        accounts.append({'account_id': acc['id'], 'name': acc.get('name'),
                         'capped': summary['capped'], **{k: summary[k] for k in totals}})
        for k in totals:
            totals[k] += summary[k]
    return jsonify({'success': True, 'totals': totals, 'accounts': accounts})
