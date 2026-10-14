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

from flask import request, jsonify, Response
from flask_login import login_required

from buyback import buyback_bp
from buyback.routes import _shared
from carpark.routes.photos import _compress_jpeg, _InvalidImage
from core.roles.decorators import v2_permission_required
from core.services import spaces_service

logger = logging.getLogger('jarvis.buyback')

MAX_BATCH_PHOTOS = 50
MAX_PHOTO_SIZE = 15 * 1024 * 1024  # 15 MB per file — matches carpark's norm
_DOC_TYPES = {'document', 'civ', 'talon'}

# Safe Content-Type per file extension for the download route. Anything not
# here is served as an octet-stream attachment (forced download, never rendered
# inline) — the stored Content-Type is never trusted (stored-XSS defense).
_SAFE_CT_BY_EXT = {
    'pdf': 'application/pdf',
    'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png',
    'webp': 'image/webp', 'gif': 'image/gif',
}


def _is_pdf(fs) -> bool:
    """A multipart part is treated as a (PDF) document when its MIME or
    filename says PDF — everything else goes through the image/_compress_jpeg
    path (which rejects non-images)."""
    mime = (getattr(fs, 'mimetype', '') or '').lower()
    name = (getattr(fs, 'filename', '') or '').lower()
    return mime == 'application/pdf' or name.endswith('.pdf')


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

    # Optional label for PDF documents in this batch (civ/talon from the CIV
    # import; else the generic 'document'). Applies to the document parts only.
    doc_type_req = (request.form.get('doc_type') or '').strip().lower()
    doc_type = doc_type_req if doc_type_req in _DOC_TYPES else 'document'
    _doc_caption = {'civ': 'CIV', 'talon': 'Talon'}.get(doc_type)

    # ── Phase 1: read + validate EVERY file first (images are compressed to
    # JPEG; PDFs are kept as-is as private documents). Writes NOTHING to Spaces
    # or the DB until all files pass, so one bad file in a batch can never
    # orphan a half-uploaded set. Client-input errors return a 4xx here.
    # Each entry: {'kind': 'image'|'document', 'data', 'content_type', 'caption'}.
    payloads = []
    for fs in files:
        raw = fs.read()
        if not raw:
            return jsonify({'success': False, 'error': 'Empty file'}), 400
        if len(raw) > MAX_PHOTO_SIZE:
            return jsonify({'success': False,
                            'error': f'File too large (max {MAX_PHOTO_SIZE // (1024 * 1024)} MB)'}), 413
        if _is_pdf(fs):
            payloads.append({'kind': 'document', 'data': raw,
                             'content_type': 'application/pdf',
                             'caption': _doc_caption or fs.filename})
        else:
            try:
                payloads.append({'kind': 'image', 'data': _compress_jpeg(raw),
                                 'content_type': 'image/jpeg', 'caption': None})
            except _InvalidImage as e:
                return jsonify({'success': False, 'error': e.message}), e.status

    # Only the first IMAGE uploaded for a record with no existing (non
    # soft-deleted) *image* becomes primary — documents never occupy the cover
    # slot nor block the first real image from becoming it, and an already-set
    # primary is never overridden.
    existing = _shared.photos_repo.get_by_record(record_id)
    existing_images = [p for p in existing if (p.get('photo_type') or 'gallery') == 'gallery']
    make_primary = len(existing_images) == 0
    first_image_done = False

    # ── Phase 2: upload + insert. On ANY mid-batch failure, best-effort roll
    # back THIS request's Spaces objects + DB rows so the request stays
    # all-or-nothing, then surface a clean 500.
    created = []
    uploaded_keys = []
    try:
        for p in payloads:
            if p['kind'] == 'document':
                # Documents are PRIVATE (may carry personal data) — served only
                # via the authenticated download route, never the public CDN.
                key = f'private/buyback/{record_id}/doc-{uuid.uuid4().hex}.pdf'
                spaces_service.upload(p['data'], key, p['content_type'], acl='private')
                uploaded_keys.append(key)
                photo = _shared.photos_repo.create(
                    record_id=record_id, url=key, photo_type=doc_type,
                    caption=p['caption'], file_size=len(p['data']),
                )
            else:
                key = f'private/buyback/{record_id}/{uuid.uuid4().hex}.jpg'
                # public-read so the object is served straight off the Spaces CDN
                # edge (buyback photos are intentionally public — see cdn_url).
                spaces_service.upload(p['data'], key, 'image/jpeg', acl='public-read')
                uploaded_keys.append(key)
                is_primary = make_primary and not first_image_done
                first_image_done = True
                photo = _shared.photos_repo.create(
                    record_id=record_id, url=key,
                    is_primary=is_primary, file_size=len(p['data']),
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

    return jsonify({'success': True, 'photos': _shared.serialize_photos(created)}), 201


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
    return jsonify({'photos': _shared.serialize_photos(photos)})


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


# ═══════════════════════════════════════════════
# DOWNLOAD (private document — authenticated)
# ═══════════════════════════════════════════════

@buyback_bp.route('/records/<int:record_id>/photos/<int:photo_id>/download', methods=['GET'])
@login_required
@v2_permission_required('buyback', 'record', 'view')
def download_photo(record_id, photo_id):
    """Stream a record's stored file — used for PRIVATE document tiles (the
    imported CIV/talon PDF and gallery-uploaded PDFs, which are not served off
    the public CDN). Same view-scope + IDOR boundary as the detail GET: the
    photo must belong to this record (an id from another record is a 404, not a
    cross-record read), and the object is fetched server-side from Spaces and
    streamed inline so the browser opens/saves it without any public URL."""
    record = _shared.records_repo.get_by_id(record_id)
    if not record:
        return jsonify({'success': False, 'error': 'Record not found'}), 404

    err = _shared._guard_company(record)
    if err:
        return err

    photo = _shared.photos_repo.get_by_id(photo_id)
    if not photo or photo.get('record_id') != record_id or photo.get('deleted_at'):
        return jsonify({'success': False, 'error': 'Not found'}), 404

    key = photo.get('url')
    try:
        data, _stored_ct = spaces_service.fetch(key)
    except Exception:
        logger.warning('buyback document fetch failed (record %s photo %s key %s)',
                       record_id, photo_id, key, exc_info=True)
        return jsonify({'success': False, 'error': 'File unavailable'}), 502

    # SECURITY: NEVER trust the stored Content-Type when serving back to a
    # browser — derive it from the (server-controlled) file extension against a
    # safe allowlist, send X-Content-Type-Options: nosniff, and only serve
    # known-safe types inline (anything else forces a download). Together these
    # close the stored-XSS vector (an object whose content-type/body is HTML/SVG
    # can never be rendered inline in our origin).
    ext = key.rsplit('.', 1)[-1].lower() if key and '.' in key else 'bin'
    served_ct = _SAFE_CT_BY_EXT.get(ext, 'application/octet-stream')
    disposition = 'inline' if served_ct != 'application/octet-stream' else 'attachment'
    label = photo.get('caption') or 'document'
    safe = ''.join(c for c in str(label) if c.isalnum() or c in ('-', '_')) or 'document'
    return Response(data, mimetype=served_ct, headers={
        'Content-Disposition': f'{disposition}; filename="{safe}.{ext}"',
        'X-Content-Type-Options': 'nosniff',
    })
