"""AutoFox outbound REST client — pull processed vehicle images.

Read-only integration: authenticate with the account's login_token, query
processed image conversions by VIN, and download the final image bytes.

Credentials live in the `connectors` store (config/credentials JSON), never in
code — the JARVIS repo is public. Contract confirmed against AutoFox's OpenAPI
(https://api.autofox.ai/dealer-swagger):
    POST /auth/login-mobile        form: login_token  -> {status, data:{access_token,...}}
    GET  /vehicle-image-conversions?vin=&only_latest_per_vehicle=&is_success=  (Bearer)
    per record: id, vehicle_id, vin, file_converted/file_retouched, retouch_state, date_modified
"""
import json
import logging
from typing import Any, Dict, List, Optional

import requests

from core.connectors.repositories.connector_repository import ConnectorRepository
from .service import (CONNECTOR_TYPE, AutofoxIngestError, _validate_url,
                      MAX_IMAGE_BYTES, DOWNLOAD_TIMEOUT)

logger = logging.getLogger('jarvis.autofox.client')

DEFAULT_BASE_URL = 'https://api.autofox.ai'
LOGIN_PATH = '/auth/login-mobile'
LIST_PATH = '/vehicle-image-conversions'
PER_PAGE = 100
MAX_PAGES = 50

# The list envelope is documented as {status, data: <object|array>}; be tolerant
# about where the array of records actually sits.
_LIST_CONTAINER_KEYS = ('data', 'items', 'results', 'records', 'rows', 'conversions')


def _extract_list(obj: Any, depth: int = 0) -> List[dict]:
    if depth > 4:
        return []
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        for k in _LIST_CONTAINER_KEYS:
            if isinstance(obj.get(k), list):
                return [x for x in obj[k] if isinstance(x, dict)]
        for v in obj.values():
            if isinstance(v, (list, dict)):
                found = _extract_list(v, depth + 1)
                if found:
                    return found
    return []


def _as_dict(v) -> dict:
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (json.JSONDecodeError, TypeError):
            return {}
    return v or {}


