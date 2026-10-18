"""Autovit.ro connector API routes.

Endpoints for managing dealer account credentials, testing connections,
and retrieving advert data from Autovit.
"""
import json
import logging
import time

import requests

from flask import request, jsonify
from flask_login import login_required, current_user

from . import autovit_bp
from . import taxonomy
from .client import AutovitClient, AutovitAuthError, PRODUCTION_URL, SANDBOX_URL
from core.connectors.repositories.connector_repository import ConnectorRepository
from core.utils.api_helpers import api_login_required, admin_required
from carpark.repositories.vehicle_repository import VehicleRepository
from carpark.repositories.vehicle_photo_repository import VehiclePhotoRepository
from carpark.repositories.autovit_listing_repository import AutovitListingRepository
from carpark.services import reconcile_service
from carpark.services.photo_urls import public_photo_urls
from carpark.routes.vehicles import (
    carpark_edit_required, carpark_required, _verify_vehicle_ownership, _serialize,
)

logger = logging.getLogger('jarvis.autovit.routes')

_repo = ConnectorRepository()
_vehicle_repo = VehicleRepository()
_photo_repo = VehiclePhotoRepository()
_listing_repo = AutovitListingRepository()

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
    standard exists-only ownership check — mirrors GET /vehicles/<id>.
    """
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err
    listings = _listing_repo.list_by_vehicle(vehicle_id)
    return jsonify({'success': True, 'listings': [_serialize(dict(l)) for l in listings]})


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
    listings = _listing_repo.list_by_vehicle(vehicle_id)
    return jsonify({'success': True, 'refreshed': refreshed,
                    'listings': [_serialize(dict(l)) for l in listings]})


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


@autovit_bp.route('/api/accounts/<int:account_id>/publish', methods=['POST'])
@login_required
@carpark_edit_required
def publish(account_id):
    """Publish (create or update) a vehicle's advert on Autovit.

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

    advert = taxonomy.vehicle_to_advert(vehicle, connector)
    missing = taxonomy.validate_for_publish(advert)
    if missing:
        return jsonify({'success': False, 'error': 'Missing required fields', 'missing': missing}), 400
    if body.get('dry_run'):
        return jsonify({'success': True, 'dry_run': True, 'advert': advert})

    client = _build_client(connector)
    # 504-guard: a single publish chains several sequential Autovit calls (token,
    # location/contact backfill, image collection, create/update, verify). At the
    # default 15s each they can sum past DO's ~60s gateway limit → 504. Cap the
    # per-call timeout to 10s here (the best-effort backfill and the verify are
    # bounded even shorter at their call sites) so the worst case stays ~<55s.
    client.timeout = 10
    _t0 = time.monotonic()
    # Backfill location + contact from the account's own adverts if the config
    # didn't carry them (Autovit requires them on create).
    _fill_location_contact(client, advert)
    _t_fill = time.monotonic()
    # Photos: non-fatal (an advert is created fine without them, as an unpaid
    # draft) but NOT silent — a failure is recorded on the listing row and in
    # the response so it shows up in JARVIS instead of as an empty gallery on
    # Autovit's form.
    photos = _attach_image_collection(client, advert, vehicle['id'])
    _t_photos = time.monotonic()

    try:
        existing = _listing_repo.get(vehicle['id'], account_id)
        ext_id = existing.get('external_advert_id') if existing else None
        # An advert the user/moderator removed on Autovit can't be updated — the
        # PUT returns 400 ("Bad Request"). Treat a known-removed listing as gone
        # and create a fresh advert instead of failing the publish.
        removed_on_autovit = bool(existing) and str(existing.get('status') or '').startswith('removed')
        updated_existing = bool(ext_id) and not removed_on_autovit
        if updated_existing:
            try:
                client.update_advert(ext_id, advert)
            except requests.HTTPError as e:
                code = getattr(e.response, 'status_code', None)
                if code not in (400, 404, 410):
                    raise
                # Advert gone/invalid on Autovit — recreate rather than surface a 400.
                logger.info('Autovit update of advert %s returned %s; recreating', ext_id, code)
                updated_existing = False
        if updated_existing:
            ext_url = existing.get('external_url')
            ext_status = 'active'
        else:
            # VIN-dedup: before creating, check whether a live Autovit ad with
            # this vehicle's VIN already exists on the account. If so, adopt +
            # update it (connect/reconcile the listing) instead of posting a
            # duplicate — covers the case where the local link was lost/removed
            # but the ad is still up.
            adopted_id, adopted_url = reconcile_service.find_active_advert_by_vin(
                client, vehicle.get('vin'))
            if adopted_id:
                logger.info('Autovit: adopting live advert %s by VIN for vehicle %s '
                            '(no duplicate)', adopted_id, vehicle['id'])
                client.update_advert(adopted_id, advert)
                ext_id, ext_url, ext_status = adopted_id, adopted_url, 'active'
                updated_existing = True
            else:
                # New adverts are created in Autovit's `unpaid` status — a private
                # draft, not visible on the marketplace until paid/activated.
                result = client.create_advert(advert) or {}
                ext_id = result.get('id')
                ext_url = result.get('url')
                ext_status = result.get('status') or 'active'
        _t_write = time.monotonic()

        # Post-write verification: read the advert back and diff what we sent
        # against what Autovit kept. Silently-dropped params are otherwise
        # invisible (the create/update returns 2xx regardless).
        verify = _verify_advert(client, ext_id, advert)
        # Per-stage timing — surfaces which leg is slow when a publish flirts
        # with the gateway limit (the whole reason for the bounds above).
        logger.info(
            'Autovit publish timing vehicle=%s update=%s fill=%.1fs photos=%.1fs '
            'write=%.1fs verify=%.1fs total=%.1fs', vehicle['id'], updated_existing,
            _t_fill - _t0, _t_photos - _t_fill, _t_write - _t_photos,
            time.monotonic() - _t_write, time.monotonic() - _t0)

        # Problems belong in last_error (the fault surface that drives the error
        # badge). The "already published" note is informational — it goes to the
        # response warnings (a toast) only, and must NOT pollute last_error.
        problems = []
        if photos['error']:
            problems.append(f"photos: {photos['error']}")
        if verify['params_dropped']:
            problems.append('params_dropped: ' + ', '.join(verify['params_dropped']))
        if verify['photos_remote'] is not None and photos['sent'] and \
                verify['photos_remote'] < photos['sent']:
            problems.append(f"photos: sent {photos['sent']}, Autovit kept {verify['photos_remote']}")
        last_error = '; '.join(problems) if problems else None
        warnings = (['Anunț deja publicat pe Autovit — a fost actualizat.']
                    if updated_existing else []) + problems

        _listing_repo.upsert(vehicle['id'], account_id,
                             external_advert_id=str(ext_id),
                             external_url=ext_url,
                             status=ext_status,
                             last_error=last_error)
        return jsonify({'success': True, 'external_id': ext_id,
                        'external_url': ext_url, 'status': ext_status,
                        'updated_existing': updated_existing,
                        'photos_sent': photos['sent'],
                        'photos_ok': photos['error'] is None,
                        'photos_remote': verify['photos_remote'],
                        'params_dropped': verify['params_dropped'],
                        'warnings': warnings})
    except Exception as e:
        logger.exception('Autovit publish failed for vehicle %s', vehicle['id'])
        _listing_repo.set_error(vehicle['id'], account_id, str(e))
        return jsonify({'success': False, 'error': str(e)}), 502


