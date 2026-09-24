"""Photo routes — upload/list/reorder/soft-delete buyback record photos.

Mirrors carpark/routes/photos.py's multipart upload route (two-phase
validate-then-upload, `_compress_jpeg` reuse, per-file size cap,
decompression-bomb guard, all-or-nothing rollback of Spaces objects + DB rows
on a mid-batch failure) adapted to a buyback record parent (not a vehicle),
the `buyback_photos` table, and the BUYBACK `PhotoRepository`
(buyback.routes._shared.photos_repo). Unlike carpark's route, this file does
NOT generate a separate thumbnail variant — Task 12's brief only calls for a
single compressed JPEG per upload.

Every route: @login_required + @v2_permission_required('buyback', 'record',
'edit'), loads the parent record (404 if missing) and runs
_shared._guard_company on it (403 on cross-company IDOR) BEFORE anything
else — matching records.py/offers.py/inspection.py's established order.

No SQL lives here — every DB access goes through buyback.routes._shared's
singleton `photos_repo` (buyback.repositories.photo_repository.PhotoRepository).

Unlike carpark's route, this one does NOT gate on spaces_service.is_enabled()
— PhotoRepository.store_base64_images (Task 6) doesn't either, and the test
harness (no DO_SPACES_* creds locally) relies on monkeypatching
spaces_service.upload directly rather than also faking is_enabled().
"""
import logging
import uuid

from flask import request, jsonify
from flask_login import login_required

from buyback import buyback_bp
from buyback.routes import _shared
from carpark.routes.photos import _compress_jpeg, _InvalidImage
from core.roles.decorators import v2_permission_required
from core.services import spaces_service

logger = logging.getLogger('jarvis.buyback')

MAX_BATCH_PHOTOS = 50
MAX_PHOTO_SIZE = 15 * 1024 * 1024  # 15 MB per file — matches carpark's norm


# ═══════════════════════════════════════════════
# UPLOAD (multipart → private Spaces)
# ═══════════════════════════════════════════════

@buyback_bp.route('/records/<int:record_id>/photos/upload', methods=['POST'])
@login_required
@v2_permission_required('buyback', 'record', 'edit')
def upload_photos(record_id):
    """Accept multipart image file(s), compress each to a size-capped JPEG,
    upload PRIVATE to Spaces under private/buyback/<record_id>/<uuid>.jpg,
    and create a buyback_photos row per image.

    Multipart fields: `files` (list) and/or `file` (single).

    Hardening: per-file size cap (MAX_PHOTO_SIZE), batch count cap
    (MAX_BATCH_PHOTOS), decompression-bomb guard (_compress_jpeg's own
    MAX_PHOTO_PIXELS), 4xx on a non-image upload, and all-or-nothing
    semantics — every file is validated and compressed BEFORE anything is
    written, and a mid-batch failure rolls back this request's Spaces
    objects + DB rows.
    """
    record = _shared.records_repo.get_by_id(record_id)
    if not record:
        return jsonify({'success': False, 'error': 'Record not found'}), 404

    err = _shared._guard_company(record)
    if err:
        return err

    files = request.files.getlist('files')
    if 'file' in request.files:
        files.append(request.files['file'])
    # Drop empty/no-filename entries rather than passing them through —
    # mirrors the store_base64_images carry-forward note (Task 6 review):
    # skip falsy/invalid entries instead of letting them error deep in a
    # helper.
    files = [f for f in files if f and f.filename]
    if not files:
        return jsonify({'success': False, 'error': 'No file'}), 400
    if len(files) > MAX_BATCH_PHOTOS:
        return jsonify({'success': False,
                        'error': f'Max {MAX_BATCH_PHOTOS} files per upload'}), 400

    # ── Phase 1: read + validate + compress EVERY file first. Writes
    # NOTHING to Spaces or the DB until all files pass, so one bad file in a
    # batch can never orphan a half-uploaded set. Client-input errors return
    # a 4xx here.
    payloads = []
    for fs in files:
        raw = fs.read()
        if not raw:
            return jsonify({'success': False, 'error': 'Empty file'}), 400
        if len(raw) > MAX_PHOTO_SIZE:
            return jsonify({'success': False,
                            'error': f'File too large (max {MAX_PHOTO_SIZE // (1024 * 1024)} MB)'}), 413
        try:
            payloads.append(_compress_jpeg(raw))
        except _InvalidImage as e:
            return jsonify({'success': False, 'error': e.message}), e.status

    # Only the first photo uploaded for a record with no existing (non
    # soft-deleted) photos becomes primary — never overrides an
    # already-set primary photo.
    existing = _shared.photos_repo.get_by_record(record_id)
    make_primary = len(existing) == 0

    # ── Phase 2: upload + insert. On ANY mid-batch failure, best-effort roll
    # back THIS request's Spaces objects + DB rows so the request stays
    # all-or-nothing, then surface a clean 500.
    created = []
    uploaded_keys = []
    try:
        for i, data in enumerate(payloads):
            key = f'private/buyback/{record_id}/{uuid.uuid4().hex}.jpg'
            spaces_service.upload(data, key, 'image/jpeg')
            uploaded_keys.append(key)
            photo = _shared.photos_repo.create(
                record_id=record_id,
                url=key,
                is_primary=(make_primary and i == 0),
                file_size=len(data),
            )
            created.append(photo)
    except Exception:
        logger.exception(
            'Photo upload failed for buyback record %s — rolling back %d '
            'object(s), %d row(s)', record_id, len(uploaded_keys), len(created))
        for photo in created:
            pid = photo.get('id') if isinstance(photo, dict) else None
            if pid is None:
                continue
            try:
                _shared.photos_repo.soft_delete([pid])
            except Exception:
                logger.exception('Rollback: failed to remove photo row %r', pid)
        for key in uploaded_keys:
            try:
                spaces_service.delete(key)
            except Exception:
                logger.exception('Rollback: failed to delete Spaces object %s', key)
        return jsonify({'success': False, 'error': 'Upload failed'}), 500

    return jsonify({'success': True, 'photos': _shared._serialize(created)}), 201


