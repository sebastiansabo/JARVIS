"""Per-vehicle+platform auto-update schedule access."""
from typing import Optional, Dict, Any
from core.base_repository import BaseRepository


class ListingScheduleRepository(BaseRepository):
    def get(self, vehicle_id: int, platform_type: str) -> Optional[Dict[str, Any]]:
        return self.query_one(
            'SELECT * FROM carpark_listing_schedules WHERE vehicle_id = %s AND platform_type = %s',
            (vehicle_id, platform_type))

    def upsert(self, vehicle_id: int, platform_type: str, cadence: str,
               enabled: bool, next_run_at) -> Dict[str, Any]:
        return self.execute('''
            INSERT INTO carpark_listing_schedules
                (vehicle_id, platform_type, cadence, enabled, next_run_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (vehicle_id, platform_type) DO UPDATE
                SET cadence = EXCLUDED.cadence, enabled = EXCLUDED.enabled,
                    next_run_at = EXCLUDED.next_run_at, updated_at = NOW()
            RETURNING *
        ''', (vehicle_id, platform_type, cadence, enabled, next_run_at), returning=True)
