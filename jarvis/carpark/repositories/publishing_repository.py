"""Publishing Repository — Data access for platforms, listings, and sync log."""
from typing import Optional, Dict, Any, List
from core.base_repository import BaseRepository


# ── Platforms ──

PLATFORM_FIELDS = (
    'name', 'platform_type', 'brand_scope', 'api_base_url',
    'api_key_encrypted', 'dealer_account_id', 'website_url',
    'icon_url', 'is_active', 'company_id', 'config',
)

PLATFORM_UPDATABLE = set(PLATFORM_FIELDS)

# ── Listings ──

LISTING_FIELDS = (
    'vehicle_id', 'platform_id', 'external_listing_id', 'status',
    'published_at', 'expires_at', 'external_url',
    'views', 'inquiries', 'last_sync', 'error_message',
)

LISTING_UPDATABLE = set(LISTING_FIELDS) - {'vehicle_id', 'platform_id'}


class PublishingRepository(BaseRepository):
    """Data access for publishing platforms, vehicle listings, and sync logs."""

    # ═══════════════════════════════════════════════
    # PLATFORMS
    # ═══════════════════════════════════════════════

    def list_platforms(self, company_id: int = None,
                       active_only: bool = False,
                       limit: int = 50) -> List[Dict[str, Any]]:
        sql = 'SELECT * FROM carpark_publishing_platforms WHERE 1=1'
        params: list = []
        if company_id:
            sql += ' AND (company_id = %s OR company_id IS NULL)'
            params.append(company_id)
        if active_only:
            sql += ' AND is_active = TRUE'
        sql += ' ORDER BY name ASC LIMIT %s'
        params.append(limit)
        return self.query_all(sql, tuple(params))

    def list_platforms_with_counts(self, company_id: int = None,
                                   active_only: bool = False,
                                   limit: int = 50) -> List[Dict[str, Any]]:
        """List platforms with active listing counts in a single query."""
        sql = '''
            SELECT p.*,
                   COALESCE(c.cnt, 0) AS active_listings
            FROM carpark_publishing_platforms p
            LEFT JOIN (
                SELECT platform_id, COUNT(*) AS cnt
                FROM carpark_vehicle_listings
                WHERE status = 'active'
                GROUP BY platform_id
            ) c ON c.platform_id = p.id
            WHERE 1=1
        '''
        params: list = []
        if company_id:
            sql += ' AND (p.company_id = %s OR p.company_id IS NULL)'
            params.append(company_id)
        if active_only:
            sql += ' AND p.is_active = TRUE'
        sql += ' ORDER BY p.name ASC LIMIT %s'
        params.append(limit)
        return self.query_all(sql, tuple(params))

    def get_platform(self, platform_id: int) -> Optional[Dict[str, Any]]:
        return self.query_one(
            'SELECT * FROM carpark_publishing_platforms WHERE id = %s', (platform_id,)
        )

    def create_platform(self, data: Dict[str, Any]) -> Dict[str, Any]:
        safe = {k: data[k] for k in PLATFORM_FIELDS if k in data and data[k] is not None}
        if 'name' not in safe:
            raise ValueError('Platform name is required')

        cols = list(safe.keys())
        vals = list(safe.values())
        placeholders = ', '.join(['%s'] * len(vals))
        col_str = ', '.join(cols)
        return self.execute(
            f'INSERT INTO carpark_publishing_platforms ({col_str}) VALUES ({placeholders}) RETURNING *',
            tuple(vals), returning=True
        )

    def update_platform(self, platform_id: int,
                        data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        sets = []
        params = []
        for key in PLATFORM_UPDATABLE:
            if key in data:
                sets.append(f'{key} = %s')
                params.append(data[key])
        if not sets:
            return None
        params.append(platform_id)
        return self.execute(
            f"UPDATE carpark_publishing_platforms SET {', '.join(sets)} WHERE id = %s RETURNING *",
            tuple(params), returning=True
        )

    def delete_platform(self, platform_id: int) -> bool:
        return self.execute(
            'DELETE FROM carpark_publishing_platforms WHERE id = %s', (platform_id,)
        ) > 0

    # ═══════════════════════════════════════════════
    # LISTINGS
    # ═══════════════════════════════════════════════

    def get_listings_for_vehicle(self, vehicle_id: int) -> List[Dict[str, Any]]:
        """Get all listings for a vehicle with platform info."""
        return self.query_all('''
            SELECT l.*, p.name AS platform_name, p.platform_type, p.icon_url
            FROM carpark_vehicle_listings l
            JOIN carpark_publishing_platforms p ON p.id = l.platform_id
            WHERE l.vehicle_id = %s
            ORDER BY p.name ASC
        ''', (vehicle_id,))

    def get_listing(self, listing_id: int) -> Optional[Dict[str, Any]]:
        return self.query_one(
            'SELECT * FROM carpark_vehicle_listings WHERE id = %s', (listing_id,)
        )

    def get_listing_by_vehicle_platform(self, vehicle_id: int,
                                        platform_id: int) -> Optional[Dict[str, Any]]:
        return self.query_one(
            'SELECT * FROM carpark_vehicle_listings WHERE vehicle_id = %s AND platform_id = %s',
            (vehicle_id, platform_id)
        )

    def create_listing(self, data: Dict[str, Any]) -> Dict[str, Any]:
        safe = {k: data[k] for k in LISTING_FIELDS if k in data and data[k] is not None}
        if 'vehicle_id' not in safe or 'platform_id' not in safe:
            raise ValueError('vehicle_id and platform_id are required')

        cols = list(safe.keys())
        vals = list(safe.values())
        placeholders = ', '.join(['%s'] * len(vals))
        col_str = ', '.join(cols)
        return self.execute(
            f'INSERT INTO carpark_vehicle_listings ({col_str}) VALUES ({placeholders}) RETURNING *',
            tuple(vals), returning=True
        )

    def update_listing(self, listing_id: int,
                       data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        sets = []
        params = []
        for key in LISTING_UPDATABLE:
            if key in data:
                sets.append(f'{key} = %s')
                params.append(data[key])
        if not sets:
            return None
        sets.append('updated_at = NOW()')
        params.append(listing_id)
        return self.execute(
            f"UPDATE carpark_vehicle_listings SET {', '.join(sets)} WHERE id = %s RETURNING *",
            tuple(params), returning=True
        )

    def delete_listing(self, listing_id: int) -> bool:
        return self.execute(
            'DELETE FROM carpark_vehicle_listings WHERE id = %s', (listing_id,)
        ) > 0

    def get_active_listings_count(self, platform_id: int = None) -> int:
        """Count active listings, optionally per platform."""
        if platform_id:
            row = self.query_one(
                "SELECT COUNT(*) AS cnt FROM carpark_vehicle_listings WHERE status = 'active' AND platform_id = %s",
                (platform_id,)
            )
        else:
            row = self.query_one(
                "SELECT COUNT(*) AS cnt FROM carpark_vehicle_listings WHERE status = 'active'"
            )
        return row['cnt'] if row else 0

    # ═══════════════════════════════════════════════
    # SYNC LOG
    # ═══════════════════════════════════════════════

    def log_sync(self, vehicle_id: int, platform_id: int,
                 action: str, success: bool,
                 request_payload: dict = None,
                 response_payload: dict = None,
                 http_status: int = None,
                 error_message: str = None) -> Dict[str, Any]:
        return self.execute('''
            INSERT INTO carpark_publishing_sync_log
                (vehicle_id, platform_id, action, request_payload,
                 response_payload, http_status, success, error_message)
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s) RETURNING *
        ''', (vehicle_id, platform_id, action,
              str(request_payload) if request_payload else None,
              str(response_payload) if response_payload else None,
              http_status, success, error_message),
            returning=True)

    def get_sync_log(self, vehicle_id: int = None,
                     platform_id: int = None,
                     limit: int = 50) -> List[Dict[str, Any]]:
        sql = 'SELECT sl.*, p.name AS platform_name FROM carpark_publishing_sync_log sl '
        sql += 'JOIN carpark_publishing_platforms p ON p.id = sl.platform_id '
        sql += 'WHERE 1=1'
        params: list = []
        if vehicle_id:
            sql += ' AND sl.vehicle_id = %s'
            params.append(vehicle_id)
        if platform_id:
            sql += ' AND sl.platform_id = %s'
            params.append(platform_id)
        sql += ' ORDER BY sl.created_at DESC LIMIT %s'
        params.append(limit)
        return self.query_all(sql, tuple(params))
