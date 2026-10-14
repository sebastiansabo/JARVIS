"""Data access for buyback_photos (vehicle photo gallery on a buyback
record), plus a base64-upload helper that pushes decoded images to Spaces.

Mirrors carpark/repositories/photo_repository.py's BaseRepository style
(raw parameterized SQL via self.query_one/self.query_all/self.execute) and
its injection posture — every value is %s-bound; no caller-influenced value
is ever interpolated into SQL text.
"""
import base64
from typing import Optional, Dict, Any, List
from uuid import uuid4

from core.base_repository import BaseRepository
from core.services import spaces_service

# Document MIME allowlist + file extension. SECURITY: only safe-to-serve types
# are accepted — PDF and raster images. Deliberately EXCLUDES text/html and
# image/svg+xml (both can carry executable script): a stored document is served
# back by the download route, so an attacker-controlled Content-Type like
# text/html would be a stored-XSS vector. Anything not in this map is rejected.
_EXT_BY_MIME = {
    'application/pdf': 'pdf',
    'image/jpeg': 'jpg', 'image/jpg': 'jpg', 'image/png': 'png',
    'image/webp': 'webp', 'image/gif': 'gif',
}

# photo_type values a client may assign to an uploaded document — anything else
# is clamped to the generic 'document' so a caller can't inject arbitrary types.
_DOC_TYPES = {'document', 'civ', 'talon'}


def _parse_data_url(value: str):
    """('data:<mime>;base64,<payload>') -> (bytes, mime).

    SECURITY: rejects any non-`data:` string so a bare Spaces key is NEVER
    fetched — same cross-tenant-copy guard as store_base64_images (a caller
    must not be able to copy another tenant's private object into their record
    by naming its key). Raises ValueError on a malformed value.
    """
    if not isinstance(value, str) or not value.startswith('data:'):
        raise ValueError('documents must be data: URLs')
    header, _, payload = value.partition(',')
    mime = (header[5:].split(';')[0].strip().lower()) or 'application/octet-stream'
    try:
        data = base64.b64decode(payload)
    except Exception:
        raise ValueError('invalid base64 document')
    return data, mime


