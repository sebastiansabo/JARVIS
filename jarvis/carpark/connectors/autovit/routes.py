"""Autovit.ro connector API routes.

Endpoints for managing dealer account credentials, testing connections,
and retrieving advert data from Autovit.
"""
import json
import logging

from flask import request, jsonify
from flask_login import login_required

from . import autovit_bp
from .client import AutovitClient, AutovitAuthError, PRODUCTION_URL, SANDBOX_URL
from core.connectors.repositories.connector_repository import ConnectorRepository
from core.utils.api_helpers import api_login_required
from carpark.repositories.vehicle_repository import VehicleRepository

logger = logging.getLogger('jarvis.autovit.routes')

_repo = ConnectorRepository()
_vehicle_repo = VehicleRepository()

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


# ── Import Advert → Vehicle Catalog ──

def _map_advert_to_vehicle(advert: dict) -> dict:
    """Map Autovit advert params to carpark_vehicles fields."""
    params = advert.get('params', {})

    def _val(key):
        v = params.get(key)
        if v is None:
            return None
        if isinstance(v, dict):
            return v.get('label') or v.get('value') or v.get('1')
        return v

    # Price extraction
    price = params.get('price', {})
    amount = price.get('1') if isinstance(price, dict) else None
    currency = price.get('currency', 'EUR') if isinstance(price, dict) else 'EUR'

    vehicle = {
        'vin': str(_val('vin') or '').strip().upper(),
        'brand': str(_val('make') or '').strip(),
        'model': str(_val('model') or '').strip(),
        'year_of_manufacture': int(_val('year')) if _val('year') else None,
        'fuel_type': str(_val('fuel_type') or '').strip() or None,
        'transmission': str(_val('gearbox') or '').strip() or None,
        'body_type': str(_val('body_type') or '').strip() or None,
        'mileage_km': int(_val('mileage')) if _val('mileage') else None,
        'engine_displacement_cc': int(_val('engine_capacity')) if _val('engine_capacity') else None,
        'engine_power_hp': int(_val('engine_power')) if _val('engine_power') else None,
        'color_exterior': str(_val('color') or '').strip() or None,
        'doors': int(_val('door_count')) if _val('door_count') else None,
        'seats': int(_val('nr_seats')) if _val('nr_seats') else None,
        'drive_type': str(_val('drive') or '').strip() or None,
        'current_price': float(amount) if amount else None,
        'price_currency': currency,
        'listing_title': advert.get('title', ''),
        'listing_description': advert.get('description', ''),
        'source': 'autovit',
        'status': 'ACQUIRED',
    }

    # Remove None values
    return {k: v for k, v in vehicle.items() if v is not None and v != ''}


@autovit_bp.route('/api/accounts/<int:account_id>/import-advert', methods=['POST'])
@api_login_required
def import_advert(account_id):
    """Import a single advert into the vehicle catalog."""
    from flask_login import current_user

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

    vehicle_data = _map_advert_to_vehicle(advert)

    # Validate required fields
    if not vehicle_data.get('vin'):
        return jsonify({'success': False, 'error': 'Advert has no VIN — cannot import without a VIN'}), 400
    if not vehicle_data.get('brand') or not vehicle_data.get('model'):
        return jsonify({'success': False, 'error': 'Advert missing make/model'}), 400

    # Check for duplicate VIN
    existing = _vehicle_repo.get_by_vin(vehicle_data['vin'])
    if existing:
        return jsonify({
            'success': False,
            'error': f'Vehicle with VIN {vehicle_data["vin"]} already exists (ID: {existing["id"]})',
            'existing_vehicle_id': existing['id'],
        }), 409

    # Add server fields
    if hasattr(current_user, 'id'):
        vehicle_data['created_by'] = current_user.id
        vehicle_data['updated_by'] = current_user.id

    try:
        vehicle = _vehicle_repo.create(vehicle_data)
        return jsonify({'success': True, 'vehicle': {'id': vehicle['id'], 'vin': vehicle['vin'], 'brand': vehicle['brand'], 'model': vehicle['model']}}), 201
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.exception('Failed to create vehicle from advert %s', advert_id)
        return jsonify({'success': False, 'error': f'Failed to create vehicle: {e}'}), 500
