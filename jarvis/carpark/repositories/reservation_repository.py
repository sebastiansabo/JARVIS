"""Reservation Repository — Data access for carpark_reservations."""
from typing import Optional, Dict, Any, List

from core.base_repository import BaseRepository


RESERVATION_FIELDS = (
    'client_id', 'client_name', 'client_company', 'client_phone', 'client_email',
    'user_id', 'reservation_start', 'reservation_end',
    'deposit_amount', 'deposit_paid', 'status', 'notes', 'created_by',
)


class ReservationRepository(BaseRepository):
    """Data access for vehicle reservation records."""

    def create(self, vehicle_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a reservation for a vehicle.

        `reservation_start` is NOT NULL in the schema with no DB-side
        default, so if the caller doesn't supply one it defaults to
        CURRENT_TIMESTAMP here.
        """
        safe = {k: data[k] for k in RESERVATION_FIELDS if k in data and data[k] is not None}

        cols = ['vehicle_id']
        placeholders = ['%s']
        vals: List[Any] = [vehicle_id]
        for key, value in safe.items():
            cols.append(key)
            placeholders.append('%s')
            vals.append(value)
        if 'reservation_start' not in safe:
            cols.append('reservation_start')
            placeholders.append('CURRENT_TIMESTAMP')

        col_str = ', '.join(cols)
        ph_str = ', '.join(placeholders)
        return self.execute(
            f'INSERT INTO carpark_reservations ({col_str}) VALUES ({ph_str}) RETURNING *',
            tuple(vals), returning=True
        )

    def active_for_vehicle(self, vehicle_id: int) -> Optional[Dict[str, Any]]:
        """Most recent active (status='active') reservation for a vehicle, or None."""
        return self.query_one('''
            SELECT * FROM carpark_reservations
            WHERE vehicle_id = %s AND status = 'active'
            ORDER BY reservation_end DESC NULLS LAST, id DESC
            LIMIT 1
        ''', (vehicle_id,))

    def set_status(self, reservation_id: int, status: str) -> Optional[Dict[str, Any]]:
        """Update a reservation's status. Returns the updated row."""
        return self.execute('''
            UPDATE carpark_reservations
            SET status = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING *
        ''', (status, reservation_id), returning=True)

    def expired(self, as_of_date) -> List[Dict[str, Any]]:
        """Active reservations whose reservation_end is before as_of_date."""
        return self.query_all('''
            SELECT * FROM carpark_reservations
            WHERE status = 'active' AND reservation_end < %s
            ORDER BY reservation_end ASC
        ''', (as_of_date,))
