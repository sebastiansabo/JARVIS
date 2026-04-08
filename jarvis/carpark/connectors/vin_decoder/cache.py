"""DB-backed VIN decode cache using BaseRepository.

Caches decoded VehicleSpecs in carpark_vin_cache table with configurable TTL.
Vehicle specs don't change, so 90-day TTL is reasonable.
"""
import json
import logging
from datetime import datetime
from typing import Optional

from core.base_repository import BaseRepository
from .providers.base import VehicleSpecs

logger = logging.getLogger('jarvis.carpark.connectors.vin_decoder.cache')


class VINCache(BaseRepository):
    """DB-backed cache for VIN decode results."""

    def __init__(self, ttl_days: int = 90):
        self._ttl_days = ttl_days

    def get(self, vin: str) -> Optional[VehicleSpecs]:
        """Retrieve cached VIN decode result if not expired.

        Returns the highest-confidence result for the VIN.
        Also increments hit_count for cache analytics.
        """
        row = self.query_one('''
            SELECT specs_json, provider, confidence_score
            FROM carpark_vin_cache
            WHERE vin = %s AND expires_at > NOW()
            ORDER BY confidence_score DESC NULLS LAST
            LIMIT 1
        ''', (vin.upper(),))

        if not row:
            return None

        # Update hit metrics (fire-and-forget, don't fail on error)
        try:
            self.execute('''
                UPDATE carpark_vin_cache
                SET hit_count = hit_count + 1, last_hit_at = NOW()
                WHERE vin = %s AND provider = %s
            ''', (vin.upper(), row['provider']))
        except Exception:
            pass  # Hit tracking is non-critical

        return self._from_row(row)

    def set(self, vin: str, specs: VehicleSpecs) -> None:
        """Store or update a VIN decode result in cache."""
        specs_dict = specs.to_dict()

        self.execute('''
            INSERT INTO carpark_vin_cache
                (vin, provider, specs_json, confidence_score, expires_at)
            VALUES (%s, %s, %s, %s, NOW() + INTERVAL '%s days')
            ON CONFLICT (vin, provider) DO UPDATE SET
                specs_json = EXCLUDED.specs_json,
                confidence_score = EXCLUDED.confidence_score,
                expires_at = EXCLUDED.expires_at,
                created_at = NOW(),
                hit_count = 0,
                last_hit_at = NULL
        ''', (
            vin.upper(),
            specs.provider,
            json.dumps(specs_dict),
            specs.confidence_score,
            self._ttl_days,
        ))

    def cleanup_expired(self) -> int:
        """Delete expired cache entries. Returns count of deleted rows."""
        try:
            count_row = self.query_one(
                'SELECT COUNT(*) as cnt FROM carpark_vin_cache WHERE expires_at < NOW()'
            )
            count = count_row['cnt'] if count_row else 0
            if count > 0:
                self.execute(
                    'DELETE FROM carpark_vin_cache WHERE expires_at < NOW()'
                )
            return count
        except Exception as e:
            logger.error(f"Cache cleanup failed: {e}")
            return 0

    def _from_row(self, row: dict) -> VehicleSpecs:
        """Reconstruct VehicleSpecs from cached DB row."""
        specs_data = row['specs_json']
        if isinstance(specs_data, str):
            specs_data = json.loads(specs_data)

        specs = VehicleSpecs(provider=row.get('provider', 'cache'))

        # Map JSON fields back to dataclass
        for key, value in specs_data.items():
            if key == 'raw_response':
                continue
            if key == 'decoded_at':
                try:
                    specs.decoded_at = datetime.fromisoformat(value)
                except (ValueError, TypeError):
                    pass
                continue
            if hasattr(specs, key):
                setattr(specs, key, value)

        return specs
