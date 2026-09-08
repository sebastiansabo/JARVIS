"""Vehicle Photo Repository — minimal data access for carpark_vehicle_photos
used by the Autovit import photo fallback (carpark/connectors/autovit/routes.py).

Note: carpark/repositories/photo_repository.py already exists for the
full photo-management UI (reorder, soft-delete, purge, ...). This repo is
intentionally separate and minimal, per the Autovit two-way-sync plan
(Task 3), which asks for a dedicated `VehiclePhotoRepository` with just the
`count`/`add` primitives the import fallback needs.
"""
from typing import Optional, Dict, Any
from core.base_repository import BaseRepository


class VehiclePhotoRepository(BaseRepository):
    """Data access for carpark_vehicle_photos (Autovit import fallback)."""

    def count(self, vehicle_id: int) -> int:
        """Total photo rows for a vehicle (used to decide whether the
        Autovit import fallback should seed any photos at all)."""
        row = self.query_one(
            'SELECT COUNT(*) AS n FROM carpark_vehicle_photos WHERE vehicle_id=%s',
            (vehicle_id,)
        )
        return int(row['n']) if row else 0

    def add(self, vehicle_id: int, url: str, thumbnail_url: str = None,
            sort_order: int = 0, is_primary: bool = False,
            photo_type: str = 'gallery') -> Dict[str, Any]:
        """Insert a single photo row and return the created record."""
        return self.execute(
            """INSERT INTO carpark_vehicle_photos
               (vehicle_id, url, thumbnail_url, sort_order, is_primary, photo_type)
               VALUES (%s,%s,%s,%s,%s,%s) RETURNING *""",
            (vehicle_id, url, thumbnail_url, sort_order, is_primary, photo_type),
            returning=True
        )
