"""Photo API routes — Upload, reorder, delete vehicle photos."""
import io
import logging
import uuid

from flask import request, jsonify
from flask_login import login_required, current_user
from PIL import Image, ImageOps, UnidentifiedImageError

from carpark import carpark_bp
from carpark.repositories.photo_repository import PhotoRepository
from carpark.routes.vehicles import (
    carpark_required, carpark_edit_required, _serialize, _verify_vehicle_ownership,
)
from core.services import spaces_service

logger = logging.getLogger('jarvis.carpark')

_photo_repo = PhotoRepository()

VALID_PHOTO_TYPES = {'gallery', 'interior_360', 'exterior_360'}
MAX_BATCH_PHOTOS = 50
# Upload hardening (multipart /photos/upload route only):
MAX_PHOTO_SIZE = 15 * 1024 * 1024  # 15 MB per file (matches DMS/statements norm)
MAX_PHOTO_PIXELS = 50_000_000      # decompression-bomb guard (~50 MP source)


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
# PHOTOS — UPLOAD (multipart → private Spaces)
# ═══════════════════════════════════════════════

class _InvalidImage(Exception):
    """Client-input image error (undecodable or decompression-bomb-sized).

    Carries an HTTP status (400 by default) so the route can surface a 4xx —
    a bad upload must never fall through to the global 500 handler.
    """

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def _compress_jpeg(raw: bytes, max_px: int = 1600, q: int = 80) -> bytes:
    """Re-encode arbitrary image bytes as a size-capped, EXIF-corrected JPEG.

    Raises _InvalidImage on undecodable input or a decompression-bomb-sized
    source so callers can map it to a 4xx (never a 500).
    """
    try:
        im = Image.open(io.BytesIO(raw))
    except (UnidentifiedImageError, OSError, ValueError) as e:
        raise _InvalidImage('Invalid image file') from e

    # Decompression-bomb guard: reject absurd source dimensions from the header
    # BEFORE decoding pixels (im.size reads the header, not the pixel buffer).
    w, h = im.size
    if w * h > MAX_PHOTO_PIXELS:
        raise _InvalidImage('Image dimensions too large')

    try:
        im = ImageOps.exif_transpose(im).convert('RGB')
        im.thumbnail((max_px, max_px), Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, 'JPEG', quality=q, optimize=True, progressive=True)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as e:
        raise _InvalidImage('Invalid image file') from e
    return out.getvalue()


@carpark_bp.route('/vehicles/<int:vehicle_id>/photos/upload', methods=['POST'])
@login_required
@carpark_edit_required
def upload_photos(vehicle_id):
    """Accept multipart image file(s), compress, upload PRIVATE to Spaces,
    and store the returned key (never raw bytes or a public URL) in
    carpark_vehicle_photos.url.

    Multipart fields: `files` (list) and/or `file` (single).

    Hardening: per-file size cap (MAX_PHOTO_SIZE), batch count cap
    (MAX_BATCH_PHOTOS), decompression-bomb guard (MAX_PHOTO_PIXELS), 4xx on a
    non-image upload, and all-or-nothing semantics — every file is validated
    and compressed BEFORE anything is written, and a mid-batch failure rolls
    back this request's Spaces objects + DB rows.
    """
    # SECURITY: Verify vehicle belongs to user's company
    _, err = _verify_vehicle_ownership(vehicle_id)
    if err:
        return err

    files = request.files.getlist('files')
    if 'file' in request.files:
        files.append(request.files['file'])
    if not files:
        return jsonify({'success': False, 'error': 'No file'}), 400
    if len(files) > MAX_BATCH_PHOTOS:
        return jsonify({'success': False,
                        'error': f'Max {MAX_BATCH_PHOTOS} files per upload'}), 400

    if not spaces_service.is_enabled():
        return jsonify({'success': False, 'error': 'Storage not configured'}), 503

    # ── Phase 1: read + validate + compress EVERY file first. Writes NOTHING
    # to Spaces or the DB until all files pass, so one bad file in a batch can
    # never orphan a half-uploaded set. Client-input errors return a 4xx here.
    payloads = []
    for fs in files:
        raw = fs.read()
        if len(raw) > MAX_PHOTO_SIZE:
            return jsonify({'success': False,
                            'error': f'File too large (max {MAX_PHOTO_SIZE // (1024 * 1024)} MB)'}), 413
        try:
            payloads.append(_compress_jpeg(raw))
        except _InvalidImage as e:
            return jsonify({'success': False, 'error': e.message}), e.status

    # Only the first photo uploaded for a vehicle with no existing photos
    # becomes primary — never overrides an already-set primary photo.
    existing = _photo_repo.get_by_vehicle(vehicle_id)
    make_primary = len(existing) == 0

    # ── Phase 2: upload + insert. On ANY mid-batch failure, best-effort roll
    # back THIS request's Spaces objects + DB rows so the request stays
    # all-or-nothing, then surface a clean 500.
    created = []
    uploaded_keys = []
    try:
        for i, data in enumerate(payloads):
            key = f'private/carpark/{vehicle_id}/{uuid.uuid4().hex}.jpg'
            spaces_service.upload(data, key, 'image/jpeg')
            uploaded_keys.append(key)
            photo = _photo_repo.create(
                vehicle_id=vehicle_id,
                url=key,
                photo_type='gallery',
                is_primary=(make_primary and i == 0),
                file_size=len(data),
            )
            created.append(photo)
    except Exception:
        logger.exception(
            'Photo upload failed for vehicle %s — rolling back %d object(s), %d row(s)',
            vehicle_id, len(uploaded_keys), len(created))
        for photo in created:
            pid = photo.get('id') if isinstance(photo, dict) else None
            if pid is None:
                continue
            try:
                _photo_repo.delete(pid)
            except Exception:
                logger.exception('Rollback: failed to delete photo row %r', pid)
        for key in uploaded_keys:
            try:
                spaces_service.delete(key)
            except Exception:
                logger.exception('Rollback: failed to delete Spaces object %s', key)
        return jsonify({'success': False, 'error': 'Upload failed'}), 500

    return jsonify({'photos': _serialize(created)}), 201


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
