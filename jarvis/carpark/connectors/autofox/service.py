"""AutoFox photo service — SSRF-guarded URL validation + pull-import storage.

Shared helpers for the read-only AutoFox pull integration (see client.py):
`_validate_url` guards every server-side download against SSRF, and
`AutofoxIngestService` stores pulled images into `carpark_vehicle_photos`,
tagged by conversion id so a re-sync is idempotent.
"""
import hashlib
import ipaddress
import socket
from typing import Any, Dict
from urllib.parse import urlparse

from carpark.repositories.photo_repository import PhotoRepository
from carpark.repositories.vehicle_repository import VehicleRepository
from core.services import spaces_service

CONNECTOR_TYPE = 'autofox'
DOWNLOAD_TIMEOUT = 30
MAX_IMAGE_BYTES = 15 * 1024 * 1024

_ALLOWED_SCHEMES = ('http', 'https')


class AutofoxIngestError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def _validate_url(url: str) -> None:
    """SSRF guard: only http(s) to a publicly-routable host.

    AutoFox returns image URLs we then fetch server-side, so reject anything
    that resolves to a private / loopback / link-local / reserved / multicast /
    unspecified address (blocks the cloud-metadata endpoint 169.254.169.254 and
    RFC1918 pivots).
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise AutofoxIngestError(f'URL scheme not allowed: {url}', 400)
    host = (parsed.hostname or '').rstrip('.').lower()
    if not host:
        raise AutofoxIngestError(f'URL has no host: {url}', 400)
    try:
        infos = socket.getaddrinfo(host, parsed.port or None)
    except socket.gaierror as e:
        raise AutofoxIngestError(f'Cannot resolve host {host}: {e}', 400)
    for *_unused, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise AutofoxIngestError(f'Blocked non-public host {host} ({ip})', 400)


class AutofoxIngestService:
    """Stores AutoFox-pulled photos into a vehicle's gallery (matched by VIN)."""

    def __init__(self, photo_repo: PhotoRepository = None,
                 vehicle_repo: VehicleRepository = None):
        self._photos = photo_repo or PhotoRepository()
        self._vehicles = vehicle_repo or VehicleRepository()

    def imported_conversion_ids(self, vehicle_id: int) -> set:
        """AutoFox conversion ids already imported for this vehicle.

        Each pulled photo is tagged ``caption = autofox:<conversion_id>`` so a
        re-sync can skip what is already present (the API guide's dedup key).
        """
        ids = set()
        for p in self._photos.get_by_vehicle(vehicle_id):
            cap = p.get('caption') or ''
            if cap.startswith('autofox:'):
                ids.add(cap.split(':', 1)[1])
        return ids

    def store_photo_bytes(self, vehicle_id: int, raw: bytes, conversion_id: str,
                          make_primary: bool = False) -> Dict[str, Any]:
        """Compress + store one pulled image, tagged with its conversion id."""
        from carpark.routes.photos import _compress_jpeg, _InvalidImage  # lazy: circular import
        try:
            data = _compress_jpeg(raw)
        except _InvalidImage as e:
            raise AutofoxIngestError(e.message, 422)
        key = f'private/carpark/{vehicle_id}/autofox_{hashlib.sha256(data).hexdigest()[:16]}.jpg'
        spaces_service.upload(data, key, 'image/jpeg')
        return self._photos.create(
            vehicle_id=vehicle_id, url=key, photo_type='gallery',
            is_primary=make_primary, file_size=len(data),
            caption=f'autofox:{conversion_id}',
        )
