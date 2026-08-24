"""Data access for foi_de_parcurs and foi_de_parcurs_audit tables."""

import json
import logging
from core.base_repository import BaseRepository
from foi_parcurs.session_lifecycle import TD_STATUS_SQL as _TD_STATUS_SQL, NOW_LOCAL_SQL, GRACE_HOURS

logger = logging.getLogger('jarvis.foi_parcurs.repository')


# Lean column set for the LIST endpoint — every scalar the sessions/contracts/
# calendar views render, but NONE of the heavy base64/JSON blobs (signatures,
# driver-license photo, damage-with-photos, general-conditions text) which add
# ~155 kB/row. The list never displays those; the detail endpoint
# (get_contract_by_id) keeps them for the form/PDF. client_name/phone are
# replaced by the COALESCE aliases, so they're omitted here.
_LIST_COLUMNS = (
    'fp.id, fp.contract_id, fp.batch_id, fp.vin, fp.client_id, fp.company_id, '
    'fp.year, fp.month, fp.route_type, fp.slot_number, fp.km_start, fp.km_end, '
    'fp.distance_km, fp.fuel_tank_capacity_liters, fp.fuel_gauge_start_level, '
    'fp.fuel_gauge_end_level, fp.fuel_start_liters, fp.fuel_end_liters, '
    'fp.fuel_consumed_liters, fp.itinerary, fp.general_observation, fp.advisor_name, fp.status, '
    'fp.created_at, fp.updated_at, fp.registration_number, fp.departure_datetime, '
    'fp.return_datetime, fp.returned_at, fp.return_notes, fp.source, '
    'fp.driver_license_number, fp.driver_license_expiry, fp.gdpr_consent, '
    'fp.inspection_acceptance, fp.inspection_id, fp.general_conditions_accepted, '
    'fp.general_conditions_accepted_at, fp.pdf_legal_path, fp.pdf_custom_path, '
    'fp.corrected_at, fp.corrected_by, '
    'fp.is_internal, '
    'fp.driver_name, fp.driver_contact_id, fp.event_id, '
    'fp.document_type, fp.service_order_ref'
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
                      date_from=None, date_to=None, route_type=None,
                      document_type=None, lean=False):
        """Paginated list with optional filters. Returns (rows, total).

        date_from/date_to filter on the drive date (departure_datetime, falling
        back to created_at); date_to is inclusive of the whole day.

        `lean=True` selects only the light columns (_LIST_COLUMNS) — the list
        views never render the base64 blobs, so this drops ~155 kB/row of
        payload. Callers that need the full row (e.g. PDF re-generation for the
        ZIP export) leave lean=False."""
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
        if document_type:
            where_clauses.append('fp.document_type = %s')
            params.append(document_type)
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
        base_cols = _LIST_COLUMNS if lean else 'fp.*'
        data_sql = (
            f'SELECT {base_cols}, '
            f'COALESCE(fp.client_name, c.name) AS client_name, '
            f'COALESCE(fp.client_phone, c.phone) AS client_phone, '
            f'co.company AS company_name, '
            f'cc.company_name AS client_company, '
            f'he.name AS event_name, '
            f'{_TD_STATUS_SQL} '
            f'FROM foi_de_parcurs fp '
            f'LEFT JOIN fp_clients c ON c.id = fp.client_id '
            f'LEFT JOIN crm_clients cc ON cc.id = fp.client_id '
            f'LEFT JOIN companies co ON co.id = fp.company_id '
            f'LEFT JOIN hr.events he ON he.id = fp.event_id'
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

    def get_mileage_floor(self, vin: str, exclude_id: int | None = None) -> int:
        """Highest known mileage for a car: the greater of its stored odometer
        and the largest km_end across its real (non-draft) sessions. Used to keep
        a session's starting odometer from dropping below the car's reality.
        exclude_id skips one session (the draft being activated) so its own
        placeholder km_end doesn't inflate the floor."""
        row = self.query_one(
            '''SELECT GREATEST(
                 COALESCE((SELECT odometer_km FROM fp_vehicles WHERE vin = %s), 0),
                 COALESCE((SELECT MAX(km_end) FROM foi_de_parcurs
                            WHERE vin = %s AND status <> 'PLANNED'
                              AND (%s::int IS NULL OR id <> %s)), 0)
               ) AS floor''',
            (vin, vin, exclude_id, exclude_id),
        )
        return int(row['floor']) if row and row.get('floor') is not None else 0

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
            'cc.company_name AS client_company, '
            'v.mark AS vehicle_mark, v.model AS vehicle_model, '
            'v.registration_number AS vehicle_registration_number, '
            'v.brand AS vehicle_brand, v.fuel_type AS vehicle_fuel_type, '
            'mp.name AS mkt_project_name, '
            'he.name AS event_name, '
            f'{_TD_STATUS_SQL} '
            'FROM foi_de_parcurs fp '
            'LEFT JOIN fp_clients c ON c.id = fp.client_id '
            'LEFT JOIN crm_clients cc ON cc.id = fp.client_id '
            'LEFT JOIN companies co ON co.id = fp.company_id '
            'LEFT JOIN fp_vehicles v ON v.vin = fp.vin '
            'LEFT JOIN mkt_projects mp ON mp.id = fp.mkt_project_id '
            'LEFT JOIN hr.events he ON he.id = fp.event_id '
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

    def reschedule_session(self, contract_id: int, departure_datetime, return_datetime) -> dict:
        """Move a PLANNED/MISSED session to a new time and revive it to PLANNED,
        clearing the missed/late-notify stamps. Guarded to those two statuses."""
        sql = (
            "UPDATE foi_de_parcurs SET departure_datetime = %s, return_datetime = %s, "
            "status = 'PLANNED', missed_at = NULL, late_notified_at = NULL, updated_at = NOW() "
            "WHERE id = %s AND route_type = 'TD' AND status IN ('PLANNED', 'MISSED') RETURNING *"
        )
        row = self.execute(sql, (departure_datetime, return_datetime, contract_id), returning=True)
        if row and row.get('id'):
            return self.get_contract_by_id(row['id']) or row
        return row

    def correct_session(self, contract_id: int, fields: dict, modified_by=None) -> dict:
        """Admin correction of a session's drive date(s) and/or odometer readings
        to fix data-entry anomalies (wrong date, overlapping km). Whitelisted
        columns only; applies to ANY status; bumps updated_at and stamps
        corrected_at/corrected_by (the "Modificat" audit marker). Returns the
        fresh row. Validation (km_end >= km_start, return >= departure, admin
        gate) lives in the route — this is the persistence primitive."""
        allowed = ('departure_datetime', 'return_datetime', 'km_start', 'km_end')
        sets = {k: fields[k] for k in allowed if k in fields}
        if not sets:
            return self.get_contract_by_id(contract_id)
        cols = ', '.join(f'{k} = %s' for k in sets)
        params = list(sets.values()) + [modified_by, contract_id]
        sql = (f'UPDATE foi_de_parcurs SET {cols}, corrected_at = NOW(), corrected_by = %s, '
               f'updated_at = NOW() WHERE id = %s RETURNING id')
        row = self.execute(sql, tuple(params), returning=True)
        return self.get_contract_by_id(row['id']) if row and row.get('id') else None

    def extend_return(self, contract_id: int, return_datetime, modified_by=None) -> dict:
        """Advisor extends/changes the return time of an OPEN (FILLED) TD session.
        Stamps corrected_at/corrected_by and clears the overdue-return alert
        cooldown so a fresh overdue can re-notify. Guarded to open TD sessions;
        returns the fresh row, or None if the session is not extendable."""
        sql = (
            "UPDATE foi_de_parcurs SET return_datetime = %s, corrected_at = NOW(), "
            "corrected_by = %s, updated_at = NOW() "
            "WHERE id = %s AND route_type = 'TD' AND status = 'FILLED' RETURNING id"
        )
        row = self.execute(sql, (return_datetime, modified_by, contract_id), returning=True)
        if not (row and row.get('id')):
            return None
        # The return moved — let a future overdue re-alert from scratch.
        try:
            self.execute(
                "DELETE FROM smart_notification_state WHERE alert_type = 'fp_return_overdue' "
                "AND entity_type = 'foi_parcurs_td' AND entity_id = %s", (contract_id,))
        except Exception:
            logger.warning('Could not clear overdue-return cooldown for %s', contract_id, exc_info=True)
        return self.get_contract_by_id(contract_id)

    def revive_to_active_if_window_open(self, contract_id: int) -> dict:
        """After an admin correction, revive a MISSED / late-PLANNED TD session to
        FILLED ("În desfășurare") when its corrected window is currently active —
        departure already passed and the return is still in the future. Clears the
        missed stamp. Returns the fresh FILLED row if flipped, else None (window
        not active, or the session isn't a revivable MISSED/PLANNED TD)."""
        sql = (
            "UPDATE foi_de_parcurs SET status = 'FILLED', missed_at = NULL, updated_at = NOW() "
            "WHERE id = %s AND route_type = 'TD' AND status IN ('MISSED', 'PLANNED') "
            f"AND departure_datetime <= {NOW_LOCAL_SQL} "
            f"AND return_datetime IS NOT NULL AND return_datetime > {NOW_LOCAL_SQL} "
            "RETURNING id"
        )
        row = self.execute(sql, (contract_id,), returning=True)
        return self.get_contract_by_id(contract_id) if row and row.get('id') else None

    def get_sessions_pending_late_notify(self) -> list:
        """PLANNED TD rows whose start just passed (still in the 8h grace) and
        that haven't been late-notified yet."""
        sql = (
            "SELECT fp.id, fp.advisor_name, "
            "COALESCE(fp.client_name, c.name) AS client_name, fp.vin, fp.departure_datetime "
            "FROM foi_de_parcurs fp LEFT JOIN fp_clients c ON c.id = fp.client_id "
            "WHERE fp.route_type = 'TD' AND fp.status = 'PLANNED' "
            f"AND fp.departure_datetime < {NOW_LOCAL_SQL} "
            f"AND fp.departure_datetime + INTERVAL '{GRACE_HOURS} hours' >= {NOW_LOCAL_SQL} "
            "AND fp.late_notified_at IS NULL"
        )
        return self.query_all(sql)

    def mark_late_notified(self, contract_id: int) -> None:
        self.execute('UPDATE foi_de_parcurs SET late_notified_at = NOW() WHERE id = %s', (contract_id,))

    def get_ids_to_miss(self) -> list:
        """IDs of PLANNED TD rows past the 8h grace (about to be flipped to
        MISSED) — fetched so the lifecycle cron can log each PLANNED→MISSED
        status change before archive_missed_sessions() flips them in bulk."""
        rows = self.query_all(
            "SELECT id FROM foi_de_parcurs WHERE route_type = 'TD' AND status = 'PLANNED' "
            f"AND departure_datetime + INTERVAL '{GRACE_HOURS} hours' < {NOW_LOCAL_SQL}"
        )
        return [r['id'] for r in (rows or [])]

    def archive_missed_sessions(self) -> int:
        """Flip PLANNED TD rows past the 8h grace to MISSED. Returns the count.

        `BaseRepository.execute(..., returning=False)` commits and returns the
        rowcount — exactly the number archived — so no RETURNING is needed."""
        return self.execute(
            "UPDATE foi_de_parcurs SET status = 'MISSED', missed_at = NOW(), updated_at = NOW() "
            "WHERE route_type = 'TD' AND status = 'PLANNED' "
            f"AND departure_datetime + INTERVAL '{GRACE_HOURS} hours' < {NOW_LOCAL_SQL}"
        ) or 0

    def get_advisor_user_id(self, advisor_name):
        """Resolve a session's advisor (by name) to a users.id, or None."""
        name = (advisor_name or '').strip()
        if not name:
            return None
        row = self.query_one(
            'SELECT id FROM users WHERE LOWER(name) = LOWER(%s) ORDER BY id LIMIT 1', (name,)
        )
        return row['id'] if row else None

    def get_overdue_return_sessions(self) -> list:
        """Active TD sessions (FILLED) whose scheduled return passed >2h ago and
        that the consilier never returned — i.e. the derived 'incomplete' state
        plus a 2h grace. Excludes any already alerted within the 4h cooldown
        (smart_notification_state), so callers just iterate and send. Joins the
        advisor (users), company and vehicle so the caller can notify + email +
        resolve the brand CC without extra queries."""
        sql = (
            "SELECT fp.id, fp.advisor_name, au.id AS advisor_user_id, au.email AS advisor_email, "
            "COALESCE(fp.client_name, c.name) AS client_name, fp.vin, "
            "v.mark, v.model, fp.registration_number, fp.return_datetime, "
            "fp.company_id, co.company AS company_name, v.brand AS vehicle_brand, "
            f"CEIL(EXTRACT(EPOCH FROM ({NOW_LOCAL_SQL} - fp.return_datetime)) / 3600.0)::int AS overdue_hours "
            "FROM foi_de_parcurs fp "
            "LEFT JOIN fp_clients c ON c.id = fp.client_id "
            "LEFT JOIN companies co ON co.id = fp.company_id "
            "LEFT JOIN fp_vehicles v ON v.vin = fp.vin "
            "LEFT JOIN LATERAL (SELECT id, email FROM users "
            "WHERE LOWER(name) = LOWER(fp.advisor_name) ORDER BY id LIMIT 1) au ON TRUE "
            "WHERE fp.route_type = 'TD' AND fp.status = 'FILLED' "
            "AND fp.return_datetime IS NOT NULL "
            f"AND fp.return_datetime + INTERVAL '2 hours' < {NOW_LOCAL_SQL} "
            "AND NOT EXISTS ("
            "SELECT 1 FROM smart_notification_state s "
            "WHERE s.alert_type = 'fp_return_overdue' AND s.entity_type = 'foi_parcurs_td' "
            "AND s.entity_id = fp.id "
            "AND s.last_alerted_at > CURRENT_TIMESTAMP - INTERVAL '4 hours')"
        )
        return self.query_all(sql)

    def mark_overdue_return_notified(self, session_id: int) -> None:
        """Record/refresh the 4h cooldown for a session's overdue-return alert."""
        self.execute(
            "INSERT INTO smart_notification_state (alert_type, entity_type, entity_id, last_alerted_at) "
            "VALUES ('fp_return_overdue', 'foi_parcurs_td', %s, CURRENT_TIMESTAMP) "
            "ON CONFLICT (alert_type, entity_type, entity_id) "
            "DO UPDATE SET last_alerted_at = CURRENT_TIMESTAMP",
            (session_id,),
        )

    # ── Session history log (foi_parcurs_session_events) ──
    def log_session_event(self, session_id: int, action: str, actor: str | None = None) -> None:
        """Append one audit row for a session mutation (create/activate/return/
        correct/extend/reschedule/reset/…). `actor` is the acting user's display
        name (or email); NULL for system actions. Best-effort — callers guard so
        a log failure never breaks the underlying action."""
        self.execute(
            'INSERT INTO foi_parcurs_session_events (session_id, action, actor) '
            'VALUES (%s, %s, %s)',
            (session_id, action, actor),
        )

    def get_session_events(self, session_id: int) -> list:
        """A session's audit trail, newest first — for the history modal."""
        return self.query_all(
            'SELECT id, action, actor, created_at FROM foi_parcurs_session_events '
            'WHERE session_id = %s ORDER BY created_at DESC, id DESC',
            (session_id,),
        )

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
        # TD datetimes are naive wall-clock (stored as digits, displayed as-is).
        # The auto return time must therefore be the *local* wall-clock, not UTC
        # NOW(), or a returned session shows ~3h behind its departure.
        sets.append("return_datetime = COALESCE(%s::timestamptz, (NOW() AT TIME ZONE 'Europe/Bucharest')::timestamptz)")
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
            # A missed slot frees the vehicle: drop MISSED and PLANNED rows already
            # past the 8h grace (archived on the next sweeper pass). In-grace 'late'
            # rows still block — the client may yet show up.
            "AND fp.status <> 'MISSED' "
            f"AND NOT (fp.status = 'PLANNED' AND fp.departure_datetime + INTERVAL '{GRACE_HOURS} hours' < {NOW_LOCAL_SQL}) "
            f"{exclude_sql} "
            "ORDER BY fp.departure_datetime ASC"
        )
        return self.query_all(sql, tuple(params))

    def get_open_session(self, vin: str, exclude_id: int | None = None) -> dict | None:
        """The earliest genuinely-OUT live session for a car: a live Test Drive
        (source='td_form') that's been handed over (status='FILLED') and not yet
        returned. Drives the single-open-session rule — you can't start a new
        session while one is out. Excludes `exclude_id` (the row being
        activated). NOTE: batch/allocation rows (source='batch') are also
        'FILLED' but carry both odometers at creation and are never returned —
        they are NOT live sessions and must not block, hence the source filter."""
        params = [vin]
        excl = ''
        if exclude_id is not None:
            excl = ' AND fp.id <> %s'
            params.append(exclude_id)
        sql = (
            "SELECT fp.id, fp.route_type, fp.departure_datetime, "
            "COALESCE(fp.client_name, c.name) AS client_name, fp.advisor_name "
            "FROM foi_de_parcurs fp LEFT JOIN fp_clients c ON c.id = fp.client_id "
            f"WHERE fp.vin = %s AND fp.status = 'FILLED' AND fp.source = 'td_form'{excl} "
            "ORDER BY fp.departure_datetime ASC NULLS LAST, fp.id ASC LIMIT 1"
        )
        return self.query_one(sql, tuple(params))

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
