"""Autovit.ro connector API routes.

Endpoints for managing dealer account credentials, testing connections,
and retrieving advert data from Autovit.
"""
import json
import logging

from flask import request, jsonify
from flask_login import login_required, current_user

from . import autovit_bp
from . import taxonomy
from .client import AutovitClient, AutovitAuthError, PRODUCTION_URL, SANDBOX_URL
from core.connectors.repositories.connector_repository import ConnectorRepository
from core.utils.api_helpers import api_login_required
from carpark.repositories.vehicle_repository import VehicleRepository
from carpark.repositories.vehicle_photo_repository import VehiclePhotoRepository

logger = logging.getLogger('jarvis.autovit.routes')

_repo = ConnectorRepository()
_vehicle_repo = VehicleRepository()
_photo_repo = VehiclePhotoRepository()

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
@api_login_required
def get_accounts():
    """List all Autovit dealer accounts (credentials masked)."""
    rows = _repo.get_all_by_type(CONNECTOR_TYPE)
    return jsonify({'success': True, 'accounts': [_safe_account(r) for r in rows]})


@autovit_bp.route('/api/config/<int:account_id>', methods=['GET'])
@api_login_required
def get_account(account_id):
    """Get a single Autovit dealer account (credentials masked)."""
    connector = _repo.get(account_id)
    if not connector or connector.get('connector_type') != CONNECTOR_TYPE:
        return jsonify({'success': False, 'error': 'Account not found'}), 404
    return jsonify({'success': True, 'account': _safe_account(connector)})


@autovit_bp.route('/api/config', methods=['POST'])
@api_login_required
def save_account():
    """Create or update an Autovit dealer account."""
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
@api_login_required
def delete_account(account_id):
    """Remove an Autovit dealer account."""
    connector = _repo.get(account_id)
    if not connector or connector.get('connector_type') != CONNECTOR_TYPE:
        return jsonify({'success': False, 'error': 'Account not found'}), 404
    _repo.delete(account_id)
    return jsonify({'success': True})


# ── Connection Testing ──

@autovit_bp.route('/api/test-connection', methods=['POST'])
@api_login_required
def test_connection():
    """Test connection for a specific account."""
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
@api_login_required
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


# ── Adverts (future) ──

@autovit_bp.route('/api/accounts/<int:account_id>/adverts', methods=['GET'])
@api_login_required
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
@api_login_required
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
@api_login_required
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