# ═══════════════════════════════════════════════
# LIST
# ═══════════════════════════════════════════════

@buyback_bp.route('/records/<int:record_id>/photos', methods=['GET'])
@login_required
@v2_permission_required('buyback', 'record', 'edit')
def list_photos(record_id):
    record = _shared.records_repo.get_by_id(record_id)
    if not record:
        return jsonify({'success': False, 'error': 'Record not found'}), 404

    err = _shared._guard_company(record)
    if err:
        return err

    photos = _shared.photos_repo.get_by_record(record_id)
    return jsonify({'photos': _shared._serialize(photos)})


# ═══════════════════════════════════════════════
# REORDER
# ═══════════════════════════════════════════════

@buyback_bp.route('/records/<int:record_id>/photos/reorder', methods=['POST'])
@login_required
@v2_permission_required('buyback', 'record', 'edit')
def reorder_photos(record_id):
    """Batch reorder photos. Body: { ids: [3, 1, 2, ...] }"""
    record = _shared.records_repo.get_by_id(record_id)
    if not record:
        return jsonify({'success': False, 'error': 'Record not found'}), 404

    err = _shared._guard_company(record)
    if err:
        return err

    data = request.get_json(silent=True) or {}
    if not isinstance(data.get('ids'), list):
        return jsonify({'success': False, 'error': 'ids array required'}), 400

    try:
        ids = [int(pid) for pid in data['ids']]
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'ids must be integers'}), 400

    _shared.photos_repo.reorder(record_id, ids)
    return jsonify({'success': True})


# ═══════════════════════════════════════════════
# DELETE (soft)
# ═══════════════════════════════════════════════

@buyback_bp.route('/records/<int:record_id>/photos/<int:photo_id>', methods=['DELETE'])
@login_required
@v2_permission_required('buyback', 'record', 'edit')
def delete_photo(record_id, photo_id):
    """Soft-delete a single photo, scoped to this record (an id belonging
    to a different record is a no-op 404, not a cross-record delete)."""
    record = _shared.records_repo.get_by_id(record_id)
    if not record:
        return jsonify({'success': False, 'error': 'Record not found'}), 404

    err = _shared._guard_company(record)
    if err:
        return err

    count = _shared.photos_repo.soft_delete([photo_id], record_id=record_id)
    if not count:
        return jsonify({'success': False, 'error': 'Photo not found'}), 404
    return jsonify({'success': True})
