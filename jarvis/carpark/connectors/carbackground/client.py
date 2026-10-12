"""CarBackground.ai REST client — generate, list backgrounds, check credits.

Every outbound call sends `BROWSER_UA` (Cloudflare Error-1010 guard), and
`_download` re-validates every URL/redirect hop against SSRF via
`service._validate_url` before following it.
"""
import base64
import logging

import requests

from core.connectors.repositories.connector_repository import ConnectorRepository
from . import service
from .service import (CONNECTOR_TYPE, CarBackgroundError,
                      MAX_IMAGE_BYTES, DOWNLOAD_TIMEOUT, BROWSER_UA)

logger = logging.getLogger('jarvis.carbackground.client')
DEFAULT_BASE_URL = 'https://api.carbackground.ai/v1'


def _as_dict(v):
    import json
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (ValueError, TypeError):
            return {}
    return v or {}


class CarBackgroundClient:
    def __init__(self, repo=None):
        self._repo = repo or ConnectorRepository()
        self._session = requests.Session()

    def _conn(self):
        c = self._repo.get_by_type(CONNECTOR_TYPE)
        if not c:
            raise CarBackgroundError('carbackground connector not configured', 400)
        return c

    def _creds_cfg(self):
        c = self._conn()
        return _as_dict(c.get('credentials')), _as_dict(c.get('config'))

    def _base_url(self):
        _, cfg = self._creds_cfg()
        return (cfg.get('api_base_url') or DEFAULT_BASE_URL).rstrip('/')

    def _headers(self):
        creds, _ = self._creds_cfg()
        key = creds.get('api_key')
        if not key:
            raise CarBackgroundError('carbackground API key not configured', 400)
        return {'Authorization': f'Bearer {key}', 'User-Agent': BROWSER_UA}

    def _raise_for(self, r):
        if r.status_code == 401:
            raise CarBackgroundError('carbackground: invalid API key', 401)
        if r.status_code == 402:
            raise CarBackgroundError('carbackground: out of credits', 402)
        if r.status_code == 422:
            raise CarBackgroundError('carbackground: invalid image/params', 422)
        if r.status_code != 200:
            raise CarBackgroundError(f'carbackground {r.status_code}', 502)

    def credits(self):
        r = self._session.get(f'{self._base_url()}/credits', headers=self._headers(), timeout=DOWNLOAD_TIMEOUT)
        self._raise_for(r)
        return (r.json() or {}).get('balance')

    def list_backgrounds(self):
        r = self._session.get(f'{self._base_url()}/backgrounds', headers=self._headers(), timeout=DOWNLOAD_TIMEOUT)
        self._raise_for(r)
        return (r.json() or {}).get('data', [])

    def generate(self, image_bytes, background_id):
        b64 = base64.b64encode(image_bytes).decode()
        r = self._session.post(f'{self._base_url()}/generations', headers=self._headers(),
                               json={'image_base64': b64, 'background_id': background_id},
                               timeout=DOWNLOAD_TIMEOUT)
        self._raise_for(r)
        url = (r.json() or {}).get('image_url')
        if not url:
            raise CarBackgroundError('carbackground: no image_url in response', 502)
        return self._download(url)

    def _download(self, url):
        # NOTE: do NOT send the Authorization bearer here. `current` is seeded
        # from the API's image_url (a presigned storage URL on a *different*
        # host than api_base_url) and rewritable by any redirect Location.
        # _validate_url only blocks private/metadata IPs, not arbitrary public
        # hosts, so sending the key here would leak it off-host. Presigned URLs
        # need no bearer — only the Cloudflare UA guard.
        dl_headers = {'User-Agent': BROWSER_UA}
        current, r = url, None
        for _hop in range(5):
            service._validate_url(current)  # re-validated on every redirect hop; module-qualified so tests can mock it
            r = self._session.get(current, headers=dl_headers, stream=True,
                                  timeout=DOWNLOAD_TIMEOUT, allow_redirects=False)
            if r.is_redirect or 300 <= r.status_code < 400:
                loc = r.headers.get('Location')
                if not loc:
                    raise CarBackgroundError('carbackground download: redirect without Location', 502)
                current = requests.compat.urljoin(current, loc)
                continue
            break
        else:
            raise CarBackgroundError('carbackground download: too many redirects', 502)
        if r.status_code != 200:
            raise CarBackgroundError(f'carbackground download {r.status_code}', 502)
        buf = bytearray()
        for chunk in r.iter_content(64 * 1024):
            buf.extend(chunk)
            if len(buf) > MAX_IMAGE_BYTES:
                raise CarBackgroundError('image too large', 413)
        return bytes(buf)
