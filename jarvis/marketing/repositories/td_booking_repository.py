"""Repository for the public test-drive booking layer (mkt_td_* tables)."""
from core.base_repository import BaseRepository
from foi_parcurs.session_lifecycle import GRACE_HOURS, NOW_LOCAL_SQL


class TdConflict(Exception):
    """Raised when a booking cannot be confirmed because the car is no longer free
    (overlapping TD session, vehicle locked/blocked, already out, or the booking is
    no longer in a confirmable state). Signals the caller to return HTTP 409."""


class TdBookingNotPending(TdConflict):
    """Raised specifically by confirm_booking_atomic's FOR-UPDATE guard when the
    booking is no longer 'pending_confirm' by the time the advisory lock is held
    (e.g. a racing/duplicate confirm already committed 'confirmed', or a cancel/
    expire fired). IS-A TdConflict for backward compatibility, but lets the service
    distinguish "someone else already finished this booking" (idempotent) from a
    genuine car-availability conflict (which must mark the booking 'conflict')."""

_PAGE_COLS = {
    'project_id', 'company_id', 'event_id', 'slug', 'status', 'opens_at',
    'closes_at', 'min_lead_minutes', 'slot_minutes', 'buffer_minutes',
    'max_bookings_per_contact', 'access_code', 'title', 'intro', 'thank_you',
    'notify_user_ids', 'created_by',
}

_BOOKING_COLS = {
    'page_id', 'slot_id', 'car_id', 'customer_name', 'customer_phone_e164',
    'customer_email', 'advisor_user_id', 'expires_at', 'extra_answers',
    'utm', 'ip', 'user_agent',
}


