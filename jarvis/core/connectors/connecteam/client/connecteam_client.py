"""Connecteam OAuth API client.

Handles OAuth 2.0 client-credentials auth and webhook lifecycle management.
Does NOT poll for data — this connector is purely webhook-driven.

Auth flow:
  1. POST /oauth/v1/token with client_id:client_secret via HTTP Basic Auth
  2. Receive Bearer token (expires in 24h)
  3. Use Bearer token for webhook management API calls
"""

import time
import logging
import requests

from ..config import (
    OAUTH_TOKEN_URL, WEBHOOK_API_URL, REQUEST_TIMEOUT,
    TOKEN_EXPIRY_SECONDS, TOKEN_REFRESH_BUFFER,
    BILET_INVOIRE_FORM_ID, SUPPORTED_EVENT_TYPES,
)
from .exceptions import AuthenticationError, NetworkError, TimeoutError, APIError

logger = logging.getLogger('jarvis.connecteam.client')


class ConnecteamClient:
    """Client for Connecteam OAuth + Webhook API.

    Auth: OAuth 2.0 client credentials — token cached in memory with auto-refresh.
    """

    def __init__(self, client_id, client_secret):
        self._client_id = client_id
        self._client_secret = client_secret
        self._token = None
        self._token_expires_at = 0
        self._session = requests.Session()

    def _ensure_token(self):
        """Get or refresh OAuth Bearer token."""
        if self._token and time.time() < self._token_expires_at:
            return

        logger.info('Requesting new OAuth token from Connecteam')
        try:
            resp = self._session.post(
                OAUTH_TOKEN_URL,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                auth=(self._client_id, self._client_secret),
                data='grant_type=client_credentials',
                timeout=REQUEST_TIMEOUT,
            )
        except requests.exceptions.Timeout:
            raise TimeoutError('Timeout requesting OAuth token')
        except requests.exceptions.ConnectionError:
            raise NetworkError('Cannot connect to Connecteam OAuth endpoint')

        if resp.status_code != 200:
            raise AuthenticationError(
                f'OAuth token request failed: HTTP {resp.status_code} — {resp.text[:200]}'
            )

        data = resp.json()
        self._token = data['access_token']
        expires_in = data.get('expires_in', TOKEN_EXPIRY_SECONDS)
        self._token_expires_at = time.time() + expires_in - TOKEN_REFRESH_BUFFER
        logger.info('OAuth token obtained (expires in %ds, scope: %s)',
                     expires_in, data.get('scope', 'unknown'))

    def _auth_headers(self):
        """Get auth headers with current Bearer token."""
        self._ensure_token()
        return {
            'Authorization': f'Bearer {self._token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }

    # ── Webhook management ──

    def register_webhook(self, name, url, secret_key=None,
                         form_id=BILET_INVOIRE_FORM_ID,
                         event_types=None):
        """Register a new webhook with Connecteam.

        Args:
            name: Descriptive name (e.g. 'JARVIS Bilet de Invoire')
            url: HTTPS callback URL
            secret_key: HMAC secret for signature verification
            form_id: Connecteam form ID (default: Bilet de Invoire)
            event_types: List of event types (default: form_submission + edited)

        Returns:
            Webhook registration response dict.
        """
        body = {
            'name': name,
            'url': url,
            'featureType': 'forms',
            'eventTypes': event_types or SUPPORTED_EVENT_TYPES,
            'objectId': form_id,
        }
        if secret_key:
            body['secretKey'] = secret_key

        return self._request('POST', WEBHOOK_API_URL, json=body)

    def list_webhooks(self):
        """List all registered webhooks."""
        return self._request('GET', WEBHOOK_API_URL)

    def delete_webhook(self, webhook_id):
        """Delete a webhook by ID."""
        return self._request('DELETE', f'{WEBHOOK_API_URL}/{webhook_id}')

    # ── Connection test ──

    def test_connection(self):
        """Test OAuth connectivity by obtaining a token and listing webhooks."""
        self._ensure_token()
        webhooks = self.list_webhooks()
        webhook_list = webhooks.get('data', {}).get('webhooks', [])
        return {
            'success': True,
            'token_valid': True,
            'webhooks_registered': len(webhook_list),
        }

    # ── Request helper ──

    def _request(self, method, url, json=None):
        """Make authenticated API request."""
        headers = self._auth_headers()
        try:
            resp = self._session.request(
                method, url, headers=headers, json=json, timeout=REQUEST_TIMEOUT,
            )
        except requests.exceptions.Timeout:
            raise TimeoutError(f'Timeout calling {method} {url}')
        except requests.exceptions.ConnectionError:
            raise NetworkError(f'Cannot connect to {url}')

        if resp.status_code in (200, 201):
            return resp.json() if resp.text else {}
        elif resp.status_code == 204:
            return {}
        elif resp.status_code == 401:
            # Token expired mid-session — clear and raise
            self._token = None
            self._token_expires_at = 0
            raise AuthenticationError('OAuth token expired or invalid')
        else:
            raise APIError(
                f'Connecteam API error: HTTP {resp.status_code} — {resp.text[:200]}',
                status_code=resp.status_code,
            )

    def close(self):
        """Close the underlying session."""
        if self._session:
            self._session.close()
