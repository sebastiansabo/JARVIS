"""Sincron REST API client.

Handles Bearer token auth and monthly timesheet retrieval.
One client instance per company (each company has its own token).

API response shapes (discovered from live testing):
  - Success:    {"currentPage": 1, "totalPages": 1, "perPage": 50, "total_rows": "45", "data": [...]}
  - No results: {"message": "No results"}   (HTTP 200)
  - Validation: {"status": "error", "message": "Month or year missing"}  (HTTP 200)
  - Auth error: {"status": false, "error": "Not authorized"}  (HTTP 401)
"""

import time
import logging
import requests

from ..config import BASE_URL, REQUEST_TIMEOUT, MAX_RETRIES, RETRY_BASE_DELAY
from .exceptions import (
    AuthenticationError, ValidationError,
    NetworkError, TimeoutError, APIError
)

logger = logging.getLogger('jarvis.sincron.client')


class SincronClient:
    """Client for Sincron Timesheet API.

    Auth: Bearer token passed in Authorization header.
    Each Autoworld company has its own token.
    """

    def __init__(self, token, base_url=None):
        self.base_url = base_url or BASE_URL
        self.token = token
        self._session = requests.Session()
        self._session.headers.update({
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}',
        })

    def get_timesheet(self, month, year, id_employee=None, page=1):
        """POST /timesheet — get monthly timesheet data.

        If id_employee is None, returns all employees (paginated).
        Returns normalized response with 'data' array (may be empty).
        """
        body = {
            'month': month,
            'year': year,
            'page': page,
        }
        if id_employee is not None:
            body['id_employee'] = id_employee

        result = self._request(body)
        return self._normalize_response(result)

    @staticmethod
    def _normalize_response(result):
        """Normalize API response to consistent shape.

        Handles three 200-OK response formats:
          1. Normal paginated: {currentPage, totalPages, data: [...]}
          2. No results:       {"message": "No results"}
          3. Validation error: {"status": "error", "message": "..."}
        """
        # Check for validation error (API returns 200 for these)
        if result.get('status') == 'error':
            raise ValidationError(result.get('message', 'Unknown validation error'))

        # "No results" response — return empty paginated structure
        if 'data' not in result and result.get('message') == 'No results':
            return {
                'currentPage': 1,
                'totalPages': 1,
                'perPage': 50,
                'total_rows': '0',
                'data': [],
            }

        return result

    def get_all_timesheets(self, month, year):
        """Fetch all pages of timesheet data for a given month/year.

        Returns combined list of all employee records.
        """
        all_data = []
        page = 1

        while True:
            result = self.get_timesheet(month, year, page=page)
            data = result.get('data', [])
            all_data.extend(data)

            total_pages = result.get('totalPages', 1)
            if page >= total_pages:
                break
            page += 1

        return all_data

    def test_connection(self):
        """Test connectivity by fetching page 1 of current month."""
        from datetime import datetime
        now = datetime.now()
        result = self.get_timesheet(now.month, now.year, page=1)
        total = result.get('total_rows', '0')
        return {
            'success': True,
            'total_employees': int(total),
            'current_page': result.get('currentPage', 1),
            'total_pages': result.get('totalPages', 1),
        }

    def _request(self, body):
        """Make POST request with retry logic."""
        for attempt in range(MAX_RETRIES):
            try:
                resp = self._session.post(
                    self.base_url,
                    json=body,
                    timeout=REQUEST_TIMEOUT,
                )
            except requests.exceptions.Timeout:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_DELAY * (attempt + 1))
                    continue
                raise TimeoutError(f'Timeout connecting to Sincron API')
            except requests.exceptions.ConnectionError:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_DELAY * (attempt + 1))
                    continue
                raise NetworkError('Cannot connect to Sincron API')

            if resp.status_code == 200:
                return self._parse_json(resp)
            elif resp.status_code == 401:
                raise AuthenticationError('Invalid or expired Bearer token')
            elif resp.status_code == 422:
                body_resp = self._parse_json(resp)
                msg = body_resp.get('message', 'Validation error')
                raise ValidationError(msg)
            elif resp.status_code >= 500:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_DELAY * (attempt + 1))
                    continue
                raise APIError('Sincron API server error',
                               status_code=resp.status_code)
            else:
                raise APIError(f'Unexpected HTTP {resp.status_code}',
                               status_code=resp.status_code)

        raise NetworkError('Max retries exceeded connecting to Sincron API')

    @staticmethod
    def _parse_json(resp):
        """Parse JSON response."""
        try:
            return resp.json()
        except (ValueError, TypeError):
            raise APIError('Invalid JSON response from Sincron API')

    def close(self):
        """Close the underlying session."""
        if self._session:
            self._session.close()