class PhotoRepository(BaseRepository):
    """Data access for buyback record photos."""

    def get_by_record(self, record_id: int,
                       photo_type: str = None) -> List[Dict[str, Any]]:
        """List photos for a record, optionally filtered by type.

        Soft-deleted photos (deleted_at set) are excluded.
        """
        sql = 'SELECT * FROM buyback_photos WHERE record_id = %s AND deleted_at IS NULL'
        params: list = [record_id]
        if photo_type:
            sql += ' AND photo_type = %s'
            params.append(photo_type)
        sql += ' ORDER BY sort_order, id'
        return self.query_all(sql, tuple(params))

    def create(self, record_id: int, url: str,
               thumbnail_url: str = None,
               photo_type: str = 'gallery',
               is_primary: bool = None,
               caption: str = None,
               file_size: int = None) -> Dict[str, Any]:
        """Add a photo to a record."""
        # If this is set as primary, unset others first
        if is_primary:
            self.execute(
                'UPDATE buyback_photos SET is_primary = FALSE WHERE record_id = %s',
                (record_id,)
            )

        # Get next sort_order
        row = self.query_one(
            'SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order FROM buyback_photos WHERE record_id = %s',
            (record_id,)
        )
        next_order = row['next_order'] if row else 0

        return self.execute('''
            INSERT INTO buyback_photos
                (record_id, url, thumbnail_url, sort_order, is_primary, photo_type, file_size, caption)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        ''', (record_id, url, thumbnail_url, next_order, bool(is_primary),
              photo_type, file_size, caption), returning=True)

    def reorder(self, record_id: int, photo_ids: List[int]) -> bool:
        """Batch reorder photos by setting sort_order from the array index."""
        def _work(cursor):
            for idx, pid in enumerate(photo_ids):
                cursor.execute(
                    'UPDATE buyback_photos SET sort_order = %s WHERE id = %s AND record_id = %s',
                    (idx, pid, record_id)
                )
            return True
        return self.execute_many(_work)

    def soft_delete(self, photo_ids: List[int], record_id: int = None) -> int:
        """Mark photos deleted (hidden immediately). Returns count.

        When `record_id` is given, only photos on that record are affected
        (ownership scoping for the bulk endpoint)."""
        if not photo_ids:
            return 0
        sql = ('UPDATE buyback_photos SET deleted_at = now() '
               'WHERE id = ANY(%s) AND deleted_at IS NULL')
        params: list = [list(photo_ids)]
        if record_id is not None:
            sql += ' AND record_id = %s'
            params.append(record_id)
        return self.execute(sql, tuple(params))

    def get_by_id(self, photo_id: int) -> Optional[Dict[str, Any]]:
        """Get a single photo by ID."""
        return self.query_one(
            'SELECT * FROM buyback_photos WHERE id = %s', (photo_id,)
        )

    def store_base64_images(self, record_id: int, images: List[str],
                             max_bytes: int) -> List[Dict[str, Any]]:
        """Decode a batch of base64 data-URL image values, upload each to
        Spaces under the record's prefix, and create a buyback_photos row
        per image.

        SECURITY: every entry MUST be a `data:` URL — a bare string is
        rejected, NOT treated as an existing Spaces key. spaces_service.
        resolve_image_bytes() would otherwise happily `fetch()` any
        non-`data:` string as a Spaces object key, letting a caller copy
        another tenant's private object (e.g. another company's
        `private/carpark/<id>/...` photo) into their own gallery just by
        naming its key in `images[]`. This check runs as its own pass,
        BEFORE any entry is decoded/fetched, so a single bad entry never
        triggers a live Spaces fetch for ANY image in the batch (all-or-
        nothing, mirrors the size-cap check below).

        The combined decoded size of the whole batch is checked against
        `max_bytes` BEFORE any upload happens, so an oversized batch never
        partially writes to Spaces or the DB.

        The first image becomes `is_primary` only when the record's gallery
        is currently empty (i.e. this call is populating it from scratch).
        """
        for img in images:
            if not isinstance(img, str) or not img.startswith('data:'):
                raise ValueError('images must be data: URLs')

        decoded = [spaces_service.resolve_image_bytes(img) for img in images]
        total = sum(len(data) for data in decoded if data)
        if total > max_bytes:
            raise ValueError('payload too large')

        gallery_empty = len(self.get_by_record(record_id)) == 0

        created = []
        for idx, data in enumerate(decoded):
            key = f'private/buyback/{record_id}/{uuid4().hex}.jpg'
            # public-read: buyback photos are served off the Spaces CDN edge.
            spaces_service.upload(data, key, 'image/jpeg', acl='public-read')
            is_primary = gallery_empty and idx == 0
            created.append(self.create(
                record_id, url=key, is_primary=is_primary, file_size=len(data)
            ))
        return created

    def store_documents(self, record_id: int, documents: List[Dict[str, Any]],
                         max_bytes: int) -> List[Dict[str, Any]]:
        """Decode a batch of base64 data-URL documents (PDFs or image docs),
        upload each PRIVATE to Spaces, and create a buyback_photos row per
        document (photo_type 'document'/'civ'/'talon', never 'gallery').

        Unlike store_base64_images, documents are stored with acl='private'
        (they can carry personal data — owner name/address, VIN) and keep
        their real content-type + extension; they are served only through the
        authenticated download route, never the public CDN. The same
        data:-URL-only guard applies (a bare key is rejected, never fetched),
        and the combined decoded size is checked against `max_bytes` BEFORE
        any upload so an oversized batch never partially writes.

        Each `documents` entry: {data: data-URL, photo_type?: str,
        caption?: str}. `is_primary` is never set for a document.
        """
        parsed = []
        for d in documents:
            data, mime = _parse_data_url(d.get('data'))
            # SECURITY: reject any MIME not on the safe allowlist (no text/html,
            # no image/svg+xml) BEFORE upload — these are served back to users.
            if mime not in _EXT_BY_MIME:
                raise ValueError(f'unsupported document type: {mime!r}')
            parsed.append((data, mime, d))

        total = sum(len(data) for data, _, _ in parsed)
        if total > max_bytes:
            raise ValueError('payload too large')

        created = []
        for data, mime, d in parsed:
            ext = _EXT_BY_MIME.get(mime, 'bin')
            key = f'private/buyback/{record_id}/doc-{uuid4().hex}.{ext}'
            spaces_service.upload(data, key, mime, acl='private')
            photo_type = d.get('photo_type') if d.get('photo_type') in _DOC_TYPES else 'document'
            created.append(self.create(
                record_id, url=key, photo_type=photo_type,
                caption=d.get('caption'), file_size=len(data),
            ))
        return created
