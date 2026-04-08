"""VIN Decoder Client — main orchestrator.

This is the ONLY class that routes/services should interact with.
It handles: validation → cache → provider chain → cache store → return.
"""
import logging
from typing import Optional

from .config import VINDecoderConfig
from .cache import VINCache
from .validator import validate_vin
from .exceptions import (
    VINValidationError, VINNotFoundError, VINDecoderError,
    ProviderUnavailableError,
)
from .providers.base import BaseVINProvider, VehicleSpecs
from .providers.vincario_provider import VincarioProvider
from .providers.nhtsa_provider import NHTSAProvider

logger = logging.getLogger('jarvis.carpark.connectors.vin_decoder')


class VINDecoderClient:
    """Multi-provider VIN decoder with caching and automatic failover.

    Provider chain: Vincario (primary, EU) → NHTSA (fallback, free).
    Results cached in DB to avoid redundant API calls.
    """

    def __init__(self, config: VINDecoderConfig = None):
        self.config = config or VINDecoderConfig.from_env()
        self._cache = VINCache(ttl_days=self.config.CACHE_TTL_DAYS)
        self._providers = self._init_providers()

    def _init_providers(self) -> list:
        """Initialize providers in priority order."""
        providers = []
        for name in self.config.PROVIDER_PRIORITY:
            name = name.strip().lower()
            if name == 'vincario':
                providers.append(VincarioProvider(self.config))
            elif name == 'nhtsa':
                providers.append(NHTSAProvider(self.config))
            else:
                logger.warning(f"Unknown VIN provider: {name}")
        return providers

    def decode(self, vin: str, skip_cache: bool = False) -> VehicleSpecs:
        """Decode VIN through provider chain with caching.

        Flow:
        1. Validate VIN format
        2. Check cache (unless skip_cache=True)
        3. Try providers in priority order
        4. First successful result: cache it, return it
        5. All failed: raise ProviderUnavailableError

        VINNotFoundError does NOT trigger failover — the VIN genuinely
        doesn't exist, trying another provider won't help.
        """
        # 1. Validate
        validation = self.validate(vin)
        if not validation['valid']:
            raise VINValidationError(
                vin, '; '.join(validation['errors']),
            )

        clean_vin = validation['vin']

        # 2. Cache check
        if not skip_cache and self.config.CACHE_ENABLED:
            try:
                cached = self._cache.get(clean_vin)
                if cached:
                    original_provider = cached.provider
                    cached.provider = f"cache (original: {original_provider})"
                    logger.info(f"VIN cache hit: {clean_vin}")
                    return cached
            except Exception as e:
                # Cache failure is non-critical, continue to providers
                logger.warning(f"Cache lookup failed for {clean_vin}: {e}")

        # 3. Provider chain
        errors = []
        providers_tried = []

        for provider in self._providers:
            if not provider.is_available():
                logger.warning(
                    f"Provider {provider.name} unavailable, skipping"
                )
                providers_tried.append(provider.name)
                continue

            try:
                specs = provider.decode(clean_vin)

                # 4. Cache successful result
                if self.config.CACHE_ENABLED:
                    try:
                        self._cache.set(clean_vin, specs)
                    except Exception as e:
                        logger.warning(f"Cache store failed: {e}")

                logger.info(
                    f"VIN decoded: {clean_vin} via {provider.name} "
                    f"(confidence={specs.confidence_score:.2f})"
                )
                return specs

            except VINNotFoundError:
                # VIN genuinely not found — don't try other providers
                raise

            except VINDecoderError as e:
                errors.append(e)
                providers_tried.append(provider.name)
                logger.warning(
                    f"Provider {provider.name} failed for {clean_vin}: {e}"
                )

        # 5. All providers failed
        if not providers_tried:
            providers_tried = [p.name for p in self._providers]

        raise ProviderUnavailableError(providers_tried, errors)

    def validate(self, vin: str) -> dict:
        """Validate VIN format without making any API calls.

        Returns: {valid, vin, wmi, vds, vis, check_digit_valid, errors}
        """
        return validate_vin(vin)

    def get_provider_status(self) -> list:
        """Return status of all configured providers.

        Returns list of dicts: [{name, available, remaining_quota}]
        """
        status = []
        for provider in self._providers:
            try:
                available = provider.is_available()
                quota = provider.get_remaining_quota()
            except Exception as e:
                logger.warning(f"Status check failed for {provider.name}: {e}")
                available = False
                quota = None

            status.append({
                'name': provider.name,
                'available': available,
                'remaining_quota': quota,
            })
        return status
