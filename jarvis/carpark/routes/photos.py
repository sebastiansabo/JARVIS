"""Photo API routes — Upload, reorder, delete vehicle photos."""
import logging

from flask import request, jsonify
from flask_login import login_required, current_user

from carpark import carpark_bp
from carpark.repositories.photo_repository import PhotoRepository
from carpark.routes.vehicles import (
    carpark_required, carpark_edit_required, _serialize, _verify_vehicle_ownership,
)

logger = logging.getLogger('jarvis.carpark')

_photo_repo = PhotoRepository()

VALID_PHOTO_TYPES = {'gallery', 'interior_360', 'exterior_360'}
MAX_BATCH_PHOTOS = 50


def _validate_url(url: str) -> bool:
    """Validate that a photo URL uses an acceptable scheme."""
    return isinstance(url, str) and url.startswith(('https://', 'http://'))


# ═══════════════════════════════════════════════
# PHOTOS — LIST
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/photos', methods=['GET'])
@login_required
@carpark_required
def list_photos(vehicle_id):
    """List photos for a vehicle. Optional query: ?type=gallery|interior_360|exterior_360"""
    # SECURITY: Verify vehicle belongs to user's company
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err

    photo_type = request.args.get('type')
    if photo_type and photo_type not in VALID_PHOTO_TYPES:
        return jsonify({'success': False, 'error': 'Invalid photo type'}), 400
    photos = _photo_repo.get_by_vehicle(vehicle_id, photo_type)
    return jsonify({'photos': _serialize(photos)})


# ═══════════════════════════════════════════════
# PHOTOS — ADD
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/photos', methods=['POST'])
@login_required
@carpark_edit_required
def add_photo(vehicle_id):
    """Add a photo to a vehicle.

    Body JSON: { url, thumbnail_url?, photo_type?, is_primary?, caption?, file_size? }
    For batch: { photos: [{ url, ... }, ...] }
    """
    # SECURITY: Verify vehicle belongs to user's company
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'error': 'Request body required'}), 400

    # Batch mode
    if 'photos' in data and isinstance(data['photos'], list):
        if len(data['photos']) > MAX_BATCH_PHOTOS:
            return jsonify({'success': False, 'error': f'Max {MAX_BATCH_PHOTOS} photos per batch'}), 400

        results = []
        for item in data['photos']:
            if not item.get('url'):
                continue
            if not _validate_url(item['url']):
                continue
            photo_type = item.get('photo_type', 'gallery')
            if photo_type not in VALID_PHOTO_TYPES:
                photo_type = 'gallery'
            photo = _photo_repo.create(
                vehicle_id=vehicle_id,
                url=item['url'],
                photo_type=photo_type,
                thumbnail_url=item.get('thumbnail_url'),
                is_primary=item.get('is_primary', False),
                file_size=item.get('file_size'),
                caption=item.get('caption'),
            )
            results.append(photo)
        return jsonify({'photos': _serialize(results)}), 201

    # Single photo
    if not data.get('url'):
        return jsonify({'success': False, 'error': 'url is required'}), 400
    if not _validate_url(data['url']):
        return jsonify({'success': False, 'error': 'Invalid URL scheme'}), 400

    photo_type = data.get('photo_type', 'gallery')
    if photo_type not in VALID_PHOTO_TYPES:
        return jsonify({'success': False, 'error': f'Invalid photo_type. Allowed: {", ".join(VALID_PHOTO_TYPES)}'}), 400

    photo = _photo_repo.create(
        vehicle_id=vehicle_id,
        url=data['url'],
        photo_type=photo_type,
        thumbnail_url=data.get('thumbnail_url'),
        is_primary=data.get('is_primary', False),
        file_size=data.get('file_size'),
        caption=data.get('caption'),
    )
    return jsonify({'photo': _serialize(photo)}), 201


# ═══════════════════════════════════════════════
# PHOTOS — UPDATE
# ═══════════════════════════════════════════════

@carpark_bp.route('/photos/<int:photo_id>', methods=['PUT'])
@login_required
@carpark_edit_required
def update_photo(photo_id):
    """Update photo metadata (sort_order, is_primary, caption, photo_type)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'error': 'Request body required'}), 400

    # Validate photo_type if provided
    if 'photo_type' in data and data['photo_type'] not in VALID_PHOTO_TYPES:
        return jsonify({'success': False, 'error': f'Invalid photo_type. Allowed: {", ".join(VALID_PHOTO_TYPES)}'}), 400

    photo = _photo_repo.update(photo_id, data)
    if not photo:
        return jsonify({'error': 'Photo not found'}), 404
    return jsonify({'photo': _serialize(photo)})


# ═══════════════════════════════════════════════
# PHOTOS — REORDER
# ═══════════════════════════════════════════════

@carpark_bp.route('/vehicles/<int:vehicle_id>/photos/reorder', methods=['PUT'])
@login_required
@carpark_edit_required
def reorder_photos(vehicle_id):
    """Batch reorder photos. Body: { photo_ids: [1, 3, 2, ...] }"""
    # SECURITY: Verify vehicle belongs to user's company
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data or not isinstance(data.get('photo_ids'), list):
        return jsonify({'success': False, 'error': 'photo_ids array required'}), 400

    # Validate all IDs are integers
    try:
        photo_ids = [int(pid) for pid in data['photo_ids']]
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'photo_ids must be integers'}), 400

    _photo_repo.reorder(vehicle_id, photo_ids)
    return jsonify({'success': True})


# ═══════════════════════════════════════════════
# PHOTOS — DELETE
# ═══════════════════════════════════════════════

@carpark_bp.route('/photos/<int:photo_id>', methods=['DELETE'])
@login_required
@carpark_edit_required
def delete_photo(photo_id):
    """Delete a single photo."""
    if _photo_repo.delete(photo_id):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Photo not found'}), 404


@carpark_bp.route('/vehicles/<int:vehicle_id>/photos', methods=['DELETE'])
@login_required
@carpark_edit_required
def delete_all_photos(vehicle_id):
    """Delete all photos for a vehicle."""
    # SECURITY: Verify vehicle belongs to user's company
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err

    count = _photo_repo.delete_all(vehicle_id)
    return jsonify({'success': True, 'deleted': count})
