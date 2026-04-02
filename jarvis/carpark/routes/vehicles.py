"""Vehicle API routes — CRUD, catalog, status, history, locations."""
import logging
from functools import wraps

from flask import request, jsonify
from flask_login import login_required, current_user

from carpark import carpark_bp
from carpark.services.vehicle_service import VehicleService

logger = logging.getLogger('jarvis.carpark')

_vehicle_service = VehicleService()


# ── Permission decorators ──

def carpark_required(f):
    """Require can_access_carpark permission on the user's role."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        if not getattr(current_user, 'can_access_carpark', False):
            return jsonify({'success': False, 'error': 'CarPark access denied'}), 403
        return f(*args, **kwargs)
    return decorated


def carpark_edit_required(f):
    """Require can_edit_carpark for write operations."""
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


def carpark_delete_required(f):
    """Require can_delete_carpark for delete operations."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        if not getattr(current_user, 'can_access_carpark', False):
            return jsonify({'success': False, 'error': 'CarPark access denied'}), 403
        if not getattr(current_user, 'can_delete_carpark', False):
            return jsonify({'success': False, 'error': 'CarPark delete permission denied'}), 403
        return f(*args, **kwargs)
    return decorated


# ── Tenant isolation helper ──

def _user_company_id():
    """Get the current user's company_id. Returns None only if user has no company."""
    return getattr(current_user, 'company_id', None)


def _verify_vehicle_ownership(vehicle_id):
    """Fetch vehicle and verify it belongs to the current user's company.
    Returns (vehicle_dict, None) on success, or (None, error_response) on failure."""
    vehicle = _vehicle_service.get_vehicle(vehicle_id)
    if not vehicle:
        return None, (jsonify({'success': False, 'error': 'Vehicle not found'}), 404)
    cid = _user_company_id()
    if cid and vehicle.get('company_id') and vehicle['company_id'] != cid:
        return None, (jsonify({'success': False, 'error': 'Vehicle not found'}), 404)
    return vehicle, None


# ── Helper: sanitize JSON-serializable response ──

def _serialize(obj):
    """Convert Decimal/date/datetime to JSON-safe types."""
    import decimal
    import datetime
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    return obj


# ═══════════════════════════════════════════════
# VEHICLES — CATALOG
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles', methods=['GET'])
@login_required
@carpark_required
def list_vehicles():
    """Paginated vehicle catalog with filters.

    Query params: page, per_page, sort_by, sort_dir, status, category,
    brand, model, fuel_type, body_type, year_min, year_max,
    price_min, price_max, km_min, km_max, location_id, search
    """
    try:
        page = max(1, int(request.args.get('page', 1)))
        per_page = max(1, min(100, int(request.args.get('per_page', 25))))
    except (ValueError, TypeError):
        page, per_page = 1, 25

    sort_by = request.args.get('sort_by') or request.args.get('sort', 'acquisition_date')
    sort_dir = request.args.get('sort_dir') or request.args.get('order', 'DESC')

    # Collect filters from query string
    filters = {}
    for key in ('status', 'category', 'brand', 'model', 'fuel_type',
                'body_type', 'year_min', 'year_max', 'price_min', 'price_max',
                'km_min', 'km_max', 'location_id', 'search'):
        val = request.args.get(key)
        if val:
            filters[key] = val

    # SECURITY: Force company_id to current user's company (tenant isolation)
    cid = _user_company_id()
    if cid:
        filters['company_id'] = str(cid)

    try:
        result = _vehicle_service.get_catalog(filters, page, per_page, sort_by, sort_dir)
        return jsonify(_serialize(result))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Invalid filter parameters'}), 400
    except Exception as e:
        logger.error(f'Catalog query failed: {e}', exc_info=True)
        return jsonify({'success': False, 'error': 'Internal error'}), 500


@carpark_bp.route('/vehicles/status-counts', methods=['GET'])
@login_required
@carpark_required
def vehicle_status_counts():
    """Vehicle counts per status for catalog tabs."""
    cid = _user_company_id()
    counts = _vehicle_service.get_status_counts(cid)
    return jsonify({'counts': _serialize(counts)})


@carpark_bp.route('/vehicles/filter-options', methods=['GET'])
@login_required
@carpark_required
def vehicle_filter_options():
    """Distinct values for filter dropdowns (brands, fuel types, body types)."""
    cid = _user_company_id()
    options = _vehicle_service.get_filter_options(cid)
    return jsonify(options)


# ═══════════════════════════════════════════════
# VEHICLES — DETAIL
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>', methods=['GET'])
@login_required
@carpark_required
def get_vehicle(vehicle_id):
    """Full vehicle detail with photos."""
    vehicle, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err
    return jsonify({'vehicle': _serialize(vehicle)})


