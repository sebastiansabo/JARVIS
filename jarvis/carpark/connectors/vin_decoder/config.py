"""VIN Decoder connector configuration.

All credentials loaded from environment variables via from_env().
NEVER hardcode API keys or secrets.
"""
from dataclasses import dataclass
import os


@dataclass
class VINDecoderConfig:
    """VIN Decoder connector configuration."""

    # Provider priority (first = primary, rest = fallback)
    PROVIDER_PRIORITY: list = None  # ['vincario', 'nhtsa']

    # Vincario API (primary - European coverage)
    VINCARIO_API_KEY: str = ''
    VINCARIO_SECRET_KEY: str = ''
    VINCARIO_BASE_URL: str = 'https://api.vincario.com/3.2'

    # NHTSA vPIC API (fallback - free, US-focused but decodes WMI globally)
    NHTSA_BASE_URL: str = 'https://vpic.nhtsa.dot.gov/api/vehicles'

    # Request settings
    REQUEST_TIMEOUT: int = 15
    MAX_RETRIES: int = 3
    RETRY_BASE_DELAY: float = 1.0

    # Caching
    CACHE_ENABLED: bool = True
    CACHE_TTL_DAYS: int = 90

    # Rate limiting
    VINCARIO_MAX_REQUESTS_PER_MONTH: int = 500
    VINCARIO_RATE_LIMIT_BUFFER: int = 10

    def __post_init__(self):
        if self.PROVIDER_PRIORITY is None:
            self.PROVIDER_PRIORITY = ['vincario', 'nhtsa']

    @classmethod
    def from_env(cls) -> 'VINDecoderConfig':
        return cls(
            PROVIDER_PRIORITY=os.environ.get(
                'VIN_PROVIDER_PRIORITY', 'vincario,nhtsa'
            ).split(','),
            VINCARIO_API_KEY=os.environ.get('VINCARIO_API_KEY', ''),
            VINCARIO_SECRET_KEY=os.environ.get('VINCARIO_SECRET_KEY', ''),
            VINCARIO_BASE_URL=os.environ.get(
                'VINCARIO_BASE_URL', 'https://api.vincario.com/3.2'
            ),
            NHTSA_BASE_URL=os.environ.get(
                'NHTSA_BASE_URL',
                'https://vpic.nhtsa.dot.gov/api/vehicles',
            ),
            REQUEST_TIMEOUT=int(os.environ.get('VIN_REQUEST_TIMEOUT', '15')),
            MAX_RETRIES=int(os.environ.get('VIN_MAX_RETRIES', '3')),
            CACHE_ENABLED=os.environ.get(
                'VIN_CACHE_ENABLED', 'true'
            ).lower() == 'true',
            CACHE_TTL_DAYS=int(os.environ.get('VIN_CACHE_TTL_DAYS', '90')),
            VINCARIO_MAX_REQUESTS_PER_MONTH=int(
                os.environ.get('VINCARIO_MAX_REQUESTS', '500')
            ),
        )