class TdBookingRepository(BaseRepository):
    # ---- pages ----
    def create_page(self, data: dict) -> dict:
        fields = {k: v for k, v in data.items() if k in _PAGE_COLS}
        cols = ', '.join(fields)
        ph = ', '.join(['%s'] * len(fields))
        return self.execute(
            f'INSERT INTO mkt_td_booking_pages ({cols}) VALUES ({ph}) RETURNING *',
            tuple(fields.values()), returning=True)

    def get_page(self, page_id: int):
        return self.query_one('SELECT * FROM mkt_td_booking_pages WHERE id=%s', (page_id,))

    def get_page_by_slug(self, slug: str):
        return self.query_one(
            'SELECT * FROM mkt_td_booking_pages WHERE slug=%s AND deleted_at IS NULL', (slug,))

    def get_company_name(self, company_id: int):
        row = self.query_one('SELECT company FROM companies WHERE id=%s', (company_id,))
        return row['company'] if row else None

    def list_pages(self, company_id=None):
        if company_id:
            return self.query_all(
                'SELECT * FROM mkt_td_booking_pages WHERE company_id=%s AND deleted_at IS NULL '
                'ORDER BY created_at DESC', (company_id,))
        return self.query_all(
            'SELECT * FROM mkt_td_booking_pages WHERE deleted_at IS NULL ORDER BY created_at DESC')

    def update_page(self, page_id: int, data: dict):
        fields = {k: v for k, v in data.items() if k in _PAGE_COLS}
        if not fields:
            return self.get_page(page_id)
        sets = ', '.join(f'{k}=%s' for k in fields)
        return self.execute(
            f'UPDATE mkt_td_booking_pages SET {sets}, updated_at=NOW() WHERE id=%s RETURNING *',
            tuple(fields.values()) + (page_id,), returning=True)

    def set_page_status(self, page_id: int, status: str):
        return self.execute(
            'UPDATE mkt_td_booking_pages SET status=%s, updated_at=NOW() WHERE id=%s RETURNING *',
            (status, page_id), returning=True)

    # ---- cars ----
    def add_car(self, page_id, vin, vehicle_id=None, default_advisor_user_id=None, sort_order=0):
        return self.execute(
            'INSERT INTO mkt_td_booking_cars (page_id, vin, vehicle_id, default_advisor_user_id, sort_order) '
            'VALUES (%s,%s,%s,%s,%s) RETURNING *',
            (page_id, vin, vehicle_id, default_advisor_user_id, sort_order), returning=True)

    def list_cars(self, page_id):
        return self.query_all(
            'SELECT * FROM mkt_td_booking_cars WHERE page_id=%s AND is_active ORDER BY sort_order, id',
            (page_id,))

    def get_car(self, car_id):
        return self.query_one('SELECT * FROM mkt_td_booking_cars WHERE id=%s', (car_id,))

    def remove_car(self, car_id):
        return self.execute('UPDATE mkt_td_booking_cars SET is_active=FALSE WHERE id=%s', (car_id,))

    # ---- windows ----
    def add_window(self, page_id, window_date, start_time, end_time, slot_minutes=None):
        return self.execute(
            'INSERT INTO mkt_td_booking_windows (page_id, window_date, start_time, end_time, slot_minutes) '
            'VALUES (%s,%s,%s,%s,%s) RETURNING *',
            (page_id, window_date, start_time, end_time, slot_minutes), returning=True)

    def list_windows(self, page_id):
        return self.query_all(
            'SELECT * FROM mkt_td_booking_windows WHERE page_id=%s ORDER BY window_date, start_time',
            (page_id,))

    def delete_window(self, window_id):
        """Hard delete -- windows are just slot generators (no FK from
        mkt_td_slots to mkt_td_booking_windows), so removing one doesn't
        orphan anything; already-materialized slots are untouched."""
        return self.execute('DELETE FROM mkt_td_booking_windows WHERE id=%s', (window_id,))

    # ---- slots ----
    def bulk_insert_slots(self, rows: list) -> int:
        if not rows:
            return 0

        def _work(cursor):
            n = 0
            for r in rows:
                cursor.execute(
                    'INSERT INTO mkt_td_slots (page_id, car_id, vin, starts_at, ends_at) '
                    'VALUES (%s,%s,%s,%s,%s) ON CONFLICT (car_id, starts_at) DO NOTHING',
                    (r['page_id'], r['car_id'], r['vin'], r['starts_at'], r['ends_at']))
                n += cursor.rowcount
            return n
        return self.execute_many(_work)

    def list_open_slots(self, page_id: int) -> list:
        return self.query_all(
            "SELECT s.* FROM mkt_td_slots s "
            "WHERE s.page_id=%s AND s.status='open' "
            "AND NOT EXISTS (SELECT 1 FROM mkt_td_bookings b "
            "                WHERE b.slot_id=s.id AND b.status IN ('pending_confirm','confirmed')) "
            "ORDER BY s.car_id, s.starts_at", (page_id,))

    # ---- bookings ----
    def create_booking(self, data: dict) -> dict:
        """Whitelisted insert. Lets psycopg2.errors.UniqueViolation propagate when the
        partial-unique index uq_mkt_td_active_booking_per_slot rejects a second active
        booking on the same slot -- the service layer maps that to HTTP 409.
        """
        from psycopg2.extras import Json
        fields = {k: v for k, v in data.items() if k in _BOOKING_COLS}
        for k in ('extra_answers', 'utm'):
            if isinstance(fields.get(k), (dict, list)):
                fields[k] = Json(fields[k])
        cols = ', '.join(fields)
        ph = ', '.join(['%s'] * len(fields))
        return self.execute(
            f'INSERT INTO mkt_td_bookings ({cols}) VALUES ({ph}) RETURNING *',
            tuple(fields.values()), returning=True)

    def get_booking(self, booking_id):
        return self.query_one('SELECT * FROM mkt_td_bookings WHERE id=%s', (booking_id,))

    def list_bookings(self, page_id, status=None) -> list:
        if status:
            return self.query_all(
                'SELECT * FROM mkt_td_bookings WHERE page_id=%s AND status=%s ORDER BY created_at DESC',
                (page_id, status))
        return self.query_all(
            'SELECT * FROM mkt_td_bookings WHERE page_id=%s ORDER BY created_at DESC', (page_id,))

    def count_active_by_contact(self, phone, email) -> int:
        row = self.query_one(
            "SELECT COUNT(*) AS n FROM mkt_td_bookings "
            "WHERE (customer_phone_e164=%s OR customer_email=%s) "
            "AND status IN ('pending_confirm','confirmed')", (phone, email))
        return int(row['n']) if row else 0

    def count_recent_by_ip(self, ip, since) -> int:
        row = self.query_one(
            'SELECT COUNT(*) AS n FROM mkt_td_bookings WHERE ip=%s AND created_at >= %s',
            (ip, since))
        return int(row['n']) if row else 0

    def mark_confirmed(self, booking_id, crm_client_id, foi_de_parcurs_id, advisor_user_id) -> dict:
        return self.execute(
            "UPDATE mkt_td_bookings SET status='confirmed', crm_client_id=%s, "
            "foi_de_parcurs_id=%s, advisor_user_id=%s, confirmed_at=NOW(), updated_at=NOW() "
            "WHERE id=%s RETURNING *",
            (crm_client_id, foi_de_parcurs_id, advisor_user_id, booking_id), returning=True)

    def mark_cancelled(self, booking_id) -> dict:
        return self.execute(
            "UPDATE mkt_td_bookings SET status='cancelled', cancelled_at=NOW(), updated_at=NOW() "
            "WHERE id=%s RETURNING *", (booking_id,), returning=True)

    def mark_status(self, booking_id, status) -> dict:
        return self.execute(
            'UPDATE mkt_td_bookings SET status=%s, updated_at=NOW() WHERE id=%s RETURNING *',
            (status, booking_id), returning=True)

    def expire_pending(self, now) -> int:
        return self.execute(
            "UPDATE mkt_td_bookings SET status='expired', updated_at=NOW() "
            "WHERE status='pending_confirm' AND expires_at < %s", (now,))

    # ---- atomic confirm (race-safe) ----
    # These three checks together are the "3-way availability" recheck. The overlap
    # SQL mirrors FoiParcursRepository.find_conflicts (foi_parcurs_repository.py:725):
    # a live TD session on the VIN whose [departure, COALESCE(return, departure)]
    # window overlaps [frm, to] and is still open. The grace clause is byte-equivalent
    # to find_conflicts' -- both interpolate GRACE_HOURS and NOW_LOCAL_SQL from
    # foi_parcurs.session_lifecycle (currently 8h grace + Bucharest-local now), so the
    # confirm-time recheck and the read-time find_conflicts can never disagree on
    # whether a stale in-grace PLANNED row still blocks. Runtime values stay
    # parameterized (%s); only the server-controlled constants are f-string'd in.
    _CONFLICT_SQL = (
        "SELECT 1 FROM foi_de_parcurs fp "
        "WHERE fp.vin=%s AND fp.route_type='TD' "
        "AND fp.departure_datetime <= %s "
        "AND COALESCE(fp.return_datetime, fp.departure_datetime) >= %s "
        "AND (fp.status='PLANNED' OR (fp.status<>'COMPLETED' AND fp.status<>'PENDING')) "
        "AND fp.status<>'MISSED' "
        f"AND NOT (fp.status = 'PLANNED' AND fp.departure_datetime + INTERVAL '{GRACE_HOURS} hours' < {NOW_LOCAL_SQL}) "
        "LIMIT 1")
    _LOCK_SQL = (
        "SELECT 1 FROM fp_vehicles v WHERE v.vin=%s AND (v.locked_out=TRUE OR EXISTS "
        "(SELECT 1 FROM fp_vehicle_blocks b WHERE b.vehicle_id=v.id AND b.is_active "
        " AND CURRENT_DATE BETWEEN b.start_date AND b.end_date)) LIMIT 1")
    _OPEN_SQL = (
        "SELECT 1 FROM foi_de_parcurs fp "
        "WHERE fp.vin=%s AND fp.status='FILLED' AND fp.source='td_form' LIMIT 1")

    def confirm_booking_atomic(self, booking_id, vin, frm, to, fp_row: dict) -> dict:
        """Confirm a pending booking under a per-VIN advisory lock, re-running the
        3-way availability check on the confirm transaction's own cursor so the lock
        actually covers it, then creating the operational PLANNED foi_de_parcurs row
        and flipping the booking to 'confirmed' -- all in ONE transaction. Raises
        TdConflict (rolling everything back) if the booking is no longer pending or
        the car is no longer free.

        Known limitation (MVP): the advisory lock serializes concurrent *public*
        confirms for a VIN, but a staff-created FP insert does not take the lock, so a
        sub-second public-vs-staff window remains -- narrowed (not eliminated) by the
        in-txn recheck. Follow-up: add the same lock to the staff TD create path.
        """
        def _work(cursor):
            # Serialize all confirms for this VIN; released at txn end (commit/rollback).
            cursor.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', (vin,))
            # Guard: booking still confirmable (row-locked for the txn).
            cursor.execute('SELECT status FROM mkt_td_bookings WHERE id=%s FOR UPDATE',
                           (booking_id,))
            row = cursor.fetchone()
            if not row or row['status'] != 'pending_confirm':
                # Distinct subclass so the service can respond idempotently to a
                # racing/duplicate confirm instead of flipping a good booking to
                # 'conflict'. The 3 availability rechecks below still raise plain
                # TdConflict.
                raise TdBookingNotPending('booking not pending')
            # 3-way availability recheck, all on THIS cursor (inside the lock).
            cursor.execute(self._CONFLICT_SQL, (vin, to, frm))
            if cursor.fetchone():
                raise TdConflict('overlapping TD session')
            cursor.execute(self._LOCK_SQL, (vin,))
            if cursor.fetchone():
                raise TdConflict('vehicle locked/blocked')
            cursor.execute(self._OPEN_SQL, (vin,))
            if cursor.fetchone():
                raise TdConflict('vehicle already out')
            # Create the operational PLANNED FP row (column-driven insert).
            cols = list(fp_row.keys())
            ph = ', '.join(['%s'] * len(cols))
            cursor.execute(
                f"INSERT INTO foi_de_parcurs ({', '.join(cols)}) VALUES ({ph}) RETURNING id",
                tuple(fp_row[c] for c in cols))
            fp_id = cursor.fetchone()['id']
            cursor.execute(
                "UPDATE mkt_td_bookings SET status='confirmed', foi_de_parcurs_id=%s, "
                "confirmed_at=NOW(), updated_at=NOW() WHERE id=%s", (fp_id, booking_id))
            return {'fp_id': fp_id}
        return self.execute_many(_work)
