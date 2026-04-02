"""Publishing Service — Multi-platform vehicle listing management.

Handles publishing, deactivation, bulk operations, and sync through
the abstract connector pattern.
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from carpark.repositories.publishing_repository import PublishingRepository
from carpark.repositories.vehicle_repository import VehicleRepository
from carpark.connectors.base_connector import BaseConnector
from carpark.connectors.autovit.client import AutovitConnector

logger = logging.getLogger('jarvis.carpark')

# Connector registry — map platform_type to connector class
CONNECTOR_REGISTRY: Dict[str, type] = {
    'autovit': AutovitConnector,
}


class PublishingService:
    """Multi-platform publishing engine."""

    def __init__(self):
        self._pub_repo = PublishingRepository()
        self._vehicle_repo = VehicleRepository()

    def _get_connector(self, platform: Dict[str, Any]) -> Optional[BaseConnector]:
        """Instantiate a connector for the given platform."""
        ptype = platform.get('platform_type', '')
        connector_cls = CONNECTOR_REGISTRY.get(ptype)
        if not connector_cls:
            return None
        return connector_cls(
            api_key=platform.get('api_key_encrypted'),
            dealer_id=platform.get('dealer_account_id'),
        )

    # ═══════════════════════════════════════════════
    # PLATFORMS CRUD
    # ═══════════════════════════════════════════════

    def list_platforms(self, company_id: int = None,
                       active_only: bool = False) -> List[Dict[str, Any]]:
        platforms = self._pub_repo.list_platforms(company_id, active_only)
        for p in platforms:
            p['active_listings'] = self._pub_repo.get_active_listings_count(p['id'])
        return platforms

    def get_platform(self, platform_id: int) -> Optional[Dict[str, Any]]:
        return self._pub_repo.get_platform(platform_id)

    def create_platform(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._pub_repo.create_platform(data)

    def update_platform(self, platform_id: int,
                        data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._pub_repo.update_platform(platform_id, data)

    def delete_platform(self, platform_id: int) -> bool:
        return self._pub_repo.delete_platform(platform_id)

    # ═══════════════════════════════════════════════
    # LISTINGS
    # ═══════════════════════════════════════════════

    def get_vehicle_listings(self, vehicle_id: int) -> List[Dict[str, Any]]:
        return self._pub_repo.get_listings_for_vehicle(vehicle_id)

    def get_listing(self, listing_id: int) -> Optional[Dict[str, Any]]:
        return self._pub_repo.get_listing(listing_id)

    def update_listing(self, listing_id: int,
                       data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return self._pub_repo.update_listing(listing_id, data)

    # ═══════════════════════════════════════════════
    # PUBLISH
    # ═══════════════════════════════════════════════

    def publish_to_platform(self, vehicle_id: int, platform_id: int,
                            expires_at: str = None) -> Dict[str, Any]:
        """Publish a vehicle to a specific platform."""
        vehicle = self._vehicle_repo.get_by_id(vehicle_id)
        if not vehicle:
            raise ValueError('Vehicle not found')

        platform = self._pub_repo.get_platform(platform_id)
        if not platform:
            raise ValueError('Platform not found')
        if not platform.get('is_active'):
            raise ValueError('Platform is not active')

        # Check for existing listing
        existing = self._pub_repo.get_listing_by_vehicle_platform(vehicle_id, platform_id)
        if existing and existing.get('status') == 'active':
            return {'listing': existing, 'action': 'already_active'}

        connector = self._get_connector(platform)

        if connector:
            # Try real API publish
            result = connector.publish(vehicle)
            success = result.get('success', False)

            self._pub_repo.log_sync(
                vehicle_id, platform_id, 'create', success,
                request_payload={'vin': vehicle.get('vin')},
                response_payload=result,
                error_message=result.get('error'),
            )

            if success:
                listing_data = {
                    'vehicle_id': vehicle_id,
                    'platform_id': platform_id,
                    'external_listing_id': result.get('external_id'),
                    'external_url': result.get('external_url'),
                    'status': 'active',
                    'published_at': datetime.utcnow().isoformat(),
                    'expires_at': expires_at,
                    'last_sync': datetime.utcnow().isoformat(),
                }
            else:
                listing_data = {
                    'vehicle_id': vehicle_id,
                    'platform_id': platform_id,
                    'status': 'error',
                    'error_message': result.get('error', 'Unknown error'),
                }
        else:
            # No connector — create as draft (manual platform)
            listing_data = {
                'vehicle_id': vehicle_id,
                'platform_id': platform_id,
                'status': 'draft',
                'expires_at': expires_at,
            }

        if existing:
            listing = self._pub_repo.update_listing(existing['id'], listing_data)
            return {'listing': listing, 'action': 'updated'}
        else:
            listing = self._pub_repo.create_listing(listing_data)
            return {'listing': listing, 'action': 'created'}

    def publish_to_all(self, vehicle_id: int,
                       company_id: int = None,
                       expires_at: str = None) -> List[Dict[str, Any]]:
        """Publish a vehicle to all active platforms."""
        platforms = self._pub_repo.list_platforms(company_id, active_only=True)
        results = []
        for platform in platforms:
            try:
                result = self.publish_to_platform(vehicle_id, platform['id'], expires_at)
                results.append({
                    'platform_id': platform['id'],
                    'platform_name': platform['name'],
                    **result,
                })
            except Exception as e:
                results.append({
                    'platform_id': platform['id'],
                    'platform_name': platform['name'],
                    'action': 'error',
                    'error': str(e),
                })
        return results

    # ═══════════════════════════════════════════════
    # ACTIVATE / DEACTIVATE
    # ═══════════════════════════════════════════════

    def activate_listing(self, listing_id: int) -> Dict[str, Any]:
        """Activate a listing (set status to active)."""
        listing = self._pub_repo.get_listing(listing_id)
        if not listing:
            raise ValueError('Listing not found')

        platform = self._pub_repo.get_platform(listing['platform_id'])
        connector = self._get_connector(platform) if platform else None

        if connector and listing.get('external_listing_id'):
            result = connector.publish({'external_id': listing['external_listing_id']})
            self._pub_repo.log_sync(
                listing['vehicle_id'], listing['platform_id'],
                'activate', result.get('success', False),
                error_message=result.get('error'),
            )

        updated = self._pub_repo.update_listing(listing_id, {
            'status': 'active',
            'published_at': datetime.utcnow().isoformat(),
            'error_message': None,
        })
        return updated

    def deactivate_listing(self, listing_id: int) -> Dict[str, Any]:
        """Deactivate a listing (make invisible but not deleted)."""
        listing = self._pub_repo.get_listing(listing_id)
        if not listing:
            raise ValueError('Listing not found')

        platform = self._pub_repo.get_platform(listing['platform_id'])
        connector = self._get_connector(platform) if platform else None

        if connector and listing.get('external_listing_id'):
            result = connector.deactivate(listing['external_listing_id'])
            self._pub_repo.log_sync(
                listing['vehicle_id'], listing['platform_id'],
                'deactivate', result.get('success', False),
                error_message=result.get('error'),
            )

        updated = self._pub_repo.update_listing(listing_id, {
            'status': 'inactive',
        })
        return updated

    def deactivate_all(self, vehicle_id: int) -> List[Dict[str, Any]]:
        """Deactivate all listings for a vehicle."""
        listings = self._pub_repo.get_listings_for_vehicle(vehicle_id)
        results = []
        for listing in listings:
            if listing.get('status') == 'active':
                try:
                    updated = self.deactivate_listing(listing['id'])
                    results.append(updated)
                except Exception as e:
                    logger.error(f'Failed to deactivate listing {listing["id"]}: {e}')
        return results

    # ═══════════════════════════════════════════════
    # SYNC STATS
    # ═══════════════════════════════════════════════

    def sync_listing_stats(self, listing_id: int) -> Optional[Dict[str, Any]]:
        """Sync views/inquiries for a single listing from the platform."""
        listing = self._pub_repo.get_listing(listing_id)
        if not listing or not listing.get('external_listing_id'):
            return listing

        platform = self._pub_repo.get_platform(listing['platform_id'])
        connector = self._get_connector(platform) if platform else None

        if connector:
            stats = connector.get_stats(listing['external_listing_id'])
            updated = self._pub_repo.update_listing(listing_id, {
                'views': stats.get('views', listing.get('views', 0)),
                'inquiries': stats.get('inquiries', listing.get('inquiries', 0)),
                'last_sync': datetime.utcnow().isoformat(),
            })
            self._pub_repo.log_sync(
                listing['vehicle_id'], listing['platform_id'],
                'sync', True,
                response_payload=stats,
            )
            return updated
        return listing

    def sync_all_platform_stats(self) -> Dict[str, int]:
        """Sync stats for all active listings across all platforms. Scheduled task."""
        # Get all active listings
        from core.base_repository import BaseRepository
        repo = BaseRepository()
        listings = repo.query_all(
            "SELECT id FROM carpark_vehicle_listings WHERE status = 'active'"
        )
        synced = 0
        errors = 0
        for row in listings:
            try:
                self.sync_listing_stats(row['id'])
                synced += 1
            except Exception as e:
                logger.error(f'Sync failed for listing {row["id"]}: {e}')
                errors += 1
        return {'synced': synced, 'errors': errors}

    # ═══════════════════════════════════════════════
    # SYNC LOG
    # ═══════════════════════════════════════════════

    def get_sync_log(self, vehicle_id: int = None,
                     platform_id: int = None,
                     limit: int = 50) -> List[Dict[str, Any]]:
        return self._pub_repo.get_sync_log(vehicle_id, platform_id, limit)
