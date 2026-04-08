"""VIN Decoder connector for CarPark module.

Multi-provider VIN decoder with automatic failover and DB-backed caching.
Providers: Vincario (primary, EU) -> NHTSA vPIC (fallback, free).
"""
from .client import VINDecoderClient
from .exceptions import (
    VINDecoderError,
    VINValidationError,
    VINNotFoundError,
    QuotaExhaustedError,
    ProviderUnavailableError,
    AuthenticationError,
    RateLimitError,
    NetworkError,
    APIError,
)

__all__ = [
    'VINDecoderClient',
    'VINDecoderError',
    'VINValidationError',
    'VINNotFoundError',
    'QuotaExhaustedError',
    'ProviderUnavailableError',
    'AuthenticationError',
    'RateLimitError',
    'NetworkError',
    'APIError',
]
