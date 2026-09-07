"""AutoFox ingest service — payload normalisation + photo ingestion.

Pure logic (no Flask). The exact AutoFox push schema is not publicly
documented, so `extract_delivery()` is deliberately tolerant: it hunts for a
VIN and a list of image references across the common key spellings and the
raw payload is always logged so the first real delivery reveals the schema.
"""
import hashlib
import logging
from typing import Any, Dict, List, Optional, Tuple

import requests

from carpark.repositories.photo_repository import PhotoRepository
from carpark.repositories.vehicle_repository import VehicleRepository
from core.services import spaces_service

logger = logging.getLogger('jarvis.autofox')

CONNECTOR_TYPE = 'autofox'
DOWNLOAD_TIMEOUT = 30
MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_IMAGES_PER_DELIVERY = 60

_VIN_KEYS = ('vin', 'VIN', 'Vin', 'fin', 'FIN', 'vehicle_vin', 'vehicleVin',
             'vehicleIdentificationNumber', 'chassis', 'chassis_number')
_LIST_KEYS = ('images', 'photos', 'pictures', 'files', 'media', 'assets',
              'results', 'output', 'outputs', 'data', 'items')
_URL_KEYS = ('url', 'href', 'src', 'image_url', 'imageUrl', 'download_url',
             'downloadUrl', 'link', 'file_url', 'fileUrl', 'cdn_url', 'public_url')
_ID_KEYS = ('id', 'image_id', 'imageId', 'file_id', 'fileId', 'uuid', 'name', 'filename')
_POS_KEYS = ('position', 'pos', 'order', 'sort', 'sort_order', 'index', 'sequence')


class AutofoxIngestError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def _find_vin(obj: Any, depth: int = 0) -> Optional[str]:
    if depth > 4 or not isinstance(obj, dict):
        return None
    for k in _VIN_KEYS:
        v = obj.get(k)
        if isinstance(v, str) and 11 <= len(v.strip()) <= 17:
            return v.strip().upper()
    for v in obj.values():
        if isinstance(v, dict):
            found = _find_vin(v, depth + 1)
            if found:
                return found
    return None


def _norm_image(item: Any, idx: int) -> Optional[Dict[str, Any]]:
    if isinstance(item, str) and item.startswith(('http://', 'https://')):
        return {'url': item, 'source_id': None, 'position': idx}
    if isinstance(item, dict):
        url = next((item[k] for k in _URL_KEYS
                    if isinstance(item.get(k), str) and item[k].startswith(('http://', 'https://'))), None)
        if not url:
            return None
        sid = next((str(item[k]) for k in _ID_KEYS if item.get(k) is not None), None)
        pos = next((item[k] for k in _POS_KEYS if isinstance(item.get(k), (int, float))), idx)
        return {'url': url, 'source_id': sid, 'position': int(pos)}
    return None


def _find_images(obj: Any, depth: int = 0) -> List[Dict[str, Any]]:
    if depth > 4:
        return []
    if isinstance(obj, list):
        out = [n for n in (_norm_image(it, i) for i, it in enumerate(obj)) if n]
        if out:
            return out
        for it in obj:
            found = _find_images(it, depth + 1)
            if found:
                return found
        return []
    if isinstance(obj, dict):
        for k in _LIST_KEYS:
            if k in obj:
                found = _find_images(obj[k], depth + 1)
                if found:
                    return found
        single = _norm_image(obj, 0)
        if single and depth > 0:
            return [single]
        for v in obj.values():
            if isinstance(v, (dict, list)):
                found = _find_images(v, depth + 1)
                if found:
                    return found
    return []


def extract_delivery(payload: Any) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """Return (vin, images[{url, source_id, position}]) from an arbitrary payload."""
    vin = _find_vin(payload)
    images = _find_images(payload)
    images.sort(key=lambda x: x['position'])
    return vin, images[:MAX_IMAGES_PER_DELIVERY]


def _download(url: str) -> bytes:
    r = requests.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True)
    r.raise_for_status()
    buf = bytearray()
    for chunk in r.iter_content(64 * 1024):
        buf.extend(chunk)
        if len(buf) > MAX_IMAGE_BYTES:
            raise AutofoxIngestError(f'Image exceeds {MAX_IMAGE_BYTES} bytes: {url}', 413)
    return bytes(buf)


class AutofoxIngestService:
    def __init__(self, photo_repo: PhotoRepository = None,
                 vehicle_repo: VehicleRepository = None):
        self._photos = photo_repo or PhotoRepository()
        self._vehicles = vehicle_repo or VehicleRepository()

    def ingest(self, vin: str, images: List[Dict[str, Any]],
               raw_blobs: List[bytes] = None,
               replace_existing: bool = False) -> Dict[str, Any]:
        """Store images for the vehicle identified by `vin`.

        `images` are URL refs (downloaded here); `raw_blobs` are bytes already
        received (multipart). Idempotent: key = sha256(bytes)[:16], so a
        re-delivery of the same image is a no-op.
        """
        from carpark.routes.photos import _compress_jpeg, _InvalidImage  # lazy: avoids circular import

        if not vin:
            raise AutofoxIngestError('VIN not found in payload', 422)
        vehicle = self._vehicles.get_by_vin(vin)
        if not vehicle:
            raise AutofoxIngestError(f'No vehicle with VIN {vin}', 404)
        if not spaces_service.is_enabled():
            raise AutofoxIngestError('Storage not configured', 503)

        vehicle_id = vehicle['id']
        blobs: List[bytes] = list(raw_blobs or [])
        errors: List[str] = []
        for img in images:
            try:
                blobs.append(_download(img['url']))
            except AutofoxIngestError as e:
                errors.append(e.message)
            except requests.RequestException as e:
                errors.append(f'download failed: {img["url"]} ({e})')

        existing = self._photos.get_by_vehicle(vehicle_id)
        if replace_existing:
            for p in existing:
                if isinstance(p.get('url'), str) and '/autofox_' in p['url']:
                    try:
                        spaces_service.delete(p['url'])
                    except Exception:
                        logger.exception('AutoFox: failed to delete Spaces object %s', p['url'])
                    self._photos.delete(p['id'])
            existing = self._photos.get_by_vehicle(vehicle_id)

        known = {p['url'] for p in existing}
        make_primary = len(existing) == 0
        created, skipped = [], 0
        for i, raw in enumerate(blobs):
            try:
                data = _compress_jpeg(raw)
            except _InvalidImage as e:
                errors.append(e.message)
                continue
            key = f'private/carpark/{vehicle_id}/autofox_{hashlib.sha256(data).hexdigest()[:16]}.jpg'
            if key in known:
                skipped += 1
                continue
            spaces_service.upload(data, key, 'image/jpeg')
            photo = self._photos.create(
                vehicle_id=vehicle_id, url=key, photo_type='gallery',
                is_primary=(make_primary and not created), file_size=len(data),
                caption='autofox',
            )
            known.add(key)
            created.append(photo)

        return {
            'vehicle_id': vehicle_id, 'vin': vin,
            'received': len(blobs), 'created': len(created),
            'skipped_duplicates': skipped, 'errors': errors,
        }
