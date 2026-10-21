"""Best-effort post-publish hook shared by the Autovit + Autoworld routes.

Call it after any publish / unpublish / delete / verify that can change how
many marketplace channels a vehicle is live on. It reconciles the vehicle's
status (READY_FOR_SALE <-> LISTED) via VehicleService.sync_listing_status, and
NEVER raises — a status-sync hiccup must not turn an already-successful
marketplace operation into a reported failure (mirrors ensure_auto_schedule's
best-effort contract on the same hot path).
"""
import logging

from carpark.services.vehicle_service import VehicleService

logger = logging.getLogger('jarvis.carpark')


def sync_listing_status(vehicle_id: int, changed_by: int = None) -> None:
    try:
        VehicleService().sync_listing_status(vehicle_id, changed_by=changed_by)
    except Exception as e:
        logger.warning('listing-status sync failed for vehicle %s: %s', vehicle_id, e)
