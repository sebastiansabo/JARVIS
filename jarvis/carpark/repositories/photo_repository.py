"""Photo Repository — Data access for carpark_vehicle_photos."""
from typing import Optional, Dict, Any, List
from core.base_repository import BaseRepository


class PhotoRepository(BaseRepository):
    """Data access for vehicle photos and 360 images."""

    def get_by_vehicle(self, vehicle_id: int,
                       photo_type: str = None) -> List[Dict[str, Any]]:
        """List photos for a vehicle, optionally filtered by type.

        Soft-deleted photos (deleted_at set) are excluded — they are hidden
        immediately on delete and purged permanently after 24h.
        """
        sql = 'SELECT * FROM carpark_vehicle_photos WHERE vehicle_id = %s AND deleted_at IS NULL'
        params: list = [vehicle_id]
        if photo_type:
            sql += ' AND photo_type = %s'
            params.append(photo_type)
        sql += ' ORDER BY sort_order, id'
        return self.query_all(sql, tuple(params))

    def create(self, vehicle_id: int, url: str,
               photo_type: str = 'gallery',
               thumbnail_url: str = None,
               is_primary: bool = False,
               file_size: int = None,
               caption: str = None) -> Dict[str, Any]:
        """Add a photo to a vehicle."""
        # If this is set as primary, unset others first
        if is_primary:
            self.execute(
                'UPDATE carpark_vehicle_photos SET is_primary = FALSE WHERE vehicle_id = %s',
                (vehicle_id,)
            )

        # Get next sort_order
        row = self.query_one(
            'SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order FROM carpark_vehicle_photos WHERE vehicle_id = %s',
            (vehicle_id,)
        )
        next_order = row['next_order'] if row else 0

        return self.execute('''
            INSERT INTO carpark_vehicle_photos
                (vehicle_id, url, thumbnail_url, sort_order, is_primary, photo_type, file_size, caption)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        ''', (vehicle_id, url, thumbnail_url, next_order, is_primary,
              photo_type, file_size, caption), returning=True)

    def update(self, photo_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update photo metadata (sort_order, is_primary, caption)."""
        sets = []
        params = []
        for key in ('sort_order', 'is_primary', 'caption', 'photo_type'):
            if key in data:
                sets.append(f'{key} = %s')
                params.append(data[key])
        if not sets:
            return None

        # If setting as primary, unset others first
        if data.get('is_primary'):
            vehicle_row = self.query_one(
                'SELECT vehicle_id FROM carpark_vehicle_photos WHERE id = %s', (photo_id,)
            )
            if vehicle_row:
                self.execute(
                    'UPDATE carpark_vehicle_photos SET is_primary = FALSE WHERE vehicle_id = %s',
                    (vehicle_row['vehicle_id'],)
                )

        params.append(photo_id)
        return self.execute(
            f"UPDATE carpark_vehicle_photos SET {', '.join(sets)} WHERE id = %s RETURNING *",
            tuple(params), returning=True
        )

    def reorder(self, vehicle_id: int, photo_ids: List[int]) -> bool:
        """Batch reorder photos by setting sort_order from the array index."""
        def _work(cursor):
            for idx, pid in enumerate(photo_ids):
                cursor.execute(
                    'UPDATE carpark_vehicle_photos SET sort_order = %s WHERE id = %s AND vehicle_id = %s',
                    (idx, pid, vehicle_id)
                )
            return True
        return self.execute_many(_work)

    def soft_delete(self, photo_ids: List[int], vehicle_id: int = None) -> int:
        """Mark photos deleted (hidden now, purged after 24h). Returns count.

        When `vehicle_id` is given, only photos on that vehicle are affected
        (ownership scoping for the bulk endpoint)."""
        if not photo_ids:
            return 0
        sql = ('UPDATE carpark_vehicle_photos SET deleted_at = now() '
               'WHERE id = ANY(%s) AND deleted_at IS NULL')
        params: list = [list(photo_ids)]
        if vehicle_id is not None:
            sql += ' AND vehicle_id = %s'
            params.append(vehicle_id)
        return self.execute(sql, tuple(params))

    def expired_deleted(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Soft-deleted photos older than `hours` — ready for permanent purge."""
        return self.query_all(
            "SELECT id, url FROM carpark_vehicle_photos "
            "WHERE deleted_at IS NOT NULL AND deleted_at < now() - make_interval(hours => %s)",
            (hours,)
        )

    def delete(self, photo_id: int) -> bool:
        """Hard-delete a single photo row (used by the purge job)."""
        return self.execute(
            'DELETE FROM carpark_vehicle_photos WHERE id = %s', (photo_id,)
        ) > 0

    def delete_all(self, vehicle_id: int) -> int:
        """Delete all photos for a vehicle."""
        return self.execute(
            'DELETE FROM carpark_vehicle_photos WHERE vehicle_id = %s', (vehicle_id,)
        )

    def get_by_id(self, photo_id: int) -> Optional[Dict[str, Any]]:
        """Get a single photo by ID."""
        return self.query_one(
            'SELECT * FROM carpark_vehicle_photos WHERE id = %s', (photo_id,)
        )