# ═══════════════════════════════════════════════
# VEHICLES — CREATE
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles', methods=['POST'])
@login_required
@carpark_edit_required
def create_vehicle():
    """Create a new vehicle.

    Body: JSON with vehicle fields. Required: vin, brand, model.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'error': 'Request body required'}), 400

    # SECURITY: Force company_id to current user's company
    cid = _user_company_id()
    if cid:
        data['company_id'] = cid

    try:
        vehicle = _vehicle_service.create_vehicle(data, created_by=current_user.id)
        return jsonify({'vehicle': _serialize(vehicle)}), 201
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error(f'Vehicle creation failed: {e}', exc_info=True)
        return jsonify({'success': False, 'error': 'Internal error'}), 500


# ═══════════════════════════════════════════════
# VEHICLES — UPDATE
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>', methods=['PUT'])
@login_required
@carpark_edit_required
def update_vehicle(vehicle_id):
    """Update vehicle fields. Logs changes to modification history."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'error': 'Request body required'}), 400

    # SECURITY: Verify vehicle belongs to user's company
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err

    try:
        vehicle = _vehicle_service.update_vehicle(
            vehicle_id, data,
            updated_by=current_user.id,
            updated_by_name=current_user.name
        )
        if not vehicle:
            return jsonify({'success': False, 'error': 'Vehicle not found'}), 404
        return jsonify({'vehicle': _serialize(vehicle)})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error(f'Vehicle update failed: {e}', exc_info=True)
        return jsonify({'success': False, 'error': 'Internal error'}), 500


# ═══════════════════════════════════════════════
# VEHICLES — DELETE
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>', methods=['DELETE'])
@login_required
@carpark_delete_required
def delete_vehicle(vehicle_id):
    """Soft-delete a vehicle."""
    # SECURITY: Verify vehicle belongs to user's company
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err

    if _vehicle_service.delete_vehicle(vehicle_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Vehicle not found'}), 404


# ═══════════════════════════════════════════════
# VEHICLES — STATUS CHANGE
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/status', methods=['PUT'])
@login_required
@carpark_edit_required
def change_vehicle_status(vehicle_id):
    """Change vehicle status. Body: { status, notes? }"""
    data = request.get_json(silent=True)
    if not data or not data.get('status'):
        return jsonify({'success': False, 'error': 'status is required'}), 400

    # SECURITY: Verify vehicle belongs to user's company
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err

    try:
        vehicle = _vehicle_service.change_status(
            vehicle_id, data['status'],
            changed_by=current_user.id,
            notes=data.get('notes')
        )
        if not vehicle:
            return jsonify({'success': False, 'error': 'Vehicle not found'}), 404
        return jsonify({'vehicle': _serialize(vehicle)})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error(f'Status change failed: {e}', exc_info=True)
        return jsonify({'success': False, 'error': 'Internal error'}), 500


# ═══════════════════════════════════════════════
# VEHICLES — HISTORY
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/status-history', methods=['GET'])
@login_required
@carpark_required
def vehicle_status_history(vehicle_id):
    """Status change history for a vehicle."""
    # SECURITY: Verify vehicle belongs to user's company
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err
    history = _vehicle_service.get_status_history(vehicle_id)
    return jsonify({'history': _serialize(history)})


@carpark_bp.route('/vehicles/<int:vehicle_id>/modifications', methods=['GET'])
@login_required
@carpark_required
def vehicle_modifications(vehicle_id):
    """Field-level modification history."""
    # SECURITY: Verify vehicle belongs to user's company
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err
    limit = request.args.get('limit', 50, type=int)
    limit = min(limit, 200)
    history = _vehicle_service.get_modification_history(vehicle_id, limit)
    return jsonify({'modifications': _serialize(history)})


# ═══════════════════════════════════════════════
# VEHICLES — VIN CHECK
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/check-vin', methods=['GET'])
@login_required
@carpark_required
def check_vin():
    """Check if a VIN already exists. Returns vehicle stub or null."""
    vin = request.args.get('vin', '').strip().upper()
    if not vin or len(vin) != 17:
        return jsonify({'success': False, 'error': 'Valid 17-char VIN required'}), 400
    existing = _vehicle_service._repo.get_by_vin(vin)
    if existing:
        return jsonify({'exists': True, 'vehicle_id': existing['id']})
    return jsonify({'exists': False})


# ═══════════════════════════════════════════════
# LOCATIONS
# ═══════════════════════════════════════════════

@carpark_bp.route('/locations', methods=['GET'])
@login_required
@carpark_required
def list_locations():
    """List all active locations for current user's company."""
    cid = _user_company_id()
    locations = _vehicle_service.get_locations(cid)
    return jsonify({'locations': _serialize(locations)})


@carpark_bp.route('/locations', methods=['POST'])
@login_required
@carpark_edit_required
def create_location():
    """Create a new location."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'error': 'Request body required'}), 400
    # SECURITY: Force company_id to current user's company
    cid = _user_company_id()
    if cid:
        data['company_id'] = cid
    try:
        location = _vehicle_service.create_location(data)
        return jsonify({'location': _serialize(location)}), 201
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error(f'Location creation failed: {e}', exc_info=True)
        return jsonify({'success': False, 'error': 'Internal error'}), 500


@carpark_bp.route('/locations/<int:location_id>', methods=['PUT'])
@login_required
@carpark_edit_required
def update_location(location_id):
    """Update a location."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'error': 'Request body required'}), 400
    # SECURITY: Remove company_id from update data (can't reassign location)
    data.pop('company_id', None)
    location = _vehicle_service.update_location(location_id, data)
    if not location:
        return jsonify({'error': 'Location not found'}), 404
    return jsonify({'location': _serialize(location)})
