"""BioStar 2 REST API client.

Handles authentication (bs-session-id), user retrieval, and event search.
Auto-relogins on session expiry.
"""

import time
import requests
import urllib3

from ..config import REQUEST_TIMEOUT, USERS_PAGE_SIZE, EVENTS_PAGE_SIZE, MAX_RETRIES, RETRY_BASE_DELAY
from .exceptions import (
    AuthenticationError, SessionExpiredError,
    NetworkError, TimeoutError, APIError, ParseError
)

# Suppress InsecureRequestWarning for self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class BioStarClient:
    """Client for BioStar 2 REST API.

    Auth: POST /api/login → bs-session-id header for subsequent requests.
    """

    def __init__(self, host, port, login_id, password, verify_ssl=False):
        self.base_url = f"https://{host}:{port}"
        self.login_id = login_id
        self.password = password
        self.verify_ssl = verify_ssl
        self._session = requests.Session()
        self._session.verify = verify_ssl
        self._session_id = None

    def login(self):
        """Authenticate and store bs-session-id. Returns user info dict."""
        try:
            resp = self._session.post(
                f"{self.base_url}/api/login",
                json={"User": {"login_id": self.login_id, "password": self.password}},
                timeout=REQUEST_TIMEOUT,
            )
        except requests.exceptions.Timeout:
            raise TimeoutError(f"Timeout connecting to {self.base_url}")
        except requests.exceptions.ConnectionError as e:
            raise NetworkError(f"Cannot connect to {self.base_url}: {e}")

        if resp.status_code != 200:
            body = self._parse_json(resp)
            msg = body.get('Response', {}).get('message', 'Login failed')
            raise AuthenticationError(msg, code=resp.status_code)

        body = self._parse_json(resp)
        if body.get('Response', {}).get('code') not in ('0', 0, None):
            msg = body.get('Response', {}).get('message', 'Login failed')
            raise AuthenticationError(msg)

        # Extract session ID from header or response
        self._session_id = resp.headers.get('bs-session-id')
        if not self._session_id:
            self._session_id = resp.cookies.get('bs-session-id')
        if self._session_id:
            self._session.headers['bs-session-id'] = self._session_id

        return body.get('User', {})

    def _ensure_session(self):
        """Login if no active session."""
        if not self._session_id:
            self.login()

    def _request(self, method, endpoint, json_data=None, params=None, retry_auth=True):
        """Make API request with auto-relogin on 401."""
        self._ensure_session()

        url = f"{self.base_url}{endpoint}"
        for attempt in range(MAX_RETRIES):
            try:
                resp = self._session.request(
                    method, url, json=json_data, params=params,
                    timeout=REQUEST_TIMEOUT,
                )
            except requests.exceptions.Timeout:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_DELAY * (attempt + 1))
                    continue
                raise TimeoutError(f"Timeout: {method} {endpoint}")
            except requests.exceptions.ConnectionError as e:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_DELAY * (attempt + 1))
                    continue
                raise NetworkError(f"Connection error: {e}")

            # Session expired — re-login once
            if resp.status_code == 401 and retry_auth:
                self._session_id = None
                self.login()
                return self._request(method, endpoint, json_data, params, retry_auth=False)

            if resp.status_code >= 400:
                body = self._parse_json(resp)
                msg = body.get('Response', {}).get('message', f'HTTP {resp.status_code}')
                raise APIError(msg, status_code=resp.status_code)

            return self._parse_json(resp)

        raise NetworkError(f"Max retries exceeded for {method} {endpoint}")

    def _parse_json(self, resp):
        """Parse JSON response, raise ParseError on failure."""
        try:
            return resp.json()
        except (ValueError, TypeError) as e:
            raise ParseError(f"Invalid JSON response: {e}")

    # ── User endpoints ──

    def get_users(self, offset=0, limit=None):
        """GET /api/users — returns {UserCollection: {total, rows: [...]}}"""
        limit = limit or USERS_PAGE_SIZE
        return self._request('GET', '/api/users', params={
            'limit': limit, 'offset': offset
        })

    def get_user(self, user_id):
        """GET /api/users/{user_id}"""
        return self._request('GET', f'/api/users/{user_id}')

    def get_user_groups(self):
        """GET /api/user_groups"""
        return self._request('GET', '/api/user_groups')

    # ── Event endpoints ──

    def search_events(self, start_datetime, end_datetime, offset=0, limit=None):
        """POST /api/events/search — search events by date range."""
        limit = limit or EVENTS_PAGE_SIZE
        return self._request('POST', '/api/events/search', json_data={
            "Query": {
                "limit": limit,
                "offset": offset,
                "conditions": [{
                    "column": "datetime",
                    "operator": 3,  # BETWEEN
                    "values": [
                        start_datetime,
                        end_datetime
                    ]
                }]
            }
        })

    # ── Connection test ──

    def test_connection(self):
        """Login and fetch user count to verify connectivity."""
        user_info = self.login()
        result = self.get_users(limit=1)
        total = result.get('UserCollection', {}).get('total', 0)
        return {
            'success': True,
            'user': user_info.get('name', 'Unknown'),
            'total_users': int(total),
        }

    def close(self):
        """Close the underlying session."""
        if self._session:
            self._session.close()