def _attach_image_collection(client: AutovitClient, advert: dict, vehicle_id: int) -> dict:
    """Build an Autovit image collection from the vehicle's photos and attach
    its id to `advert`. Returns {'sent': n, 'error': str|None}.

    carpark_vehicle_photos.url holds PRIVATE Spaces object keys, not URLs —
    Autovit fetches images server-side and cannot read those, so every key is
    presigned first (same fix Shopify got in connectors/shopify/connector.py).
    Before this, every push sent raw keys, Autovit rejected the collection,
    and the exception was downgraded to a log warning: 100% of JARVIS-published
    adverts had zero photos and `success: true`.
    """
    try:
        photo_urls = public_photo_urls(_photo_repo.urls(vehicle_id))
    except Exception as e:
        logger.warning('Autovit photo lookup failed for vehicle %s: %s', vehicle_id, e)
        return {'sent': 0, 'error': f'photo lookup failed: {e}'}
    if not photo_urls:
        return {'sent': 0, 'error': None}
    try:
        icid = client.create_image_collection(photo_urls)
    except Exception as e:
        # A bare "400 Bad Request" isn't actionable — capture Autovit's actual
        # rejection reason (the HTTPError response body) plus a sample source URL
        # (host/path/query shape) so the real cause is diagnosable from the logs.
        body = getattr(getattr(e, 'response', None), 'text', '') or ''
        sample = photo_urls[0] if photo_urls else ''
        logger.warning(
            'Autovit image collection failed for vehicle %s: %s | autovit_body=%s | sample_source=%s',
            vehicle_id, e, body[:600], sample[:220])
        return {'sent': len(photo_urls), 'error': f'image collection rejected: {e}'}
    if not icid:
        return {'sent': len(photo_urls), 'error': 'image collection returned no id'}
    advert['image_collection_id'] = icid
    return {'sent': len(photo_urls), 'error': None}


def _verify_advert(client: AutovitClient, advert_id, sent: dict) -> dict:
    """GET the advert back from Autovit and report which `params` keys we sent
    that Autovit did not keep, plus how many photos it holds.
    Returns {'params_dropped': [..], 'photos_remote': int|None}. Never raises —
    verification must not turn a successful publish into a 502."""
    out = {'params_dropped': [], 'photos_remote': None}
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
