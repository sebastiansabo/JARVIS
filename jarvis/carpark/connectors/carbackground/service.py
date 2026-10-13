"""CarBackground.ai shared constants + SSRF guard.

`_validate_url` guards every server-side download against SSRF (blocks the
cloud-metadata endpoint 169.254.169.254 and RFC1918 pivots): only http(s) to
a publicly-routable host is allowed. `BROWSER_UA` is sent on every outbound
request to CarBackground to dodge Cloudflare's Error-1010 bot block.

`CarBackgroundEnhanceService` below (Task 4) orchestrates generate + store
enhanced photo, reusing the constants and guards Task 3's client needs.
"""
import hashlib
import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger('jarvis.carbackground.service')

CONNECTOR_TYPE = 'carbackground'
DOWNLOAD_TIMEOUT = 60
MAX_IMAGE_BYTES = 50 * 1024 * 1024
BROWSER_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/129.0 Safari/537.36')
_ALLOWED_SCHEMES = ('http', 'https')


class CarBackgroundError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def _validate_url(url):
    p = urlparse(url)
    if p.scheme not in _ALLOWED_SCHEMES:
        raise CarBackgroundError(f'URL scheme not allowed: {url}', 400)
    host = (p.hostname or '').rstrip('.').lower()
    if not host:
        raise CarBackgroundError(f'URL has no host: {url}', 400)
    try:
        infos = socket.getaddrinfo(host, p.port or None)
    except socket.gaierror as e:
        raise CarBackgroundError(f'Cannot resolve host {host}: {e}', 400)
    for *_u, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise CarBackgroundError(f'Blocked non-public host {host} ({ip})', 400)


from carpark.repositories.photo_repository import PhotoRepository
from core.connectors.repositories.connector_repository import ConnectorRepository
from core.services import spaces_service


class CarBackgroundEnhanceService:
    """Orchestrates a CarBackground.ai enhance: fetch original -> generate ->
    compress full + thumbnail -> upload both to Spaces -> drop any stale
    enhanced objects -> persist via PhotoRepository.set_enhanced.
    """

    def __init__(self, client=None, photo_repo=None, repo=None):
        from .client import CarBackgroundClient  # lazy: avoid import cycle
        self._client = client or CarBackgroundClient()
        self._photos = photo_repo or PhotoRepository()
        self._repo = repo or ConnectorRepository()

    def _config(self):
        c = self._repo.get_by_type(CONNECTOR_TYPE) or {}
        cfg = c.get('config') or {}
        if isinstance(cfg, str):
            import json
            try:
                cfg = json.loads(cfg)
            except (ValueError, TypeError):
                cfg = {}
        return cfg

    def house_background_id(self):
        bg = self._config().get('background_id')
        if not bg:
            raise CarBackgroundError('carbackground house background_id not configured', 400)
        return bg

    def preferred_background_ids(self):
        """The curated set of backgrounds editors may pick from. Falls back to
        the single legacy `background_id` so connectors configured before the
        multi-background feature still expose their one house backdrop."""
        cfg = self._config()
        ids = cfg.get('preferred_background_ids')
        if isinstance(ids, list):
            ids = [str(i) for i in ids if i]
            if ids:
                return ids
        bg = cfg.get('background_id')
        return [bg] if bg else []

    def resolve_background_id(self, background_id=None):
        """Pick the background for a generation: an explicit override must be
        one of the preferred backgrounds; absent an override, the house default
        is used."""
        if background_id:
            if background_id not in self.preferred_background_ids():
                raise CarBackgroundError(
                    f'background_id "{background_id}" is not a preferred background', 400)
            return background_id
        return self.house_background_id()

    def enhance_photo(self, photo_id, background_id=None):
        photo = self._photos.get_by_id(photo_id)
        if not photo:
            raise CarBackgroundError('photo not found', 404)
        bg = self.resolve_background_id(background_id)
        raw = spaces_service.resolve_image_bytes(photo['url'])
        out = self._client.generate(raw, bg)
        # reuse the gallery compressors (validates it's a decodable image)
        from carpark.routes.photos import _compress_jpeg, _InvalidImage, THUMB_MAX_PX, THUMB_QUALITY
        try:
            data = _compress_jpeg(out)
            thumb = _compress_jpeg(out, max_px=THUMB_MAX_PX, q=THUMB_QUALITY)
        except _InvalidImage as e:
            raise CarBackgroundError(getattr(e, 'message', str(e)), 422)
        vid = photo['vehicle_id']; stem = hashlib.sha256(data).hexdigest()[:16]
        key = f'private/carpark/{vid}/enhanced_{stem}.jpg'
        tkey = f'private/carpark/{vid}/enhanced_{stem}_thumb.jpg'
        spaces_service.upload(data, key, 'image/jpeg')
        spaces_service.upload(thumb, tkey, 'image/jpeg')
        for old in (photo.get('enhanced_url'), photo.get('enhanced_thumbnail_url')):
            if old and old != key and old != tkey:
                try:
                    spaces_service.delete(old)
                except Exception:
                    logger.warning('carbackground: stale enhanced delete failed: %s', old)
        return self._photos.set_enhanced(photo_id, key, tkey, bg)