class AutofoxClient:
    """Thin authenticated client over the AutoFox dealer API."""

    def __init__(self, repo: ConnectorRepository = None):
        self._repo = repo or ConnectorRepository()
        self._token: Optional[str] = None
        self._session = requests.Session()

    # ── config / credentials (from the connectors store) ──

    def _connector(self) -> dict:
        c = self._repo.get_by_type(CONNECTOR_TYPE)
        if not c:
            raise AutofoxIngestError('AutoFox connector not configured', 400)
        return c

    def _creds_cfg(self):
        c = self._connector()
        return _as_dict(c.get('credentials')), _as_dict(c.get('config'))

    def _base_url(self) -> str:
        _, cfg = self._creds_cfg()
        return (cfg.get('api_base_url') or DEFAULT_BASE_URL).rstrip('/')

    def absolute_url(self, path: str) -> str:
        """Resolve a (possibly relative) AutoFox media path to an absolute URL.

        The API returns ``file_converted``/``file_retouched`` as paths relative
        to the base host (e.g. ``media/vehicle-images/…`), so they must be
        prefixed before download/display."""
        if path.startswith(('http://', 'https://')):
            return path
        return f"{self._base_url()}/{path.lstrip('/')}"

    # ── auth ──

    def login(self) -> str:
        creds, _ = self._creds_cfg()
        login_token = creds.get('login_token')
        if not login_token:
            raise AutofoxIngestError('AutoFox API login_token not configured', 400)
        try:
            r = self._session.post(f'{self._base_url()}{LOGIN_PATH}',
                                   data={'login_token': login_token},
                                   timeout=DOWNLOAD_TIMEOUT)
        except requests.RequestException as e:
            raise AutofoxIngestError(f'AutoFox login request failed: {e}', 502)
        if r.status_code != 200:
            raise AutofoxIngestError(f'AutoFox login rejected ({r.status_code})', 502)
        token = (_as_dict(r.json().get('data')) if isinstance(r.json(), dict) else {}).get('access_token')
        if not token:
            raise AutofoxIngestError('AutoFox login: no access_token in response', 502)
        self._token = token
        return token

    def _auth_headers(self) -> dict:
        if not self._token:
            self.login()
        return {'Authorization': f'Bearer {self._token}'}

    def _get(self, path: str, params: dict = None) -> dict:
        url = f'{self._base_url()}{path}'
        r = self._session.get(url, params=params, headers=self._auth_headers(),
                              timeout=DOWNLOAD_TIMEOUT)
        if r.status_code == 401:  # token expired → re-auth once
            self._token = None
            r = self._session.get(url, params=params, headers=self._auth_headers(),
                                  timeout=DOWNLOAD_TIMEOUT)
        if r.status_code != 200:
            raise AutofoxIngestError(f'AutoFox {path} → {r.status_code}', 502)
        body = r.json()
        return body if isinstance(body, dict) else {'data': body}

    # ── queries ──

    def list_conversions_by_vin(self, vin: str) -> List[Dict[str, Any]]:
        """Normalised processed conversions for a VIN, newest per vehicle.

        Returns [{conversion_id, url, retouch_state, date_modified, vin}].
        """
        vin = (vin or '').strip()
        if not vin:
            return []
        out: List[Dict[str, Any]] = []
        for page in range(1, MAX_PAGES + 1):
            body = self._get(LIST_PATH, {
                'vin': vin,
                'only_latest_per_vehicle': 'true',
                'is_success': 'true',
                'page': page,
                'per_page': PER_PAGE,
            })
            rows = _extract_list(body.get('data', body))
            if not rows:
                break
            for row in rows:
                norm = self._normalise(row, vin)
                if norm:
                    norm['url'] = self.absolute_url(norm['path'])
                    out.append(norm)
            if len(rows) < PER_PAGE:
                break
        # newest first (the API rejects sort_by=date_modified, so sort here)
        out.sort(key=lambda r: r.get('date_modified') or '', reverse=True)
        return out

    @staticmethod
    def _normalise(row: dict, vin: str) -> Optional[Dict[str, Any]]:
        cid = row.get('id')
        # prefer the retouched (final) render, else the converted one; the API
        # returns these as paths relative to the base host
        path = row.get('file_retouched') or row.get('file_converted') or row.get('file')
        if cid is None or not path:
            return None
        return {
            'conversion_id': str(cid),
            'path': path,
            'retouch_state': row.get('retouch_state'),
            'date_modified': row.get('date_modified'),
            'vin': row.get('vin') or vin,
        }

    # ── download ──

    def download(self, url: str) -> bytes:
        """Fetch image bytes for a permanent conversion URL (Bearer, or the
        account's image_access_id for tokenless access).

        SSRF-guarded and size-capped. Redirects are followed manually and
        EVERY hop is re-validated with `_validate_url`, so a redirect from a
        public URL to an internal host (cloud metadata, RFC1918) is blocked
        rather than silently followed by requests.
        """
        creds, _ = self._creds_cfg()
        access_id = creds.get('image_access_id')
        params = {'image_access_id': access_id} if access_id else None
        current = url
        reauthed = False
        r = None
        for _hop in range(5):
            _validate_url(current)  # re-checked on redirect targets too
            try:
                r = self._session.get(current, headers=self._auth_headers(), params=params,
                                      stream=True, timeout=DOWNLOAD_TIMEOUT, allow_redirects=False)
            except requests.RequestException as e:
                raise AutofoxIngestError(f'AutoFox image download failed: {e}', 502)
            if r.status_code == 401 and not reauthed:
                self._token = None
                reauthed = True
                continue  # retry same URL with a fresh token
            if r.is_redirect or 300 <= r.status_code < 400:
                loc = r.headers.get('Location')
                if not loc:
                    raise AutofoxIngestError('AutoFox download: redirect without Location', 502)
                current = requests.compat.urljoin(current, loc)
                params = None  # only the original AutoFox URL takes image_access_id
                continue
            break
        else:
            raise AutofoxIngestError('AutoFox download: too many redirects', 502)
        try:
            r.raise_for_status()
        except requests.RequestException as e:
            raise AutofoxIngestError(f'AutoFox image download failed: {e}', 502)
        buf = bytearray()
        for chunk in r.iter_content(64 * 1024):
            buf.extend(chunk)
            if len(buf) > MAX_IMAGE_BYTES:
                raise AutofoxIngestError(f'Image exceeds {MAX_IMAGE_BYTES} bytes: {url}', 413)
        return bytes(buf)
