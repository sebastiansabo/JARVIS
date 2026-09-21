# jarvis/carpark/connectors/shopify/connector.py
"""High-level Shopify connector: orchestrates mapper + client + listing state."""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from carpark.connectors.base_connector import BaseConnector
from core.services import spaces_service
from . import mapper

logger = logging.getLogger('jarvis.carpark.shopify.connector')

PLATFORM_TYPE = 'shopify'

# Shopify ingests product media asynchronously by fetching `originalSource` from its
# own servers, so the signed URL must outlive the mutation's processing window.
PHOTO_PRESIGN_TTL = 24 * 3600


def _photo_source(url: str) -> str:
    """Resolve a stored photo reference into a Shopify-fetchable image URL.

    Photos are persisted as private Spaces object keys (carpark/routes/photos.py),
    which Shopify cannot fetch — passing a raw key fails with "File URL is invalid".
    Presign keys into a time-limited GET URL; leave anything already a public
    http(s) source (or a legacy data: URL) untouched.
    """
    if not url or url.startswith(('http://', 'https://', 'data:')):
        return url
    return spaces_service.presigned_url(url, expires=PHOTO_PRESIGN_TTL)


def ensure_platform(publishing_repo, store_domain: str) -> int:
    """Return the carpark_publishing_platforms.id for Shopify, creating it once."""
    for p in publishing_repo.list_platforms():
        if (p.get('platform_type') or '').lower() == PLATFORM_TYPE:
            return p['id']
    created = publishing_repo.create_platform({
        'name': 'Shopify — Autoworld',
        'platform_type': PLATFORM_TYPE,
        'website_url': f'https://{store_domain}',
        'is_active': True,
    })
    return created['id']


class ShopifyConnector(BaseConnector):
    def __init__(self, client, publishing_repo, platform_id: int):
        self.client = client
        self.pub = publishing_repo
        self.platform_id = platform_id

    def _admin_url(self, product_gid: str) -> str:
        num = product_gid.rsplit('/', 1)[-1]
        return f'https://{self.client.store_domain}/admin/products/{num}'

    def publish(self, vehicle: Dict[str, Any], photos: List[dict],
                field_map: List[dict], value_map: Dict[str, Dict[str, str]],
                config: Dict[str, Any]) -> Dict[str, Any]:
        ok, reason = mapper.is_eligible(vehicle, photos)
        if not ok:
            return {'success': False, 'error': reason}

        existing = self.pub.get_listing_by_vehicle_platform(vehicle['id'], self.platform_id)
        resolved_photos = [{**p, 'url': _photo_source(p.get('url'))} for p in photos]
        product_input, warnings = mapper.vehicle_to_product(vehicle, resolved_photos, field_map, value_map, config)
        if existing and existing.get('external_listing_id'):
            product_input['id'] = existing['external_listing_id']

        result = self.client.product_set(product_input)
        if result['userErrors']:
            msg = '; '.join(f"{e.get('field')}: {e['message']}" for e in result['userErrors'])
            if existing:
                self.pub.update_listing(existing['id'], {'status': 'error', 'error_message': msg})
            return {'success': False, 'error': msg, 'warnings': warnings}

        gid = result['id']
        url = result.get('preview_url') or self._admin_url(gid)
        listing_data = {
            'vehicle_id': vehicle['id'], 'platform_id': self.platform_id,
            'external_listing_id': gid, 'external_url': url,
            'status': 'published', 'error_message': None,
            'last_sync': datetime.now(timezone.utc),
        }
        if existing:
            self.pub.update_listing(existing['id'], {k: v for k, v in listing_data.items()
                                                     if k not in ('vehicle_id', 'platform_id')})
        else:
            listing_data['published_at'] = datetime.now(timezone.utc)
            self.pub.create_listing(listing_data)
        return {'success': True, 'external_id': gid, 'external_url': url, 'warnings': warnings}

    def update(self, external_id: str, vehicle_data: Dict[str, Any]) -> Dict[str, Any]:
        """Intentional no-op: updates flow through publish()'s idempotent upsert."""
        return {'success': True}

    def deactivate(self, external_id: str) -> Dict[str, Any]:
        res = self.client.set_product_status(external_id, 'ARCHIVED')
        if res['userErrors']:
            return {'success': False, 'error': str(res['userErrors'])}
        return {'success': True}

    def delete(self, external_id: str) -> Dict[str, Any]:
        res = self.client.set_product_status(external_id, 'ARCHIVED')
        return {'success': not res['userErrors']}

    def get_stats(self, external_id: str) -> Dict[str, Any]:
        return {'views': 0, 'inquiries': 0}
