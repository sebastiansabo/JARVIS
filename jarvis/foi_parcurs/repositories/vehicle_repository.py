"""Data access for fp_vehicles table (foi de parcurs vehicle stock)."""

import logging
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.foi_parcurs.vehicle_repository')


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
        # Lockout state so the Driving Park + session car pickers can show a car
        # as blocked (disabled) with its reason.
        'v.locked_out, v.lockout_category, v.lockout_note, v.lockout_until, '
        # Archival reason so the Driving Park can show why an archived car left.
        'v.archive_category, v.archive_note, v.archived_at, '
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
        "WHERE f.vin = v.vin AND f.status <> 'PLANNED'), 0)) AS mileage_floor "
        'FROM fp_vehicles v '
        'LEFT JOIN companies c ON c.id = v.company_id'
    )

    def get_all(self, active_only=True):
        """Get all vehicles (lean — no document blobs), optionally active-only."""
        if active_only:
            return self.query_all(
                f'{self._LIST_SELECT} WHERE v.is_active = TRUE ORDER BY v.mark, v.model, v.vin'
            )
        return self.query_all(f'{self._LIST_SELECT} ORDER BY v.mark, v.model, v.vin')

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
                norma_combustibil, norma_energie, category, company_id,
                vignette_valid_until, itp_valid_until, insurance_valid_until,
                insurance_doc, talon_doc, civ_doc, registration_doc, offer_doc)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *''',
            (data['vin'], data.get('registration_number'), data.get('car_id'),
             data['mark'], data.get('brand'), data['model'], data.get('color'),
             data.get('fuel_type', 'Diesel'),
             data.get('fuel_tank_capacity_liters'),
             data.get('battery_capacity_kwh'),
             data.get('odometer_km'),
             data.get('norma_combustibil'),
             data.get('norma_energie'),
             data.get('category'),
             data.get('company_id'),
             data.get('vignette_valid_until'), data.get('itp_valid_until'),
             data.get('insurance_valid_until'), data.get('insurance_doc'),
             data.get('talon_doc'), data.get('civ_doc'), data.get('registration_doc'),
             data.get('offer_doc')),
            returning=True,
        )

    def update(self, vehicle_id, data):
        """Update a vehicle."""
        sets = []
        params = []
        for col in ('vin', 'registration_number', 'car_id', 'mark', 'brand', 'model', 'color',
                    'fuel_type', 'fuel_tank_capacity_liters', 'battery_capacity_kwh', 'odometer_km',
                    'norma_combustibil', 'norma_energie', 'category', 'company_id', 'is_active',
                    'vignette_valid_until', 'itp_valid_until', 'insurance_valid_until',
                    'insurance_doc', 'talon_doc', 'civ_doc', 'registration_doc', 'offer_doc'):
            if col in data:
                sets.append(f'{col} = %s')
                params.append(data[col])
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
        return self.execute(
            '''UPDATE fp_vehicles
               SET locked_out = TRUE, lockout_category = %s, lockout_note = %s,
                   lockout_until = %s, locked_by = %s, locked_at = NOW(), updated_at = NOW()
               WHERE id = %s RETURNING *''',
            (category, note, until, user_id, vehicle_id),
            returning=True,
        )

    def unlock_vehicle(self, vehicle_id):
        """Clear a car's lockout, making it available again."""
        return self.execute(
            '''UPDATE fp_vehicles
               SET locked_out = FALSE, lockout_category = NULL, lockout_note = NULL,
                   lockout_until = NULL, locked_by = NULL, locked_at = NULL, updated_at = NOW()
               WHERE id = %s RETURNING *''',
            (vehicle_id,),
            returning=True,
        )

    def get_lock_by_vin(self, vin):
        """Current lockout state for a VIN (for session-create validation)."""
        return self.query_one(
            'SELECT locked_out, lockout_category, lockout_note, lockout_until '
            'FROM fp_vehicles WHERE vin = %s',
            (vin,),
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
