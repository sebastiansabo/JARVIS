"""Data access for fp_vehicles table (foi de parcurs vehicle stock)."""

import logging
import re
from core.base_repository import BaseRepository
from ..document_types import normalize as _normalize_doctype

logger = logging.getLogger('jarvis.foi_parcurs.vehicle_repository')


def _normalize_plate(value):
    """Uppercase + collapse separators to canonical spaced RO plate; pass through unknowns.

    Standard civilian: county + 2 digits (3 for Bucharest) + 3 letters.
    Provisional (numere provizorii): county + 6-8 digits and NO letters — the
    digit run is kept intact (must mirror the frontend mask in plateFormat.ts).
    """
    if not value:
        return value
    s = re.sub(r'[^A-Za-z0-9]', '', str(value)).upper()
    if not s:
        return value
    if s == 'B' or (s[0] == 'B' and len(s) > 1 and s[1].isdigit()):
        county, rest = 'B', s[1:]
    else:
        county, rest = s[:2], s[2:]
    m = re.match(r'^(\d+)([A-Z]+)?$', rest)
    if not m:
        return value
    letters = (m.group(2) or '')[:3]
    if letters:
        # Standard plate — the digit group is bounded (2, or 3 for Bucharest).
        max_d = 3 if county == 'B' else 2
        digits = m.group(1)[:max_d]
    else:
        # Provisional plate — keep the full digit run (up to 8).
        digits = m.group(1)[:8]
    return ' '.join(p for p in (county, digits, letters) if p)


