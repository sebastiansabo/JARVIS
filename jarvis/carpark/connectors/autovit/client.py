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

    def get_adverts(self, page: int = 1) -> Dict[str, Any]:
        """List adverts for this dealer account.

        Returns: {results, total_elements, total_pages, current_page, ...}
        """
        resp = self._request('GET', '/adverts/', params={'page': page})
        return resp.json()

    def get_advert(self, advert_id: str) -> Dict[str, Any]:
        """Get single advert details."""
        resp = self._request('GET', f'/adverts/{advert_id}')
        return resp.json()


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
