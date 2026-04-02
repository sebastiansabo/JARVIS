"""Publishing API routes — Platforms, listings, publish/deactivate, sync."""
import logging

from flask import request, jsonify
from flask_login import login_required, current_user

from carpark import carpark_bp
from carpark.services.publishing_service import PublishingService
from carpark.routes.vehicles import (
    carpark_required, carpark_edit_required, _serialize,
    _verify_vehicle_ownership, _user_company_id,
)

logger = logging.getLogger('jarvis.carpark')

_pub_service = PublishingService()


# ═══════════════════════════════════════════════
# PLATFORMS — LIST / CREATE
# ═══════════════════════════════════════════════

@carpark_bp.route('/platforms', methods=['GET'])
@login_required
@carpark_required
def list_platforms():
    """List publishing platforms. Query: ?active_only=true"""
    active_only = request.args.get('active_only', '').lower() == 'true'
    company_id = _user_company_id()
    platforms = _pub_service.list_platforms(company_id, active_only)
    return jsonify({'platforms': _serialize(platforms)})


@carpark_bp.route('/platforms', methods=['POST'])
@login_required
@carpark_edit_required
def create_platform():
    """Create a publishing platform.

    Body: { name, platform_type?, brand_scope?, api_base_url?,
            api_key_encrypted?, dealer_account_id?, website_url?,
            icon_url?, config? }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    data['company_id'] = _user_company_id()

    try:
        platform = _pub_service.create_platform(data)
        return jsonify({'platform': _serialize(platform)}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f'Platform creation failed: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500


# ═══════════════════════════════════════════════
# PLATFORMS — GET / UPDATE / DELETE
# ═══════════════════════════════════════════════

@carpark_bp.route('/platforms/<int:platform_id>', methods=['GET'])
@login_required
@carpark_required
def get_platform(platform_id):
    platform = _pub_service.get_platform(platform_id)
    if not platform:
        return jsonify({'error': 'Platform not found'}), 404
    return jsonify({'platform': _serialize(platform)})


@carpark_bp.route('/platforms/<int:platform_id>', methods=['PUT'])
@login_required
@carpark_edit_required
def update_platform(platform_id):
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    existing = _pub_service.get_platform(platform_id)
    if not existing:
        return jsonify({'error': 'Platform not found'}), 404

    platform = _pub_service.update_platform(platform_id, data)
    if not platform:
        return jsonify({'error': 'No fields to update'}), 400
    return jsonify({'platform': _serialize(platform)})


@carpark_bp.route('/platforms/<int:platform_id>', methods=['DELETE'])
@login_required
@carpark_edit_required
def delete_platform(platform_id):
    if _pub_service.delete_platform(platform_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Platform not found'}), 404


# ═══════════════════════════════════════════════
# VEHICLE LISTINGS
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/listings', methods=['GET'])
@login_required
@carpark_required
def vehicle_listings(vehicle_id):
    """List all platform listings for a vehicle."""
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err
    listings = _pub_service.get_vehicle_listings(vehicle_id)
    return jsonify({'listings': _serialize(listings)})


# ═══════════════════════════════════════════════
# PUBLISH
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/publish', methods=['POST'])
@login_required
@carpark_edit_required
def publish_vehicle(vehicle_id):
    """Publish vehicle to a specific platform.

    Body: { platform_id, expires_at? }
    """
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    platform_id = data.get('platform_id')
    if not platform_id:
        return jsonify({'error': 'platform_id is required'}), 400

    try:
        result = _pub_service.publish_to_platform(
            vehicle_id, platform_id,
            expires_at=data.get('expires_at'),
        )
        return jsonify(_serialize(result)), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f'Publish failed: {e}', exc_info=True)
        return jsonify({'error': 'Internal error'}), 500


@carpark_bp.route('/vehicles/<int:vehicle_id>/publish-all', methods=['POST'])
@login_required
@carpark_edit_required
def publish_vehicle_all(vehicle_id):
    """Publish vehicle to all active platforms.

    Body: { expires_at? }
    """
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    company_id = _user_company_id()

    results = _pub_service.publish_to_all(
        vehicle_id, company_id=company_id,
        expires_at=data.get('expires_at'),
    )
    return jsonify({'results': _serialize(results)})


# ═══════════════════════════════════════════════
# LISTING UPDATE
# ═══════════════════════════════════════════════

@carpark_bp.route('/listings/<int:listing_id>', methods=['PUT'])
@login_required
@carpark_edit_required
def update_listing(listing_id):
    """Update listing details (external_url, views, etc.)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    existing = _pub_service.get_listing(listing_id)
    if not existing:
        return jsonify({'error': 'Listing not found'}), 404

    _, err = _verify_vehicle_ownership(existing['vehicle_id'])
    if err:
        return err

    listing = _pub_service.update_listing(listing_id, data)
    if not listing:
        return jsonify({'error': 'No fields to update'}), 400
    return jsonify({'listing': _serialize(listing)})