class FPVehicleRepository(BaseRepository):

    # Lean list SELECT — every scalar the Driving Park table renders, but NONE of
    # the base64 document uploads (insurance_doc/talon_doc/civ_doc/registration_doc/
    # offer_doc) which are avg ~1.5 MB/row (offer PDF alone up to 7 MB). The list
    # never shows them; the detail endpoint (get_by_id) returns the full row for
    # the edit form / document view.
    _LIST_SELECT = (
        'SELECT v.id, v.vin, v.mark, v.brand, v.model, v.color, v.fuel_type, '
        'v.fuel_tank_capacity_liters, v.battery_capacity_kwh, v.odometer_km, '
        'v.norma_combustibil, v.norma_energie, v.category, '
        'v.company_id, v.car_id, v.registration_number, v.is_active, '
        'v.document_type, '
        # Service (Mașini de curtoazie) price + policy so the Driving Park list
        # and the Tarife price-list can show/edit all 6 svc_ fields without a
        # per-row fetch of the full vehicle document blobs (avoids an N+1 and a
        # Save-before-load null race in the Tarife editor). Tiny numerics —
        # harmless to other list consumers.
        'v.svc_tariff_eur_day, v.svc_tariff_eur_month, v.rental_category_id, '
        'v.svc_km_included_day, v.svc_extra_km_eur, '
        'v.svc_deposit_eur, v.svc_franchise_eur, '
        # Lockout state so the Driving Park + session car pickers can show a car
        # as blocked (disabled) with its reason.
        'v.locked_out, v.lockout_category, v.lockout_note, v.lockout_until, '
        # Archival reason so the Driving Park can show why an archived car left.
        'v.archive_category, v.archive_note, v.archived_at, '
        # Scheduled-block awareness so pickers/tables can show a car blocked by a
        # window (blocked_now) and flag an upcoming one, without pulling the table.
        '(ab.active_block_end IS NOT NULL) AS blocked_now, '
        'ab.active_block_category, ab.active_block_end, '
        'nb.next_block_start, nb.next_block_end, '
        # Live-session awareness: is the car currently OUT on a handed-over test
        # drive? Mirrors FPRepository.get_open_session (FILLED + source='td_form',
        # not the never-returned 'batch' comodat rows) so the Driving Park shows
        # "Pe drum" instead of a false "Disponibil" for a car at a client now.
        '(od.on_drive_id IS NOT NULL) AS on_drive, '
        'od.on_drive_client, od.on_drive_until, '
        'v.created_at, v.updated_at, v.vignette_valid_until, v.itp_valid_until, '
        'v.insurance_valid_until, c.company AS company_name, '
        # Cheap doc-availability flags so clients (mobile Parc Auto) know which
        # documents exist without pulling the base64 blobs.
        '(v.insurance_doc IS NOT NULL) AS has_insurance, '
        '(v.talon_doc IS NOT NULL) AS has_talon, '
        '(v.civ_doc IS NOT NULL) AS has_civ, '
        '(v.registration_doc IS NOT NULL) AS has_registration, '
        '(v.offer_doc IS NOT NULL) AS has_offer, '
        # Highest known mileage for the car: its stored odometer vs the greatest
        # km_end across its real (non-draft) sessions. Lets the TD form start a
        # session at the car's true latest reading and warn on anything lower.
        "GREATEST(COALESCE(v.odometer_km, 0), COALESCE("
        "(SELECT MAX(f.km_end) FROM foi_de_parcurs f "
        "WHERE f.vin = v.vin AND f.status <> 'PLANNED'), 0)) AS mileage_floor, "
        # Next up-to-3 PLANNED sessions for the car, so the Driving Park can show
        # an upcoming-bookings chip without a separate round-trip.
        "COALESCE(up.upcoming_planned, '[]'::json) AS upcoming_planned "
        'FROM fp_vehicles v '
        'LEFT JOIN companies c ON c.id = v.company_id '
        'LEFT JOIN LATERAL ('
        '  SELECT b.category AS active_block_category, b.end_date AS active_block_end '
        '  FROM fp_vehicle_blocks b '
        '  WHERE b.vehicle_id = v.id AND b.is_active '
        '    AND CURRENT_DATE BETWEEN b.start_date AND b.end_date '
        '  ORDER BY b.end_date DESC LIMIT 1'
        ') ab ON TRUE '
        'LEFT JOIN LATERAL ('
        '  SELECT b.start_date AS next_block_start, b.end_date AS next_block_end '
        '  FROM fp_vehicle_blocks b '
        '  WHERE b.vehicle_id = v.id AND b.is_active AND b.start_date > CURRENT_DATE '
        '  ORDER BY b.start_date ASC LIMIT 1'
        ') nb ON TRUE '
        'LEFT JOIN LATERAL ('
        '  SELECT s.id AS on_drive_id, '
        '         COALESCE(s.client_name, oc.name) AS on_drive_client, '
        '         s.return_datetime AS on_drive_until '
        '  FROM foi_de_parcurs s LEFT JOIN fp_clients oc ON oc.id = s.client_id '
        "  WHERE s.vin = v.vin AND s.status = 'FILLED' AND s.source = 'td_form' "
        '  ORDER BY s.departure_datetime ASC NULLS LAST, s.id ASC LIMIT 1'
        ') od ON TRUE '
        'LEFT JOIN LATERAL ('
        "  SELECT json_agg(json_build_object('departure', s.departure_datetime, 'client', s.client_name) ORDER BY s.departure_datetime) AS upcoming_planned "
        '  FROM (SELECT departure_datetime, client_name FROM foi_de_parcurs f '
        "         WHERE f.vin = v.vin AND f.status = 'PLANNED' "
        '         ORDER BY f.departure_datetime ASC NULLS LAST LIMIT 3) s'
        ') up ON TRUE'
    )

    def report_fleet(self, company_id=None, document_type=None, odo_order='high', top=5, brand=None):
        """Fleet composition for the Rapoarte tab: active-car count by fuel type,
        and the top-N cars by known mileage. `odo_order` 'high' (default) lists
        the most-driven cars, 'low' the least. Scoped to active cars of the given
        company + document-type pool (+ franchise brand when set). Company scope is
        enforced by the route."""
        clauses = ['v.is_active = TRUE']
        params = []
        if company_id:
            clauses.append('v.company_id = %s')
            params.append(company_id)
        if document_type:
            clauses.append('v.document_type = %s')
            params.append(document_type)
        if brand:
            clauses.append("COALESCE(NULLIF(TRIM(v.brand), ''), NULLIF(TRIM(v.mark), ''), 'Necunoscut') = %s")
            params.append(brand)
        where = ' WHERE ' + ' AND '.join(clauses)

        fuel_composition = self.query_all(
            "SELECT COALESCE(NULLIF(TRIM(v.fuel_type), ''), 'Necunoscut') AS fuel_type, "
            'COUNT(*)::int AS count '
            f'FROM fp_vehicles v{where} GROUP BY 1 ORDER BY 2 DESC', tuple(params))

        # whitelisted direction — odo_order is validated to 'high'/'low' upstream
        direction = 'ASC' if str(odo_order).lower() == 'low' else 'DESC'
        top_odometer = self.query_all(
            'SELECT v.vin, v.registration_number, '
            "COALESCE(NULLIF(TRIM(v.mark || ' ' || v.model), ''), v.model, 'Necunoscut') AS model, "
            'GREATEST(COALESCE(v.odometer_km, 0), COALESCE('
            "(SELECT MAX(f.km_end) FROM foi_de_parcurs f WHERE f.vin = v.vin AND f.status <> 'PLANNED'), 0))::int AS odometer_km "
            f'FROM fp_vehicles v{where} ORDER BY odometer_km {direction} LIMIT %s',
            tuple(params) + (top,))

        return {'fuel_composition': fuel_composition, 'top_odometer': top_odometer}

    def get_all(self, active_only=True, document_type=None):
        """Get all vehicles (lean — no document blobs), optionally active-only
        and/or filtered to a single document_type pool (sales/service).
        document_type=None (default) returns all pools — back-compat for
        management views that need the whole fleet."""
        where_clauses = []
        params = []
        if active_only:
            where_clauses.append('v.is_active = TRUE')
        if document_type:
            where_clauses.append('v.document_type = %s')
            params.append(document_type)
        where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ''
        return self.query_all(
            f'{self._LIST_SELECT}{where_sql} ORDER BY v.mark, v.model, v.vin',
            tuple(params) if params else None,
        )

    def get_by_vin(self, vin):
        """Get a single vehicle by VIN (full row, incl. documents)."""
        return self.query_one('SELECT * FROM fp_vehicles WHERE vin = %s', (vin,))

    def get_by_id(self, vehicle_id):
        """Get a single vehicle by ID (full row, incl. documents)."""
        return self.query_one('SELECT * FROM fp_vehicles WHERE id = %s', (vehicle_id,))

    def create(self, data):
        """Insert a new vehicle."""
        return self.execute(
            '''INSERT INTO fp_vehicles
               (vin, registration_number, car_id, mark, brand, model, color,
                fuel_type, fuel_tank_capacity_liters, battery_capacity_kwh, odometer_km,
                norma_combustibil, norma_energie, category, company_id, document_type,
                vignette_valid_until, itp_valid_until, insurance_valid_until,
                insurance_doc, talon_doc, civ_doc, registration_doc, offer_doc,
                svc_tariff_eur_day, svc_tariff_eur_month, svc_km_included_day,
                svc_extra_km_eur, svc_deposit_eur, svc_franchise_eur, rental_category_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s, %s, %s, %s) RETURNING *''',
            (data['vin'], _normalize_plate(data.get('registration_number')), data.get('car_id'),
             data['mark'], data.get('brand'), data['model'], data.get('color'),
             data.get('fuel_type', 'Diesel'),
             data.get('fuel_tank_capacity_liters'),
             data.get('battery_capacity_kwh'),
             data.get('odometer_km'),
             data.get('norma_combustibil'),
             data.get('norma_energie'),
             data.get('category'),
             data.get('company_id'),
             _normalize_doctype(data.get('document_type')),
             data.get('vignette_valid_until'), data.get('itp_valid_until'),
             data.get('insurance_valid_until'), data.get('insurance_doc'),
             data.get('talon_doc'), data.get('civ_doc'), data.get('registration_doc'),
             data.get('offer_doc'),
             data.get('svc_tariff_eur_day'), data.get('svc_tariff_eur_month'),
             data.get('svc_km_included_day'), data.get('svc_extra_km_eur'),
             data.get('svc_deposit_eur'), data.get('svc_franchise_eur'),
             data.get('rental_category_id')),
            returning=True,
        )

    def update(self, vehicle_id, data):
        """Update a vehicle."""
        sets = []
        params = []
        for col in ('vin', 'registration_number', 'car_id', 'mark', 'brand', 'model', 'color',
                    'fuel_type', 'fuel_tank_capacity_liters', 'battery_capacity_kwh', 'odometer_km',
                    'norma_combustibil', 'norma_energie', 'category', 'company_id', 'is_active',
                    'document_type',
                    'vignette_valid_until', 'itp_valid_until', 'insurance_valid_until',
                    'insurance_doc', 'talon_doc', 'civ_doc', 'registration_doc', 'offer_doc',
                    'svc_tariff_eur_day', 'svc_tariff_eur_month', 'svc_km_included_day',
                    'svc_extra_km_eur', 'svc_deposit_eur', 'svc_franchise_eur',
                    'rental_category_id'):
            if col in data:
                sets.append(f'{col} = %s')
                if col == 'registration_number':
                    value = _normalize_plate(data[col])
                elif col == 'document_type':
                    value = _normalize_doctype(data[col])
                else:
                    value = data[col]
                params.append(value)
        if not sets:
            return None
        sets.append('updated_at = NOW()')
        params.append(vehicle_id)
        sql = f"UPDATE fp_vehicles SET {', '.join(sets)} WHERE id = %s RETURNING *"
        return self.execute(sql, tuple(params), returning=True)

    def delete(self, vehicle_id):
        """Soft-delete (set is_active=FALSE)."""
        return self.execute(
            'UPDATE fp_vehicles SET is_active = FALSE, updated_at = NOW() WHERE id = %s',
            (vehicle_id,),
        )

    def get_documents_expiring(self, days_ahead: int = 30) -> list:
        """Active cars whose Rovinietă / RCA / ITP is expired or within
        `days_ahead`. One row per (car, document): {id, vin, mark, model,
        registration_number, company_id, doc, valid_until, days} — `days` is
        negative when the document has already expired."""
        return self.query_all(
            '''
            SELECT id, vin, mark, model, registration_number, company_id,
                   'Rovinietă' AS doc, vignette_valid_until AS valid_until,
                   (vignette_valid_until - CURRENT_DATE) AS days
              FROM fp_vehicles
             WHERE is_active AND vignette_valid_until IS NOT NULL
               AND vignette_valid_until <= CURRENT_DATE + %s
            UNION ALL
            SELECT id, vin, mark, model, registration_number, company_id,
                   'RCA (asigurare)', insurance_valid_until,
                   (insurance_valid_until - CURRENT_DATE)
              FROM fp_vehicles
             WHERE is_active AND insurance_valid_until IS NOT NULL
               AND insurance_valid_until <= CURRENT_DATE + %s
            UNION ALL
            SELECT id, vin, mark, model, registration_number, company_id,
                   'ITP', itp_valid_until,
                   (itp_valid_until - CURRENT_DATE)
              FROM fp_vehicles
             WHERE is_active AND itp_valid_until IS NOT NULL
               AND itp_valid_until <= CURRENT_DATE + %s
            ORDER BY days
            ''',
            (days_ahead, days_ahead, days_ahead),
        )

    def archive_vehicle(self, vehicle_id, category, note):
        """Soft-delete a car WITH a reason: stores the reason slug, an optional
        note and the archival timestamp (mirrors lock_vehicle)."""
        return self.execute(
            '''UPDATE fp_vehicles
               SET is_active = FALSE, archive_category = %s, archive_note = %s,
                   archived_at = NOW(), updated_at = NOW()
               WHERE id = %s RETURNING *''',
            (category, note, vehicle_id),
            returning=True,
        )

    # ── Lockout: block a car from the driving park ──────────────────────────

    def lock_vehicle(self, vehicle_id, category, note, until, user_id):
        """Lock a car out of the driving park (blocks new sessions)."""
        row = self.execute(
            '''UPDATE fp_vehicles
               SET locked_out = TRUE, lockout_category = %s, lockout_note = %s,
                   lockout_until = %s, locked_by = %s, locked_at = NOW(), updated_at = NOW()
               WHERE id = %s RETURNING *''',
            (category, note, until, user_id, vehicle_id),
            returning=True,
        )
        if row:
            self._log_lock_event(vehicle_id, 'lock', category, note, until, user_id)
        return row

    def unlock_vehicle(self, vehicle_id, user_id=None):
        """Clear a car's lockout, making it available again. `user_id` is the
        acting user, recorded in the audit trail as who unblocked the car."""
        # Snapshot the reason being cleared BEFORE the wipe, so the 'unlock'
        # event records what the car was unblocked from.
        prev = self.query_one(
            'SELECT lockout_category, lockout_note, lockout_until FROM fp_vehicles WHERE id = %s',
            (vehicle_id,),
        ) or {}
        row = self.execute(
            '''UPDATE fp_vehicles
               SET locked_out = FALSE, lockout_category = NULL, lockout_note = NULL,
                   lockout_until = NULL, locked_by = NULL, locked_at = NULL, updated_at = NOW()
               WHERE id = %s RETURNING *''',
            (vehicle_id,),
            returning=True,
        )
        if row:
            self._log_lock_event(
                vehicle_id, 'unlock',
                prev.get('lockout_category'), prev.get('lockout_note'),
                prev.get('lockout_until'), user_id,
            )
        return row

    # ── Lock/unlock audit trail (fp_vehicle_lock_events) ────────────────────
    def _actor_name(self, user_id):
        """Display name for a user id (snapshotted into the event); None if the
        action was unauthenticated/system or the user is unknown."""
        if not user_id:
            return None
        row = self.query_one('SELECT name FROM users WHERE id = %s', (user_id,))
        return row['name'] if row else None

    def _log_lock_event(self, vehicle_id, action, category, note, until, user_id):
        """Append one row to a car's lock/unlock history. Best-effort: an audit
        write must never break the lock/unlock it records, so failures (e.g. a
        missing table on a stale DB) are swallowed and logged."""
        try:
            self.execute(
                '''INSERT INTO fp_vehicle_lock_events
                       (vehicle_id, action, category, note, until, actor_id, actor_name)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                (vehicle_id, action, category, note, until, user_id, self._actor_name(user_id)),
            )
        except Exception:
            logger.warning('fp lock-event log failed for vehicle %s (%s)', vehicle_id, action, exc_info=True)

    def get_lock_events(self, vehicle_id):
        """A car's block/unblock audit trail, newest first — for the lock modal."""
        return self.query_all(
            '''SELECT id, action, category, note, until, actor_id, actor_name, created_at
               FROM fp_vehicle_lock_events
               WHERE vehicle_id = %s
               ORDER BY created_at DESC, id DESC''',
            (vehicle_id,),
        )

    def get_lock_by_vin(self, vin):
        """Effective lockout for a VIN: a manual lockout OR an active scheduled
        block window (CURRENT_DATE within [start,end] of an active block). Manual
        lock takes precedence. Shape matches the old manual-only return so the TD
        gates (test_drive.py) work unchanged; adds `lock_source`."""
        return self.query_one(
            '''
            SELECT
                (v.locked_out OR b.id IS NOT NULL) AS locked_out,
                CASE WHEN v.locked_out THEN v.lockout_category ELSE b.category END AS lockout_category,
                CASE WHEN v.locked_out THEN v.lockout_note     ELSE b.note     END AS lockout_note,
                CASE WHEN v.locked_out THEN v.lockout_until     ELSE b.end_date END AS lockout_until,
                CASE WHEN v.locked_out THEN 'manual'
                     WHEN b.id IS NOT NULL THEN 'scheduled' END AS lock_source
            FROM fp_vehicles v
            LEFT JOIN LATERAL (
                SELECT id, category, note, end_date
                FROM fp_vehicle_blocks
                WHERE vehicle_id = v.id AND is_active
                  AND CURRENT_DATE BETWEEN start_date AND end_date
                ORDER BY end_date DESC LIMIT 1
            ) b ON TRUE
            WHERE v.vin = %s
            ''',
            (vin,),
        )

    # ── Scheduled blocks (to-do #3): future date-windows that auto-block a car ──

    def get_identity(self, vehicle_id):
        """Lean identity row for a car (no document blobs) for block routes/cron."""
        return self.query_one(
            'SELECT id, vin, company_id, mark, model, registration_number '
            'FROM fp_vehicles WHERE id = %s',
            (vehicle_id,),
        )

    def list_scheduled_blocks(self, vehicle_id):
        """All block windows for a car (newest first) with a computed state."""
        return self.query_all(
            '''
            SELECT id, vehicle_id, category, note, start_date, end_date,
                   is_active, created_by, created_at,
                   CASE WHEN NOT is_active THEN 'cancelled'
                        WHEN CURRENT_DATE > end_date THEN 'past'
                        WHEN CURRENT_DATE BETWEEN start_date AND end_date THEN 'active'
                        ELSE 'upcoming' END AS state
            FROM fp_vehicle_blocks
            WHERE vehicle_id = %s
            ORDER BY start_date DESC, id DESC
            ''',
            (vehicle_id,),
        )

    def create_scheduled_block(self, vehicle_id, category, note, start_date, end_date, user_id):
        return self.execute(
            '''INSERT INTO fp_vehicle_blocks
                 (vehicle_id, category, note, start_date, end_date, created_by)
               VALUES (%s, %s, %s, %s, %s, %s) RETURNING *''',
            (vehicle_id, category, note, start_date, end_date, user_id),
            returning=True,
        )

    def get_scheduled_block(self, block_id):
        return self.query_one('SELECT * FROM fp_vehicle_blocks WHERE id = %s', (block_id,))

    def cancel_scheduled_block(self, block_id):
        """Soft-cancel a scheduled block (keeps history)."""
        return self.execute(
            'UPDATE fp_vehicle_blocks SET is_active = FALSE, updated_at = NOW() '
            'WHERE id = %s RETURNING *',
            (block_id,),
            returning=True,
        )

    def get_blocks_starting_or_ending_today(self):
        """Active blocks whose window starts or ends today (for the notify cron)."""
        return self.query_all(
            '''
            SELECT b.id, b.vehicle_id, b.category, b.start_date, b.end_date,
                   v.vin, v.mark, v.model, v.registration_number, v.company_id,
                   CASE WHEN b.start_date = CURRENT_DATE THEN 'start' ELSE 'end' END AS boundary
            FROM fp_vehicle_blocks b
            JOIN fp_vehicles v ON v.id = b.vehicle_id
            WHERE b.is_active
              AND (b.start_date = CURRENT_DATE OR b.end_date = CURRENT_DATE)
            ORDER BY b.vehicle_id
            ''',
        )

    # ── Lockout reasons (configurable, editable in Settings) ────────────────

    def list_lockout_reasons(self, active_only=False):
        """All lockout reasons ordered for display. active_only for the picker."""
        where = 'WHERE is_active = TRUE' if active_only else ''
        return self.query_all(
            f'SELECT id, slug, label, sort_order, is_active '
            f'FROM fp_lockout_reasons {where} ORDER BY sort_order, label'
        )

    def get_active_lockout_slugs(self):
        """Slugs currently valid for locking a car (for lock-endpoint validation)."""
        rows = self.query_all('SELECT slug FROM fp_lockout_reasons WHERE is_active = TRUE')
        return {r['slug'] for r in (rows or [])}

    def slug_exists(self, slug):
        return self.query_one('SELECT 1 FROM fp_lockout_reasons WHERE slug = %s', (slug,)) is not None

    def create_lockout_reason(self, slug, label, sort_order=0):
        return self.execute(
            '''INSERT INTO fp_lockout_reasons (slug, label, sort_order)
               VALUES (%s, %s, %s) RETURNING *''',
            (slug, label, sort_order),
            returning=True,
        )

    def get_lockout_reason(self, reason_id):
        return self.query_one('SELECT * FROM fp_lockout_reasons WHERE id = %s', (reason_id,))

    def update_lockout_reason(self, reason_id, label, sort_order, is_active):
        return self.execute(
            '''UPDATE fp_lockout_reasons
               SET label = %s, sort_order = %s, is_active = %s, updated_at = NOW()
               WHERE id = %s RETURNING *''',
            (label, sort_order, is_active, reason_id),
            returning=True,
        )

    # ── Archive reasons (configurable, editable in Settings → Motive arhivare) ─

    def list_archive_reasons(self, active_only=False):
        """All archive reasons ordered for display. active_only for the picker."""
        where = 'WHERE is_active = TRUE' if active_only else ''
        return self.query_all(
            f'SELECT id, slug, label, sort_order, is_active '
            f'FROM fp_archive_reasons {where} ORDER BY sort_order, label'
        )

    def get_active_archive_slugs(self):
        """Slugs currently valid for archiving a car (for archive-endpoint validation)."""
        rows = self.query_all('SELECT slug FROM fp_archive_reasons WHERE is_active = TRUE')
        return {r['slug'] for r in (rows or [])}

    def archive_slug_exists(self, slug):
        return self.query_one('SELECT 1 FROM fp_archive_reasons WHERE slug = %s', (slug,)) is not None

    def create_archive_reason(self, slug, label, sort_order=0):
        return self.execute(
            '''INSERT INTO fp_archive_reasons (slug, label, sort_order)
               VALUES (%s, %s, %s) RETURNING *''',
            (slug, label, sort_order),
            returning=True,
        )

    def get_archive_reason(self, reason_id):
        return self.query_one('SELECT * FROM fp_archive_reasons WHERE id = %s', (reason_id,))

    def update_archive_reason(self, reason_id, label, sort_order, is_active):
        return self.execute(
            '''UPDATE fp_archive_reasons
               SET label = %s, sort_order = %s, is_active = %s, updated_at = NOW()
               WHERE id = %s RETURNING *''',
            (label, sort_order, is_active, reason_id),
            returning=True,
        )
