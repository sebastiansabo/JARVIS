"""CarPark scheduled tasks."""
import logging

logger = logging.getLogger('jarvis.tasks.carpark')


def cleanup_vin_cache():
    """Delete expired VIN decoder cache entries."""
    try:
        from carpark.connectors.vin_decoder.cache import VINCache
        cache = VINCache()
        count = cache.cleanup_expired()
        if count > 0:
            logger.info(f"Cleanup: deleted {count} expired VIN cache entries")
    except Exception as e:
        logger.error(f"VIN cache cleanup task failed: {e}")
