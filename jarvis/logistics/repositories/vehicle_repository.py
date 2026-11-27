"""Vehicle Repository — Data access for logistics_vehicles.

Mirrors carpark/repositories/vehicle_repository.py's style: BaseRepository
for connection handling, a server-field-safe whitelist for create/update, and
Json() wrapping for the JSONB column.
"""
from typing import Any, Dict, List, Optional

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


# Parc register (Task 6) — whitelist mapping each sortable display column to
# its real SQL expression. Keys are exactly the 8 display columns from the
# design spec (§4.1); `filters['sort']` is looked up here, never interpolated
# raw, so an unknown/absent key can never become a SQL-injection vector or an
# "unknown column" error -- it just falls through to the stable default order.
_VEHICLE_SORT_COLUMNS = {
    'vehicul': 'v.model',
    'comanda': 'v.order_ref',
    'locatie': 'l.name',
    'pozitie': 'p.code',
    'destinatie': 'v.destinatie',
    'etapa_parc': 'v.etapa_parc',
    'predare': 'v.predare',
    'vin': 'v.vin',
}


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

    def update_vehicle(self, vehicle_id: int, patch: Dict[str, Any], cursor=None) -> Optional[Dict[str, Any]]:
        """Update vehicle fields. Returns the updated record (or the
        unchanged current record if patch has no whitelisted fields).

        `cursor` (optional): run on an already-open shared cursor inside an
        execute_many() transaction instead of auto-committing — lets the
        reception-confirm move (moves.py) write the vehicle, task status, and
        history rows atomically.
        """
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
        sql = f"UPDATE logistics_vehicles SET {', '.join(sets)} WHERE id = %s RETURNING *"
        if cursor is not None:
            return self._execute_on_cursor(cursor, sql, tuple(params), returning=True)
        return self.execute(sql, tuple(params), returning=True)

    def list_vehicles(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parc register — the flat vehicle list behind GET /api/logistics/vehicles.

        `filters` (all optional except `company_id`):
          q            — free-text search against VIN / order_ref / model / plate
                         (NULL vin is treated as empty via COALESCE, so a
                         not-yet-received car with no VIN still matches on
                         order_ref/model without the query erroring).
          location_id  — exact match on logistics_vehicles.location_id
          destinatie   — exact match (`Intern`/`AAP`/`Export`/`Expunere`)
          etapa        — exact match on etapa_parc
          predare      — exact match on predare
          sort         — one of the 8 display columns (see
                         `_VEHICLE_SORT_COLUMNS`); unknown/absent -> default order
          dir          — 'asc' (default) or 'desc'; anything else -> 'asc'
          company_id   — tenant scope (every query is scoped by this)

        Returns rows shaped for the Parc table: the 8 display columns
        (vehicul, comanda, locatie, pozitie, destinatie, etapa_parc, predare,
        vin) plus id/location_id/position_id for the row-click -> detail nav.

        Order is always stable: an explicit `sort` is tie-broken by `v.id`,
        and with no (or an unrecognized) `sort` the whole result falls back
        to `v.id ASC` (insertion order) -- never "whatever Postgres felt like
        today" for two rows with equal sort keys.
        """
        where = ['v.company_id = %s']
        params: list = [filters.get('company_id')]

        q = filters.get('q')
        if q:
            like = f'%{q}%'
            where.append(
                "(COALESCE(v.vin, '') ILIKE %s OR v.order_ref ILIKE %s "
                "OR COALESCE(v.model, '') ILIKE %s OR COALESCE(v.plate, '') ILIKE %s)"
            )
            params.extend([like, like, like, like])

        location_id = filters.get('location_id')
        if location_id is not None:
            where.append('v.location_id = %s')
            params.append(location_id)

        destinatie = filters.get('destinatie')
        if destinatie:
            where.append('v.destinatie = %s')
            params.append(destinatie)

        etapa = filters.get('etapa')
        if etapa:
            where.append('v.etapa_parc = %s')
            params.append(etapa)

        predare = filters.get('predare')
        if predare:
            where.append('v.predare = %s')
            params.append(predare)

        sort_col = _VEHICLE_SORT_COLUMNS.get(filters.get('sort'))
        if sort_col is None:
            order_clause = 'v.id ASC'
        else:
            direction = 'DESC' if str(filters.get('dir', 'asc')).lower() == 'desc' else 'ASC'
            order_clause = f'{sort_col} {direction}, v.id ASC'

        sql = f'''
            SELECT
                v.id, v.model AS vehicul, v.order_ref AS comanda,
                l.name AS locatie, p.code AS pozitie,
                v.destinatie, v.etapa_parc, v.predare, v.vin,
                v.location_id, v.position_id
            FROM logistics_vehicles v
            LEFT JOIN logistics_locations l ON v.location_id = l.id
            LEFT JOIN logistics_positions p ON v.position_id = p.id
            WHERE {' AND '.join(where)}
            ORDER BY {order_clause}
        '''
        return self.query_all(sql, tuple(params))
