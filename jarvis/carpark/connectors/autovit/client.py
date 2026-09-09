"""Autovit.ro API Client — OAuth2 password-grant integration.

Uses the OLX Group / Autovit dealer API:
  Production: https://ssl.autovit.ro/api/open
  Sandbox:    https://autovit.fixeads.com/api/open

Auth flow:
  POST {base}/oauth/token/
  Basic auth header (client_id:client_secret)
  Body: username={email}&password={pwd}&grant_type=password
  → access_token (Bearer, 3600s TTL)
"""
import logging
import time
from typing import Dict, Any, Optional

import requests

from carpark.connectors.base_connector import BaseConnector

logger = logging.getLogger('jarvis.carpark.autovit')

PRODUCTION_URL = 'https://www.autovit.ro/api/open'
SANDBOX_URL = 'https://autovit.fixeads.com/api/open'

TOKEN_TTL_BUFFER = 300  # refresh 5 min before expiry


class AutovitClient:
    """Low-level HTTP client for a single Autovit dealer account."""

    def __init__(self, base_url: str, client_id: str, client_secret: str,
                 username: str, password: str, timeout: int = 15):
        self.base_url = base_url.rstrip('/')
        self.client_id = client_id
        self.client_secret = client_secret
        self.username = username
        self.password = password
        self.timeout = timeout
        self._token: Optional[str] = None
        self._token_expires: float = 0

    def _get_token(self) -> str:
        """Fetch or return cached OAuth2 access token."""
        if self._token and time.time() < self._token_expires:
            return self._token

        url = f'{self.base_url}/oauth/token/'
        resp = requests.post(
            url,
            auth=(self.client_id, self.client_secret),
            data={
                'username': self.username,
                'password': self.password,
                'grant_type': 'password',
            },
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        if 'error' in data:
            raise AutovitAuthError(data.get('error_description', data['error']))

        self._token = data['access_token']
        expires_in = data.get('expires_in', 3600)
        self._token_expires = time.time() + expires_in - TOKEN_TTL_BUFFER
        logger.info('Autovit token acquired for %s (expires in %ds)', self.username, expires_in)
        return self._token

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Authenticated request with auto token refresh."""
        token = self._get_token()
        url = f'{self.base_url}{path}'
        headers = kwargs.pop('headers', {})
        headers['Authorization'] = f'Bearer {token}'
        headers.setdefault('Accept', 'application/json')
        # Autovit's account (password-grant) write endpoints require the dealer
        # account email in the User-Agent header.
        headers.setdefault('User-Agent', self.username)
        if method.upper() in ('POST', 'PUT'):
            headers.setdefault('Content-Type', 'application/json')

        resp = requests.request(method, url, headers=headers, timeout=self.timeout, **kwargs)

        # Token expired mid-flight — retry once
        if resp.status_code == 401:
            self._token = None
            token = self._get_token()
            headers['Authorization'] = f'Bearer {token}'
            resp = requests.request(method, url, headers=headers, timeout=self.timeout, **kwargs)

        resp.raise_for_status()
        return resp

    # ── Public API methods ──

    def health_check(self) -> Dict[str, Any]:
        """Test authentication — returns user/account info or raises."""
        self._get_token()
        # Fetch first page to get total count
        resp = self._request('GET', '/adverts/', params={'page': 1})
        data = resp.json()
        return {
            'success': True,
            'username': self.username,
            'total_adverts': data.get('total_elements', 0),
        }

    def get_adverts(self, page: int = 1, status: str = None) -> Dict[str, Any]:
        """List adverts for this dealer account.

        Args:
            page: Page number (1-based).
            status: Filter by status (e.g. 'active', 'disabled', 'removed_by_user').

        Returns: {results, total_elements, total_pages, current_page, ...}
        """
        params: Dict[str, Any] = {'page': page}
        if status:
            params['status'] = status
        resp = self._request('GET', '/adverts/', params=params)
        return resp.json()

    def get_advert(self, advert_id: str) -> Dict[str, Any]:
        """Get single advert details."""
        resp = self._request('GET', f'/adverts/{advert_id}')
        return resp.json()

    # ── Push (write) methods — Autovit "account" API (password grant) ──
    #
    # IMPORTANT: password-grant (dealer) clients MUST use the /account/adverts
    # endpoints. The bare /adverts endpoints need the partner-only
    # `advertsWrite` permission and return 403 "You are not allowed to post
    # adverts here" for dealer keys. Verified live 2026-09-09: POST
    # /account/adverts -> 201 (status "unpaid" draft); DELETE
    # /account/adverts/{id} -> 204. All write calls carry User-Agent=email
    # (set in _request).

    def create_advert(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new advert (dealer/account endpoint). Returns {id, url, status, ...}.

        Created adverts start in `unpaid` status (a private draft, not visible
        on the marketplace) until paid/activated — safe to create without
        immediately publishing.
        """
        return self._request('POST', '/account/adverts', json=payload).json()

    def update_advert(self, advert_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing advert in place."""
        return self._request('PUT', f'/account/adverts/{advert_id}', json=payload).json()

    def deactivate_advert(self, advert_id: str) -> Dict[str, Any]:
        """Deactivate (unpublish without deleting) an active advert."""
        return self._request('POST', f'/account/adverts/{advert_id}/deactivate', json={}).json()

    def delete_advert(self, advert_id: str) -> Dict[str, Any]:
        """Permanently delete an advert (account endpoint; 204 No Content)."""
        self._request('DELETE', f'/account/adverts/{advert_id}')
        return {'success': True}

    def get_account_advert(self, advert_id: str) -> Dict[str, Any]:
        """Get one of THIS account's adverts — works for unpaid/draft adverts too,
        unlike the public GET /adverts/{id} (which 404s for drafts)."""
        return self._request('GET', f'/account/adverts/{advert_id}').json()

    def create_image_collection(self, image_urls: list) -> Optional[str]:
        """Create an Autovit image collection from public image URLs; returns its
        id for use as `image_collection_id` on an advert (or None if no URLs).

        Photos are optional for advert creation, so callers should treat a
        failure here as non-fatal. Autovit expects images keyed by number:
        ``{"images": {"1": {"source": url}, ...}}``.
        """
        if not image_urls:
            return None
        images = {str(i + 1): {'source': u} for i, u in enumerate(image_urls) if u}
        if not images:
            return None
        resp = self._request('POST', '/imageCollections', json={'images': images})
        return str(resp.json().get('id')) if resp.ok else None


class AutovitConnector(BaseConnector):
    """High-level connector wrapping AutovitClient for marketplace operations."""

    def __init__(self, client: AutovitClient):
        self.client = client

    def publish(self, vehicle_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            resp = self.client._request('POST', '/adverts', json=vehicle_data)
            data = resp.json()
            return {
                'external_id': data.get('id'),
                'external_url': data.get('url'),
                'success': True,
            }
        except Exception as e:
            logger.exception('Autovit publish failed')
            return {'external_id': None, 'external_url': None, 'success': False, 'error': str(e)}

    def update(self, external_id: str, vehicle_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self.client._request('PUT', f'/adverts/{external_id}', json=vehicle_data)
            return {'success': True}
        except Exception as e:
            logger.exception('Autovit update failed')
            return {'success': False, 'error': str(e)}

    def deactivate(self, external_id: str) -> Dict[str, Any]:
        try:
            self.client._request('POST', f'/adverts/{external_id}/deactivate')
            return {'success': True}
        except Exception as e:
            logger.exception('Autovit deactivate failed')
            return {'success': False, 'error': str(e)}

    def delete(self, external_id: str) -> Dict[str, Any]:
        try:
            self.client._request('DELETE', f'/adverts/{external_id}')
            return {'success': True}
        except Exception as e:
            logger.exception('Autovit delete failed')
            return {'success': False, 'error': str(e)}

    def get_stats(self, external_id: str) -> Dict[str, Any]:
        try:
            resp = self.client._request('GET', f'/adverts/{external_id}/stats')
            data = resp.json()
            return {'views': data.get('views', 0), 'inquiries': data.get('inquiries', 0)}
        except Exception:
            return {'views': 0, 'inquiries': 0}

    def health_check(self) -> bool:
        try:
            self.client.health_check()
            return True
        except Exception:
            return False


class AutovitAuthError(Exception):
    """Raised when OAuth2 token acquisition fails."""
    pass
