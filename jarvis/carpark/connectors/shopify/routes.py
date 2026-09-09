# jarvis/carpark/connectors/shopify/routes.py
"""Shopify connector API routes."""
import json
import logging
from functools import wraps

from flask import request, jsonify
from flask_login import current_user

from . import shopify_bp
from .client import ShopifyClient, ShopifyAuthError
from .connector import ShopifyConnector, ensure_platform
from . import taxonomy
from .taxonomy_repository import TaxonomyMapRepository
from core.connectors.repositories.connector_repository import ConnectorRepository
from core.utils.api_helpers import api_login_required, admin_required
from carpark.repositories.vehicle_repository import VehicleRepository
from carpark.repositories.photo_repository import PhotoRepository
from carpark.repositories.publishing_repository import PublishingRepository

logger = logging.getLogger('jarvis.shopify.routes')

_repo = ConnectorRepository()
_vehicle_repo = VehicleRepository()
_photo_repo = PhotoRepository()
_taxo_repo = TaxonomyMapRepository()
_pub_repo = PublishingRepository()

CONNECTOR_TYPE = 'shopify'
BULK_CAP = 250  # max vehicles auto-published when no explicit vehicle_ids are given

# Module-level client cache: connector id -> (creds_signature, ShopifyClient).
# The client-credentials access token lives ~24h on the client instance, so reusing
# the same instance across requests avoids a cold token fetch on every request.
_client_cache: dict = {}


