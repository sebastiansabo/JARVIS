"""Vincario API provider — primary, paid, EU-focused with rich decode data.

Auth: SHA1-based control sum (first 10 chars of SHA1 hash).
Control sum = sha1(f"{VIN}|{action_id}|{api_key}|{secret_key}").hexdigest()[:10]

SECURITY: Never log api_key, secret_key, control_sum, or full URL.
Log only: endpoint path, VIN, latency_ms, status_code.
"""
import hashlib
import logging
import time
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config import VINDecoderConfig
from ..exceptions import (
    AuthenticationError, RateLimitError, QuotaExhaustedError,
    VINNotFoundError, VINValidationError, NetworkError, TimeoutError,
    APIError, ParseError,
)
from ..mapper import map_vincario_response
from .base import BaseVINProvider, VehicleSpecs

logger = logging.getLogger('jarvis.carpark.connectors.vin_decoder.vincario')


class VincarioProvider(BaseVINProvider):
    """Vincario API v3.2 provider (primary, paid, European coverage)."""

    def __init__(self, config: VINDecoderConfig, session: requests.Session = None):
        self.config = config
        self._api_key = config.VINCARIO_API_KEY
        self._secret_key = config.VINCARIO_SECRET_KEY
        self._base_url = config.VINCARIO_BASE_URL
        self._session = session
        self._cached_balance = None
        self._balance_checked_at = 0.0

    @property
    def name(self) -> str:
        return 'vincario'

    def _get_session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
            retry = Retry(
                total=self.config.MAX_RETRIES,
                backoff_factor=self.config.RETRY_BASE_DELAY,
                status_forcelist=[500, 502, 503, 504],
                allowed_methods=['GET'],
            )
            adapter = HTTPAdapter(max_retries=retry)
            self._session.mount('https://', adapter)
            self._session.mount('http://', adapter)
            self._session.headers.update({
                'Accept': 'application/json',
                'User-Agent': 'JARVIS-CarPark-VINDecoder/1.0',
            })
        return self._session

    def _control_sum(self, vin: str = None, action_id: str = 'decode') -> str:
        """Calculate Vincario API control sum (first 10 chars of SHA1).

        IMPORTANT: Uses SHA1, NOT SHA256.
        """
        if vin:
            raw = f"{vin.upper()}|{action_id}|{self._api_key}|{self._secret_key}"
        else:
            raw = f"{action_id}|{self._api_key}|{self._secret_key}"
        return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:10]

    def _handle_error_response(self, resp: requests.Response, vin: str = ''):
        """Map HTTP status codes to appropriate exceptions."""
        status = resp.status_code

        if status == 400:
            raise VINValidationError(vin, 'Vincario rejected VIN format')
        elif status in (401, 403):
            raise AuthenticationError('Vincario authentication failed')
        elif status == 402:
            raise QuotaExhaustedError('Vincario API quota exhausted')
        elif status == 404:
            raise VINNotFoundError(vin)
        elif status == 429:
            retry_after = None
            try:
                retry_after = int(resp.headers.get('Retry-After', 60))
            except (ValueError, TypeError):
                pass
            raise RateLimitError(
                'Vincario rate limit exceeded', retry_after=retry_after,
            )
        else:
            raise APIError(
                f'Vincario returned {status}',
                status_code=status,
            )

    def decode(self, vin: str) -> VehicleSpecs:
        """Decode VIN via Vincario decode endpoint (consumes 1 API credit)."""
        clean_vin = vin.upper()
        control = self._control_sum(clean_vin, 'decode')
        url = f"{self._base_url}/{self._api_key}/{control}/decode/{clean_vin}.json"
        t0 = time.perf_counter()

        try:
            resp = self._get_session().get(
                url, timeout=self.config.REQUEST_TIMEOUT,
            )
            latency_ms = (time.perf_counter() - t0) * 1000
            # SECURITY: Only log endpoint path, not full URL (contains api_key)
            logger.info(
                f"Vincario decode: vin={clean_vin} status={resp.status_code} "
                f"latency={latency_ms:.0f}ms"
            )

            if resp.status_code != 200:
                self._handle_error_response(resp, clean_vin)

            data = resp.json()

            # Vincario returns an error object on failure
            if isinstance(data, dict) and data.get('error'):
                error_msg = data.get('error', 'Unknown error')
                if 'not found' in str(error_msg).lower():
                    raise VINNotFoundError(clean_vin)
                raise APIError(f'Vincario error: {error_msg}', status_code=200)

            specs = map_vincario_response(data, vin=clean_vin)
            return specs

        except (VINNotFoundError, VINValidationError, AuthenticationError,
                QuotaExhaustedError, RateLimitError, APIError, ParseError):
            raise
        except requests.exceptions.Timeout as e:
            raise TimeoutError(
                'Vincario request timed out',
                timeout_seconds=self.config.REQUEST_TIMEOUT,
                original_error=e,
            )
        except requests.exceptions.ConnectionError as e:
            raise NetworkError('Vincario connection failed', original_error=e)
        except requests.exceptions.SSLError as e:
            raise NetworkError('Vincario SSL error', original_error=e)
        except requests.exceptions.RequestException as e:
            raise NetworkError(
                f'Vincario request failed: {e}', original_error=e,
            )
        except (ValueError, KeyError) as e:
            raise ParseError(f'Failed to parse Vincario response: {e}')

    def info(self, vin: str) -> dict:
        """Free call to check which fields are available for a VIN.

        Does NOT consume API credits.
        """
        clean_vin = vin.upper()
        control = self._control_sum(clean_vin, 'info')
        url = f"{self._base_url}/{self._api_key}/{control}/info/{clean_vin}.json"

        try:
            resp = self._get_session().get(
                url, timeout=self.config.REQUEST_TIMEOUT,
            )
            if resp.status_code != 200:
                return {}
            return resp.json()
        except Exception:
            return {}

    def get_remaining_quota(self) -> Optional[int]:
        """Call Vincario balance endpoint to get remaining decode credits.

        Caches result for 5 minutes to avoid excessive balance checks.
        """
        # Check cache (5 minute TTL)
        now = time.time()
        if (self._cached_balance is not None and
                now - self._balance_checked_at < 300):
            return self._cached_balance

        if not self._api_key or not self._secret_key:
            return 0

        control = self._control_sum(action_id='balance')
        url = f"{self._base_url}/{self._api_key}/{control}/balance.json"

        try:
            resp = self._get_session().get(
                url, timeout=self.config.REQUEST_TIMEOUT,
            )
            if resp.status_code != 200:
                logger.warning(
                    f"Vincario balance check failed: status={resp.status_code}"
                )
                return self._cached_balance

            data = resp.json()
            balance = int(data.get('API Decode', 0))
            self._cached_balance = balance
            self._balance_checked_at = now
            logger.debug(f"Vincario balance: {balance} decode credits remaining")
            return balance

        except Exception as e:
            logger.warning(f"Vincario balance check error: {e}")
            return self._cached_balance

    def is_available(self) -> bool:
        """Check if Vincario is configured and has quota remaining."""
        if not self._api_key or not self._secret_key:
            return False

        remaining = self.get_remaining_quota()
        if remaining is None:
            # Can't check balance, assume available if keys are set
            return True

        return remaining > self.config.VINCARIO_RATE_LIMIT_BUFFER