# ═══════════════════════════════════════════════
# ACTIVATE / DEACTIVATE
# ═══════════════════════════════════════════════

@carpark_bp.route('/listings/<int:listing_id>/activate', methods=['POST'])
@login_required
@carpark_edit_required
def activate_listing(listing_id):
    """Activate a listing."""
    existing = _pub_service.get_listing(listing_id)
    if not existing:
        return jsonify({'error': 'Listing not found'}), 404
    _, err = _verify_vehicle_ownership(existing['vehicle_id'])
    if err:
        return err

    try:
        listing = _pub_service.activate_listing(listing_id)
        return jsonify({'listing': _serialize(listing)})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@carpark_bp.route('/listings/<int:listing_id>/deactivate', methods=['POST'])
@login_required
@carpark_edit_required
def deactivate_listing(listing_id):
    """Deactivate a listing."""
    existing = _pub_service.get_listing(listing_id)
    if not existing:
        return jsonify({'error': 'Listing not found'}), 404
    _, err = _verify_vehicle_ownership(existing['vehicle_id'])
    if err:
        return err

    try:
        listing = _pub_service.deactivate_listing(listing_id)
        return jsonify({'listing': _serialize(listing)})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@carpark_bp.route('/vehicles/<int:vehicle_id>/deactivate-all', methods=['POST'])
@login_required
@carpark_edit_required
def deactivate_all_listings(vehicle_id):
    """Deactivate all listings for a vehicle."""
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err

    results = _pub_service.deactivate_all(vehicle_id)
    return jsonify({'deactivated': _serialize(results), 'count': len(results)})


# ═══════════════════════════════════════════════
# SYNC
# ═══════════════════════════════════════════════

@carpark_bp.route('/publishing/sync', methods=['POST'])
@login_required
@carpark_edit_required
def sync_all_stats():
    """Full sync of all active listing stats from platforms."""
    result = _pub_service.sync_all_platform_stats()
    return jsonify(_serialize(result))


@carpark_bp.route('/listings/<int:listing_id>/sync', methods=['POST'])
@login_required
@carpark_edit_required
def sync_listing(listing_id):
    """Sync stats for a single listing."""
    existing = _pub_service.get_listing(listing_id)
    if not existing:
        return jsonify({'error': 'Listing not found'}), 404
    _, err = _verify_vehicle_ownership(existing['vehicle_id'])
    if err:
        return err

    listing = _pub_service.sync_listing_stats(listing_id)
    return jsonify({'listing': _serialize(listing)})


# ═══════════════════════════════════════════════
# SYNC LOG
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/sync-log', methods=['GET'])
@login_required
@carpark_required
def vehicle_sync_log(vehicle_id):
    """Get sync log for a vehicle."""
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err
    log = _pub_service.get_sync_log(vehicle_id=vehicle_id)
    return jsonify({'log': _serialize(log)})