def carpark_edit_required(f):
    """Require can_edit_carpark for Shopify write operations (publish/unpublish/bulk).

    Mirrors carpark.routes.vehicles.carpark_edit_required — publishing a vehicle to
    the live public storefront is a high-blast-radius write and must not be reachable
    by a read-only viewer.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        if not getattr(current_user, 'can_access_carpark', False):
            return jsonify({'success': False, 'error': 'CarPark access denied'}), 403
        if not getattr(current_user, 'can_edit_carpark', False):
            return jsonify({'success': False, 'error': 'CarPark edit permission denied'}), 403
        return f(*args, **kwargs)
    return decorated


def _parse_json(connector, field):
    val = connector.get(field) or {}
    if isinstance(val, str):
        try:
            val = json.loads(val)
        except (json.JSONDecodeError, TypeError):
            val = {}
    return val


def _safe_account(row):
    creds = _parse_json(row, 'credentials'); cfg = _parse_json(row, 'config')
    return {
        'id': row['id'], 'name': row.get('name', ''),
        'store_domain': cfg.get('store_domain', ''),
        'client_id': creds.get('client_id', ''),
        'status': row.get('status', 'disconnected'),
        'last_error': row.get('last_error'),
        'credential_fields': {'client_secret': '••••••' if creds.get('client_secret') else ''},
    }


def _build_client(connector) -> ShopifyClient:
    creds = _parse_json(connector, 'credentials'); cfg = _parse_json(connector, 'config')
    store_domain = cfg.get('store_domain', '')
    client_id = creds.get('client_id', '')
    client_secret = creds.get('client_secret', '')
    signature = (store_domain, client_id, client_secret)
    key = connector['id']
    cached = _client_cache.get(key)
    if cached and cached[0] == signature:
        return cached[1]
    client = ShopifyClient(store_domain, client_id, client_secret)
    _client_cache[key] = (signature, client)
    return client


def _get_single_account():
    rows = _repo.get_all_by_type(CONNECTOR_TYPE)
    return rows[0] if rows else None


# ---------- config CRUD ----------
@shopify_bp.route('/api/config', methods=['GET'])
@api_login_required
def get_accounts():
    rows = _repo.get_all_by_type(CONNECTOR_TYPE)
    return jsonify({'success': True, 'accounts': [_safe_account(r) for r in rows]})


@shopify_bp.route('/api/config', methods=['POST'])
@admin_required
def save_account():
    data = request.get_json(silent=True) or {}
    store_domain = (data.get('store_domain') or '').strip()
    client_id = (data.get('client_id') or '').strip()
    client_secret = (data.get('client_secret') or '').strip()
    account_id = data.get('id')
    if not store_domain or not client_id:
        return jsonify({'success': False, 'error': 'store_domain and client_id are required'}), 400
    config = {'store_domain': store_domain}
    creds = {'client_id': client_id}
    if client_secret:
        creds['client_secret'] = client_secret
    if account_id:
        connector = _repo.get(account_id)
        if not connector:
            return jsonify({'success': False, 'error': 'Account not found'}), 404
        existing = _parse_json(connector, 'credentials')
        existing.update({k: v for k, v in creds.items() if v})
        _repo.update(account_id, name=store_domain, config=config, credentials=existing)
        return jsonify({'success': True, 'account': _safe_account(_repo.get(account_id))})
    if not client_secret:
        return jsonify({'success': False, 'error': 'client_secret required for new account'}), 400
    cid = _repo.save(CONNECTOR_TYPE, store_domain, status='disconnected',
                     config=config, credentials=creds)
    return jsonify({'success': True, 'account': _safe_account(_repo.get(cid))}), 201


@shopify_bp.route('/api/config/<int:account_id>', methods=['DELETE'])
@admin_required
def delete_account(account_id):
    connector = _repo.get(account_id)
    if not connector or connector.get('connector_type') != CONNECTOR_TYPE:
        return jsonify({'success': False, 'error': 'Account not found'}), 404
    _repo.delete(account_id)
    return jsonify({'success': True})


@shopify_bp.route('/api/test-connection', methods=['POST'])
@api_login_required
def test_connection():
    connector = _get_single_account()
    if not connector:
        return jsonify({'success': False, 'error': 'Shopify not configured'}), 400
    try:
        shop = _build_client(connector).get_shop()
        _repo.update(connector['id'], status='connected', last_error=None)
        return jsonify({'success': True, 'data': shop})
    except ShopifyAuthError as e:
        _repo.update(connector['id'], status='error', last_error=str(e))
        return jsonify({'success': False, 'error': f'Auth failed: {e}'})
    except Exception as e:
        _repo.update(connector['id'], status='error', last_error=str(e))
        logger.exception('Shopify test-connection failed')
        return jsonify({'success': False, 'error': 'Connection failed'})


# ---------- taxonomy ----------
@shopify_bp.route('/api/taxonomy', methods=['GET'])
@api_login_required
def get_taxonomy():
    dim_cols = {d: taxonomy.vehicle_field_for(d) for d in taxonomy.DIMENSIONS}
    distinct = _taxo_repo.distinct_source_values(dim_cols)
    current = _taxo_repo.get_map()
    allowed = {}
    connector = _get_single_account()
    if connector:
        try:
            client = _build_client(connector)
            values = client.fetch_car_attribute_values()  # one query for all native dims
            for dim, attr_gid in taxonomy.DIMENSION_ATTRIBUTES.items():
                allowed[dim] = values.get(attr_gid, [])
        except Exception:
            logger.exception('taxonomy value fetch failed')
    return jsonify({'success': True, 'dimensions': taxonomy.DIMENSIONS,
                    'sources': distinct, 'allowed_values': allowed, 'mapping': current})


@shopify_bp.route('/api/taxonomy', methods=['POST'])
@admin_required
def save_taxonomy():
    from core.utils.api_helpers import current_user  # noqa
    data = request.get_json(silent=True) or {}
    entries = data.get('mappings') or []
    for e in entries:
        _taxo_repo.upsert(e['dimension'], e['source_value'], e.get('target_gid'),
                          e.get('target_label'), e.get('shopify_attribute_gid'),
                          updated_by=getattr(current_user, 'id', None))
    return jsonify({'success': True, 'saved': len(entries)})


# ---------- publish / unpublish ----------
def _connector_or_error():
    connector = _get_single_account()
    if not connector:
        return None, (jsonify({'success': False, 'error': 'Shopify is not configured'}), 400)
    client = _build_client(connector)
    platform_id = ensure_platform(_pub_repo, client.store_domain)
    return ShopifyConnector(client, _pub_repo, platform_id), None


@shopify_bp.route('/api/vehicles/<int:vid>/publish', methods=['POST'])
@carpark_edit_required
def publish_vehicle(vid):
    conn, err = _connector_or_error()
    if err:
        return err
    vehicle = _vehicle_repo.get_by_id(vid)
    if not vehicle:
        return jsonify({'success': False, 'error': 'Vehicle not found'}), 404
    photos = _photo_repo.get_by_vehicle(vid)
    result = conn.publish(vehicle, photos, _taxo_repo.get_map())
    return jsonify(result), (200 if result.get('success') else 400)


@shopify_bp.route('/api/vehicles/<int:vid>/unpublish', methods=['POST'])
@carpark_edit_required
def unpublish_vehicle(vid):
    conn, err = _connector_or_error()
    if err:
        return err
    listing = _pub_repo.get_listing_by_vehicle_platform(vid, conn.platform_id)
    if not listing or not listing.get('external_listing_id'):
        return jsonify({'success': False, 'error': 'No Shopify listing for this vehicle'}), 404
    result = conn.deactivate(listing['external_listing_id'])
    if result.get('success'):
        _pub_repo.update_listing(listing['id'], {'status': 'archived'})
    return jsonify(result), (200 if result.get('success') else 400)


@shopify_bp.route('/api/vehicles/<int:vid>/status', methods=['GET'])
@api_login_required
def vehicle_status(vid):
    connector = _get_single_account()
    if not connector:
        return jsonify({'success': True, 'listing': None})
    platform_id = ensure_platform(_pub_repo, _parse_json(connector, 'config').get('store_domain', ''))
    listing = _pub_repo.get_listing_by_vehicle_platform(vid, platform_id)
    return jsonify({'success': True, 'listing': listing})


@shopify_bp.route('/api/publish-bulk', methods=['POST'])
@carpark_edit_required
def publish_bulk():
    conn, err = _connector_or_error()
    if err:
        return err
    from carpark.connectors.shopify.mapper import ELIGIBLE_STATUSES
    ids = (request.get_json(silent=True) or {}).get('vehicle_ids')
    truncated = False
    total_eligible = None
    if not ids:
        rows = _vehicle_repo.query_all(
            "SELECT id FROM carpark_vehicles WHERE status = ANY(%s) AND deleted_at IS NULL",
            (list(ELIGIBLE_STATUSES),))
        ids = [r['id'] for r in rows]
        total_eligible = len(ids)
        if total_eligible > BULK_CAP:
            logger.warning('publish_bulk: %d eligible vehicles exceed cap %d; truncating',
                           total_eligible, BULK_CAP)
            ids = ids[:BULK_CAP]
            truncated = True
    taxo = _taxo_repo.get_map()
    results = []
    for vid in ids:
        vehicle = _vehicle_repo.get_by_id(vid)
        photos = _photo_repo.get_by_vehicle(vid) if vehicle else []
        res = conn.publish(vehicle, photos, taxo) if vehicle else {'success': False, 'error': 'not found'}
        results.append({'vehicle_id': vid, **res})
    response = {'success': True, 'results': results,
                'published': sum(1 for r in results if r.get('success')),
                'truncated': truncated}
    if truncated:
        response['total_eligible'] = total_eligible
    return jsonify(response)
