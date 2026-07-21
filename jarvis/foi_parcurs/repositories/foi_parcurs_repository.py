"""Data access for foi_de_parcurs and foi_de_parcurs_audit tables."""

import json
import logging
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.foi_parcurs.repository')


# Derived three-state status for Test Drive contracts, surfaced on the list and
# detail endpoints so the mobile app can badge each row without re-deriving:
#   complete   → the return form was submitted (status COMPLETED)
#   incomplete → the expected arrival time (return_datetime) has passed but no
#                return form was submitted yet
#   driving    → still out (no return yet, arrival time not passed / not set)
_TD_STATUS_SQL = (
    "CASE "
    "WHEN fp.status = 'COMPLETED' THEN 'complete' "
    "WHEN fp.return_datetime IS NOT NULL AND fp.return_datetime < NOW() THEN 'incomplete' "
    "ELSE 'driving' "
    "END AS td_status"
)


class FoiParcursRepository(BaseRepository):

    def create_contract(self, data: dict) -> dict:
        """INSERT into foi_de_parcurs with RETURNING *."""
        cols = list(data.keys())
        placeholders = ', '.join(['%s'] * len(cols))
        col_names = ', '.join(cols)
        sql = f'INSERT INTO foi_de_parcurs ({col_names}) VALUES ({placeholders}) RETURNING *'
        return self.execute(sql, tuple(data[c] for c in cols), returning=True)

    def create_audit_entry(self, data: dict) -> dict:
        """INSERT into foi_de_parcurs_audit."""
        cols = list(data.keys())
        placeholders = ', '.join(['%s'] * len(cols))
        col_names = ', '.join(cols)
        sql = f'INSERT INTO foi_de_parcurs_audit ({col_names}) VALUES ({placeholders}) RETURNING *'
        return self.execute(sql, tuple(data[c] for c in cols), returning=True)

    def get_contracts(self, vin=None, company_id=None, status=None,
                      batch_id=None, page=1, per_page=25,
                      sort_by='created_at', sort_dir='DESC',
                      date_from=None, date_to=None, route_type=None):
        """Paginated list with optional filters. Returns (rows, total).

        date_from/date_to filter on the drive date (departure_datetime, falling
        back to created_at); date_to is inclusive of the whole day."""
        allowed_sort = {'created_at', 'contract_id', 'vin', 'km_start', 'km_end',
                        'route_type', 'distance_km', 'status', 'batch_id'}
        if sort_by not in allowed_sort:
            sort_by = 'created_at'
        if sort_dir.upper() not in ('ASC', 'DESC'):
            sort_dir = 'DESC'

        where_clauses = []
        params = []

        if vin:
            where_clauses.append('fp.vin = %s')
            params.append(vin)
        if company_id:
            where_clauses.append('fp.company_id = %s')
            params.append(company_id)
        if status:
            where_clauses.append('fp.status = %s')
            params.append(status)
        if batch_id:
            where_clauses.append('fp.batch_id = %s')
            params.append(batch_id)
        if route_type:
            where_clauses.append('fp.route_type = %s')
            params.append(route_type)
        if date_from:
            where_clauses.append('COALESCE(fp.departure_datetime, fp.created_at) >= %s')
            params.append(date_from)
        if date_to:
            # inclusive of the whole end day
            where_clauses.append('COALESCE(fp.departure_datetime, fp.created_at) < (%s::date + INTERVAL \'1 day\')')
            params.append(date_to)

        where_sql = (' WHERE ' + ' AND '.join(where_clauses)) if where_clauses else ''

        count_row = self.query_one(
            f'SELECT COUNT(*) AS total FROM foi_de_parcurs fp{where_sql}',
            tuple(params),
        )
        total = count_row['total'] if count_row else 0

        offset = (page - 1) * per_page
        data_sql = (
            f'SELECT fp.*, '
            f'COALESCE(fp.client_name, c.name) AS client_name, '
            f'COALESCE(fp.client_phone, c.phone) AS client_phone, '
            f'co.company AS company_name, '
            f'{_TD_STATUS_SQL} '
            f'FROM foi_de_parcurs fp '
            f'LEFT JOIN fp_clients c ON c.id = fp.client_id '
            f'LEFT JOIN companies co ON co.id = fp.company_id'
            f'{where_sql} '
            f'ORDER BY fp.{sort_by} {sort_dir} '
            f'LIMIT %s OFFSET %s'
        )
        params.extend([per_page, offset])
        rows = self.query_all(data_sql, tuple(params))

        return rows, total

    def delete_contract(self, contract_id: int):
        """Permanently delete a foi_de_parcurs row (admin/test cleanup)."""
        self.execute('DELETE FROM foi_de_parcurs WHERE id = %s', (contract_id,))

    def reset_return(self, contract_id: int) -> dict:
        """Admin/test: revert a Test Drive to 'driving' — clear the return data
        (km_end back to km_start, fuel/damage/signatures/returned_at reset) and
        set status back to FILLED, so the return flow can be re-tested. The
        vehicle's stored odometer is left as-is (not un-advanced)."""
        sql = (
            "UPDATE foi_de_parcurs SET "
            "status = 'FILLED', returned_at = NULL, "
            "km_end = km_start, fuel_gauge_end_level = NULL, "
            "return_damage = '[]'::jsonb, return_notes = NULL, "
            "return_advisor_signature = NULL, return_client_signature = NULL, "
            "updated_at = NOW() "
            "WHERE id = %s AND route_type = 'TD' RETURNING *"
        )
        row = self.execute(sql, (contract_id,), returning=True)
        if row and row.get('id'):
            return self.get_contract_by_id(row['id']) or row
        return row

    def get_odometer_readings(self, vin: str) -> list:
        """All drives for a VIN in chronological order (departure time, falling
        back to created_at) — every route_type, so odometer continuity/gap
        analysis isn't fooled by non-TD drives. Only the fields needed for the
        odometer history."""
        return self.query_all(
            '''SELECT fp.id, fp.contract_id, fp.route_type, fp.status,
                      fp.km_start, fp.km_end, fp.returned_at,
                      fp.departure_datetime, fp.return_datetime, fp.created_at,
                      fp.departure_damage, fp.return_damage,
                      COALESCE(fp.client_name, c.name) AS client_name
               FROM foi_de_parcurs fp
               LEFT JOIN fp_clients c ON c.id = fp.client_id
               WHERE fp.vin = %s
               ORDER BY COALESCE(fp.departure_datetime, fp.created_at) ASC, fp.id ASC''',
            (vin,),
        )

    def get_contract_by_id(self, contract_id: int) -> dict:
        """Single contract with client + company + vehicle join."""
        sql = (
            'SELECT fp.*, '
            'COALESCE(fp.client_name, cc.display_name, c.name) AS client_name, '
            'COALESCE(fp.client_phone, cc.phone, c.phone) AS client_phone, '
            'COALESCE(cc.email, c.email) AS client_email, '
            "COALESCE(NULLIF(TRIM(CONCAT_WS(', ', cc.street, cc.city, cc.region)), ''), c.address) AS client_address, "
            'co.company AS company_name, '
            'v.mark AS vehicle_mark, v.model AS vehicle_model, '
            'v.registration_number AS vehicle_registration_number, '
            'v.brand AS vehicle_brand, v.fuel_type AS vehicle_fuel_type, '
            f'{_TD_STATUS_SQL} '
            'FROM foi_de_parcurs fp '
            'LEFT JOIN fp_clients c ON c.id = fp.client_id '
            'LEFT JOIN crm_clients cc ON cc.id = fp.client_id '
            'LEFT JOIN companies co ON co.id = fp.company_id '
            'LEFT JOIN fp_vehicles v ON v.vin = fp.vin '
            'WHERE fp.id = %s'
        )
        return self.query_one(sql, (contract_id,))

    def get_contracts_by_batch_id(self, batch_id: str) -> list:
        """Get all contracts for a batch."""
        sql = (
            'SELECT fp.*, '
            'c.name AS client_name, c.phone AS client_phone, '
            'co.company AS company_name '
            'FROM foi_de_parcurs fp '
            'LEFT JOIN fp_clients c ON c.id = fp.client_id '
            'LEFT JOIN companies co ON co.id = fp.company_id '
            'WHERE fp.batch_id = %s '
            'ORDER BY fp.slot_number ASC'
        )
        return self.query_all(sql, (batch_id,))

    def create_from_td_form(self, data: dict) -> dict:
        """Create a FILLED contract from test drive form data.

        `data` may include `client_name`/`client_phone` (resolved from the CRM
        client at submission time) — these are inserted as columns on
        foi_de_parcurs like any other key, since this INSERT is column-driven
        by whatever keys the caller provides.
        """
        cols = list(data.keys())
        placeholders = ', '.join(['%s'] * len(cols))
        col_names = ', '.join(cols)
        sql = f'INSERT INTO foi_de_parcurs ({col_names}) VALUES ({placeholders}) RETURNING *'
        row = self.execute(sql, tuple(data[c] for c in cols), returning=True)
        if row and row.get('id'):
            return self.get_contract_by_id(row['id']) or row
        return row

    def allocate_client(self, contract_id: int, data: dict) -> dict:
        """Update a PENDING contract with client allocation data."""
        sets = ', '.join(f'{k} = %s' for k in data.keys())
        sql = f'UPDATE foi_de_parcurs SET {sets}, updated_at = NOW() WHERE id = %s RETURNING *'
        params = list(data.values()) + [contract_id]
        return self.execute(sql, tuple(params), returning=True)

    def update_plan(self, contract_id: int, data: dict) -> dict:
        """Edit a PLANNED draft's fields (date/time/vehicle/client/etc.) without
        activating it — PLANNED-only, status unchanged."""
        data = dict(data)
        if 'departure_damage' in data and not isinstance(data['departure_damage'], str):
            data['departure_damage'] = json.dumps(data['departure_damage'])
        sets = ', '.join(f'{k} = %s' for k in data.keys())
        sql = (
            f'UPDATE foi_de_parcurs SET {sets}, updated_at = NOW() '
            f"WHERE id = %s AND route_type = 'TD' AND status = 'PLANNED' RETURNING *"
        )
        params = list(data.values()) + [contract_id]
        row = self.execute(sql, tuple(params), returning=True)
        if row and row.get('id'):
            return self.get_contract_by_id(row['id']) or row
        return row

    def record_return(self, contract_id: int, data: dict) -> dict:
        """Update a TD contract with return data (km/fuel/damage/signatures) and mark COMPLETED.

        `return_datetime` (if provided in data) is stored as-is; if missing/falsy,
        it defaults to NOW() via COALESCE.
        """
        data = dict(data)
        if 'return_damage' in data:
            data['return_damage'] = json.dumps(data['return_damage'])
        return_datetime = data.pop('return_datetime', None)

        sets = [f'{k} = %s' for k in data.keys()]
        params = list(data.values())
        sets.append('return_datetime = COALESCE(%s, NOW())')
        params.append(return_datetime)

        sets_sql = ', '.join(sets)
        sql = (
            f'UPDATE foi_de_parcurs SET {sets_sql}, '
            f"returned_at = NOW(), status = 'COMPLETED', updated_at = NOW() "
            f"WHERE id = %s AND route_type = 'TD' RETURNING *"
        )
        params.append(contract_id)
        row = self.execute(sql, tuple(params), returning=True)
        if row and row.get('id'):
            return self.get_contract_by_id(row['id']) or row
        return row

    def find_conflicts(self, vin: str, frm, to, exclude_id: int | None = None) -> list:
        """TD sessions on `vin` whose [departure, COALESCE(return, departure)]
        window overlaps [frm, to] and which are still open — PLANNED drafts or
        live drives (out now / overdue). Excludes `exclude_id`."""
        params = [vin, to, frm]
        exclude_sql = ''
        if exclude_id is not None:
            exclude_sql = ' AND fp.id <> %s'
            params.append(exclude_id)
        sql = (
            "SELECT fp.id, fp.contract_id, fp.status, fp.departure_datetime, fp.return_datetime, "
            "COALESCE(fp.client_name, c.name) AS client_name, fp.advisor_name "
            "FROM foi_de_parcurs fp "
            "LEFT JOIN fp_clients c ON c.id = fp.client_id "
            "WHERE fp.vin = %s AND fp.route_type = 'TD' "
            # overlap: existing.dep <= new.to AND new.frm <= existing.end
            "AND fp.departure_datetime <= %s "
            "AND COALESCE(fp.return_datetime, fp.departure_datetime) >= %s "
            "AND ( fp.status = 'PLANNED' "
            "      OR (fp.status <> 'COMPLETED' AND fp.status <> 'PENDING') ) "
            f"{exclude_sql} "
            "ORDER BY fp.departure_datetime ASC"
        )
        return self.query_all(sql, tuple(params))

    def record_activation(self, contract_id: int, data: dict) -> dict:
        """Turn a PLANNED draft into a live FILLED contract: write the handover
        fields (km/fuel/signatures/departure) and set status='FILLED'."""
        data = dict(data)
        if 'departure_damage' in data and not isinstance(data['departure_damage'], str):
            data['departure_damage'] = json.dumps(data['departure_damage'])
        sets = ', '.join(f'{k} = %s' for k in data.keys())
        sql = (
            f'UPDATE foi_de_parcurs SET {sets}, '
            f"status = 'FILLED', updated_at = NOW() "
            f"WHERE id = %s AND route_type = 'TD' AND status = 'PLANNED' RETURNING *"
        )
        params = list(data.values()) + [contract_id]
        row = self.execute(sql, tuple(params), returning=True)
        if row and row.get('id'):
            return self.get_contract_by_id(row['id']) or row
        return row
