"""NHTSA vPIC API provider — free, unlimited, US-focused but decodes WMI globally.

Endpoint: GET https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/{vin}?format=json
Auth: None required (public API).
Response: JSON with Results array of {Variable, Value, ValueId, VariableId} pairs.
"""
import logging
import time
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config import VINDecoderConfig
from ..exceptions import (
    NetworkError, TimeoutError, APIError, ParseError, VINNotFoundError,
)
from ..mapper import map_nhtsa_response
from .base import BaseVINProvider, VehicleSpecs

logger = logging.getLogger('jarvis.carpark.connectors.vin_decoder.nhtsa')


class NHTSAProvider(BaseVINProvider):
    """NHTSA vPIC API provider (free, unlimited)."""

    def __init__(self, config: VINDecoderConfig, session: requests.Session = None):
        self.config = config
        self._session = session

    @property
    def name(self) -> str:
        return 'nhtsa'

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

    def decode(self, vin: str) -> VehicleSpecs:
        """Decode VIN via NHTSA vPIC API."""
        url = f"{self.config.NHTSA_BASE_URL}/decodevin/{vin}?format=json"
        t0 = time.perf_counter()

        try:
            resp = self._get_session().get(
                url, timeout=self.config.REQUEST_TIMEOUT,
            )
            latency_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                f"NHTSA decode: vin={vin} status={resp.status_code} "
                f"latency={latency_ms:.0f}ms"
            )

            if resp.status_code != 200:
                raise APIError(
                    f"NHTSA returned {resp.status_code}",
                    status_code=resp.status_code,
                )

            data = resp.json()
            results = data.get('Results', [])
            if not results:
                raise VINNotFoundError(vin)

            # Check if NHTSA returned meaningful data
            # ErrorCode '0' means success, anything else is an error for that field
            has_data = False
            for item in results:
                if (item.get('Value') and
                        item.get('Variable') in ('Make', 'Model') and
                        str(item['Value']).strip()):
                    has_data = True
                    break

            if not has_data:
                raise VINNotFoundError(vin)

            specs = map_nhtsa_response(results, vin=vin)
            return specs

        except requests.exceptions.Timeout as e:
            raise TimeoutError(
                'NHTSA request timed out',
                timeout_seconds=self.config.REQUEST_TIMEOUT,
                original_error=e,
            )
        except requests.exceptions.ConnectionError as e:
            raise NetworkError('NHTSA connection failed', original_error=e)
        except requests.exceptions.SSLError as e:
            raise NetworkError('NHTSA SSL error', original_error=e)
        except requests.exceptions.RequestException as e:
            raise NetworkError(f'NHTSA request failed: {e}', original_error=e)
        except (ValueError, KeyError) as e:
            raise ParseError(f'Failed to parse NHTSA response: {e}')

    def is_available(self) -> bool:
        """NHTSA is always available (free, no auth)."""
        return True

    def get_remaining_quota(self) -> Optional[int]:
        """NHTSA is unlimited."""
        return None
