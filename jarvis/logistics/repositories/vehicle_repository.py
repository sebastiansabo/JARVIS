"""Vehicle Repository — Data access for logistics_vehicles.

Mirrors carpark/repositories/vehicle_repository.py's style: BaseRepository
for connection handling, a server-field-safe whitelist for create/update, and
Json() wrapping for the JSONB column.
"""
from typing import Any, Dict, Optional

from psycopg2.extras import Json

from core.base_repository import BaseRepository

# JSONB columns on logistics_vehicles. psycopg2 cannot adapt a raw Python
# dict into JSONB directly (it raises "can't adapt type 'dict'"), so any
# dict value bound for one of these columns must be wrapped in Json().
VEHICLE_JSONB_FIELDS = {'confirmed_fields'}

# Fields a caller may set via create_vehicle()/update_vehicle() (whitelist —
# mirrors carpark's VEHICLE_UPDATABLE_FIELDS pattern). `id`, `created_at`,
# `updated_at` are server-controlled and excluded.
VEHICLE_FIELDS = {
    'order_ref', 'vin', 'model', 'plate', 'destinatie',
    'location_id', 'position_id', 'etapa_parc', 'predare',
    'eta', 'arrived_at', 'confirmed_fields', 'last_event_ts',
    'company_id',
}


def _adapt_jsonb(column: str, value: Any) -> Any:
    """Wrap a dict/list bound for a JSONB column in Json() so psycopg2 can
    adapt it. Strings (already-serialized JSON) and None pass through."""
    if column in VEHICLE_JSONB_FIELDS and isinstance(value, (dict, list)):
        return Json(value)
    return value


class LogisticsVehicleRepository(BaseRepository):
    """Data access for logistics_vehicles.

    Named `LogisticsVehicleRepository` (not `VehicleRepository`) — the
    modularity hook flags any class name duplicated across modules, and
    carpark already owns a `VehicleRepository`.
    """

    def get_vehicle_by_order_ref(self, order_ref: str, company_id: int = None) -> Optional[Dict[str, Any]]:
        """Lookup a vehicle by its order reference (the intake dedup key).

        order_ref is globally UNIQUE, so company_id is an extra safety filter
        (never a second disambiguating key) — pass None to look up regardless
        of tenant.
        """
        if company_id is not None:
            return self.query_one(
                'SELECT * FROM logistics_vehicles WHERE order_ref = %s AND company_id = %s',
                (order_ref, company_id),
            )
        return self.query_one(
            'SELECT * FROM logistics_vehicles WHERE order_ref = %s',
            (order_ref,),
        )

    def get_vehicle_by_id(self, vehicle_id: int) -> Optional[Dict[str, Any]]:
        """Full vehicle record by id."""
        return self.query_one('SELECT * FROM logistics_vehicles WHERE id = %s', (vehicle_id,))

    def create_vehicle(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a new vehicle. Returns the created record.

        Raises psycopg2.errors.UniqueViolation (via the DB) if order_ref
        already exists — callers rely on that for the intake pipeline's
        idempotent-create behaviour (Task 2).
        """
        safe_data = {k: v for k, v in data.items() if k in VEHICLE_FIELDS}
        if not safe_data.get('order_ref'):
            raise ValueError('order_ref is required')

        columns = list(safe_data.keys())
        placeholders = ', '.join(['%s'] * len(columns))
        col_names = ', '.join(columns)
        values = [_adapt_jsonb(c, safe_data[c]) for c in columns]

        return self.execute(
            f'INSERT INTO logistics_vehicles ({col_names}) VALUES ({placeholders}) RETURNING *',
            tuple(values), returning=True
        )

    def update_vehicle(self, vehicle_id: int, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update vehicle fields. Returns the updated record (or the
        unchanged current record if patch has no whitelisted fields)."""
        safe_data = {k: v for k, v in patch.items() if k in VEHICLE_FIELDS}
        if not safe_data:
            return self.get_vehicle_by_id(vehicle_id)

        sets = []
        params = []
        for key, value in safe_data.items():
            sets.append(f'{key} = %s')
            params.append(_adapt_jsonb(key, value))
        sets.append('updated_at = CURRENT_TIMESTAMP')

        params.append(vehicle_id)
        return self.execute(
            f"UPDATE logistics_vehicles SET {', '.join(sets)} WHERE id = %s RETURNING *",
            tuple(params), returning=True
        )
