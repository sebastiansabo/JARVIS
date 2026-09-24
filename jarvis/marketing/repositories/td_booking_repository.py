"""Repository for the public test-drive booking layer (mkt_td_* tables)."""
import psycopg2
import psycopg2.errors

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
    'conditions_text', 'logo_url', 'email_subject', 'email_body',
    'waitlist_email_subject', 'waitlist_email_body',
    'require_license_photo', 'notify_user_ids', 'created_by',
}

_BOOKING_COLS = {
    'page_id', 'slot_id', 'car_id', 'customer_name', 'customer_phone_e164',
    'customer_email', 'group_id', 'advisor_user_id', 'expires_at', 'extra_answers',
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

    def get_company_gdpr_text(self, company_id: int):
        """The tenant's configured GDPR text for the public consent checkbox
        (None when unset/missing)."""
        row = self.query_one('SELECT gdpr_text FROM companies WHERE id=%s', (company_id,))
        return row['gdpr_text'] if row else None

    def list_pages(self, company_id=None):
        if company_id:
            return self.query_all(
                'SELECT * FROM mkt_td_booking_pages WHERE company_id=%s AND deleted_at IS NULL '
                'ORDER BY created_at DESC', (company_id,))
        return self.query_all(
            'SELECT * FROM mkt_td_booking_pages WHERE deleted_at IS NULL ORDER BY created_at DESC')

    def soft_delete_page(self, page_id: int):
        """Archive an event page (deleted_at stamp). list_pages / get_page_by_slug
        already filter deleted_at IS NULL, so it drops from the list + frees the slug."""
        return self.execute(
            'UPDATE mkt_td_booking_pages SET deleted_at=NOW() WHERE id=%s AND deleted_at IS NULL '
            'RETURNING id', (page_id,), returning=True)

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

    def list_cars_with_vehicle(self, page_id):
        """Active cars for a page, each joined to its fp_vehicles row for a
        friendly make/model label + plate. The LATERAL prefers the explicit
        vehicle_id link, else falls back to matching by vin, and LIMIT 1
        guarantees exactly one (possibly all-NULL) vehicle row per car -- so a
        car whose fleet row is missing still comes back (the caller falls back
        to the VIN for the label). All runtime values stay parameterized."""
        return self.query_all(
            "SELECT c.id, c.vin, c.vehicle_id, "
            "       v.mark AS mark, v.model AS model, "
            "       v.registration_number AS registration_number "
            "FROM mkt_td_booking_cars c "
            "LEFT JOIN LATERAL ("
            "    SELECT mark, model, registration_number FROM fp_vehicles fv "
            "    WHERE fv.id = c.vehicle_id OR fv.vin = c.vin "
            "    ORDER BY (fv.id = c.vehicle_id) DESC NULLS LAST LIMIT 1"
            ") v ON TRUE "
            "WHERE c.page_id=%s AND c.is_active "
            "ORDER BY c.sort_order, c.id",
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
        # Enriched with the vehicle's mark/model/plate so the admin editor's
        # move/swap picker reads as a car, not a bare VIN (extra columns are
        # additive; the confirm/reassign callers only read s.*).
        return self.query_all(
            "SELECT s.*, v.mark, v.model, v.registration_number FROM mkt_td_slots s "
            "LEFT JOIN fp_vehicles v ON v.vin = s.vin "
            "WHERE s.page_id=%s AND s.status='open' "
            "AND NOT EXISTS (SELECT 1 FROM mkt_td_bookings b "
            "                WHERE b.slot_id=s.id AND b.status IN ('pending_confirm','confirmed')) "
            "ORDER BY s.car_id, s.starts_at", (page_id,))

    def count_slots(self, page_id: int) -> int:
        """Total materialized slots for a page (regardless of live availability) —
        drives the admin's 'no slots generated' warning."""
        row = self.query_one('SELECT COUNT(*) AS n FROM mkt_td_slots WHERE page_id=%s', (page_id,))
        return int(row['n']) if row else 0

    def list_events_for_calendar(self, company_id: int, date_from, date_to) -> list:
        """Active (draft/open) Event TD pages for a company, one row per (page,
        car), spanning the earliest→latest availability window that falls in
        [date_from, date_to]. Feeds the Driving Hub Calendar overlay so staff see
        which cars are committed to an event. Returns NAIVE local wall-clock
        timestamps (window_date + time, no zone): the calendar's naiveDate reads
        times as wall-clock and strips any zone, exactly as for a session's
        departure/return -- an AT TIME ZONE conversion here would shift the band
        (e.g. render a 10:00 window at 07:00)."""
        return self.query_all(
            "SELECT p.id AS page_id, p.title, p.slug, p.status, c.vin, "
            "       MIN(w.window_date + w.start_time) AS starts_at, "
            "       MAX(w.window_date + w.end_time)   AS ends_at "
            "FROM mkt_td_booking_pages p "
            "JOIN mkt_td_booking_cars c ON c.page_id = p.id AND c.is_active "
            "JOIN mkt_td_booking_windows w ON w.page_id = p.id "
            "WHERE p.company_id = %s AND p.deleted_at IS NULL AND p.status IN ('draft','open') "
            "  AND w.window_date BETWEEN %s AND %s "
            "GROUP BY p.id, p.title, p.slug, p.status, c.vin "
            "ORDER BY starts_at", (company_id, date_from, date_to))

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

    def create_bookings_group(self, rows: list) -> list:
        """Insert a batch of bookings that share one group_id (several
        car+interval slots booked together). Each row is inserted with the same
        per-row `create_booking` semantics + its own transaction, so a per-slot
        UniqueViolation (that slot was just taken by the partial-unique active
        index) skips ONLY that row -- the rest still commit. Returns the rows
        that were actually created (empty if every slot lost its race)."""
        created = []
        for row in rows:
            try:
                created.append(self.create_booking(row))
            except psycopg2.errors.UniqueViolation:
                continue
        return created

    def get_booking(self, booking_id):
        return self.query_one('SELECT * FROM mkt_td_bookings WHERE id=%s', (booking_id,))

    def get_group(self, group_id) -> list:
        return self.query_all(
            'SELECT * FROM mkt_td_bookings WHERE group_id=%s ORDER BY id', (group_id,))

    def list_bookings(self, page_id, status=None) -> list:
        # Resolve the booked car's vin/mark/model so the admin can see + filter
        # reservations by car ("who is on which car").
        base = (
            'SELECT b.*, car.vin AS car_vin, v.mark AS car_mark, v.model AS car_model '
            'FROM mkt_td_bookings b '
            'LEFT JOIN mkt_td_booking_cars car ON car.id = b.car_id '
            'LEFT JOIN fp_vehicles v ON v.vin = car.vin '
            'WHERE b.page_id=%s')
        if status:
            return self.query_all(base + ' AND b.status=%s ORDER BY b.created_at DESC', (page_id, status))
        return self.query_all(base + ' ORDER BY b.created_at DESC', (page_id,))

    def count_active_by_contact(self, phone, email) -> int:
        row = self.query_one(
            "SELECT COUNT(*) AS n FROM mkt_td_bookings "
            "WHERE (customer_phone_e164=%s OR customer_email=%s) "
            "AND status IN ('pending_confirm','confirmed')", (phone, email))
        return int(row['n']) if row else 0

    def count_active_groups_by_contact(self, phone, email) -> int:
        """Count a contact's active *groups* (not bookings): every booking that
        shares a group_id counts once, and each legacy NULL-group booking counts
        as its own group. This is what the per-contact limit is measured against,
        so a multi-slot group counts as ONE toward max_bookings_per_contact."""
        row = self.query_one(
            "SELECT COUNT(*) AS n FROM ("
            "  SELECT DISTINCT COALESCE(group_id, 'single-' || id::text) AS g "
            "  FROM mkt_td_bookings "
            "  WHERE (customer_phone_e164=%s OR customer_email=%s) "
            "  AND status IN ('pending_confirm','confirmed')"
            ") t", (phone, email))
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

    def mark_group_cancelled(self, group_id) -> int:
        """Cancel every still-active booking in a group (leaves already
        terminal ones -- expired/conflict/completed -- untouched). Returns the
        number of rows flipped to 'cancelled'."""
        return self.execute(
            "UPDATE mkt_td_bookings SET status='cancelled', cancelled_at=NOW(), updated_at=NOW() "
            "WHERE group_id=%s AND status IN ('pending_confirm','confirmed')", (group_id,))

    def mark_status(self, booking_id, status) -> dict:
        return self.execute(
            'UPDATE mkt_td_bookings SET status=%s, updated_at=NOW() WHERE id=%s RETURNING *',
            (status, booking_id), returning=True)

    def expire_pending(self, now) -> int:
        return self.execute(
            "UPDATE mkt_td_bookings SET status='expired', updated_at=NOW() "
            "WHERE status='pending_confirm' AND expires_at < %s", (now,))

    def has_pending_overlap(self, vin, now, frm, to) -> bool:
        """True when a still-live `pending_confirm` hold on `vin` overlaps [frm, to).

        A pending hold reserves its interval but has NOT yet created a
        foi_de_parcurs row, so the fp-based availability checks (find_conflicts /
        get_open_session) can't see it. Without this, an OVERLAPPING slot on the
        same car -- e.g. the same VIN offered on another page -- would look free
        until the hold is confirmed or its confirmation window expires. `now`
        (real current time) drops holds already past expires_at even if the expiry
        sweep hasn't run yet. Half-open overlap: slot.starts_at < to AND
        slot.ends_at > frm."""
        row = self.query_one(
            "SELECT 1 FROM mkt_td_bookings b "
            "JOIN mkt_td_slots s ON s.id = b.slot_id "
            "WHERE s.vin = %s AND b.status = 'pending_confirm' AND b.expires_at > %s "
            "AND s.starts_at < %s AND s.ends_at > %s LIMIT 1",
            (vin, now, to, frm))
        return row is not None

    # ---- waitlist ----
    _WAITLIST_COLS = ('page_id', 'customer_name', 'customer_phone_e164',
                      'customer_email', 'preferred_car_vin', 'note',
                      'gdpr_consent', 'ip')

    def create_waitlist_entry(self, data: dict) -> dict:
        fields = {k: data.get(k) for k in self._WAITLIST_COLS if k in data}
        cols = ', '.join(fields)
        ph = ', '.join(['%s'] * len(fields))
        return self.execute(
            f'INSERT INTO mkt_td_waitlist ({cols}) VALUES ({ph}) RETURNING *',
            tuple(fields.values()), returning=True)

    def list_waitlist(self, page_id: int) -> list:
        # Resolve the preferred car's mark/model so the admin sees "MG MGS9 PHEV
        # Luxury", not a bare VIN.
        return self.query_all(
            'SELECT w.*, v.mark AS preferred_car_mark, v.model AS preferred_car_model '
            'FROM mkt_td_waitlist w LEFT JOIN fp_vehicles v ON v.vin = w.preferred_car_vin '
            'WHERE w.page_id=%s ORDER BY w.created_at DESC', (page_id,))

    def count_recent_waitlist_by_ip(self, ip, since) -> int:
        row = self.query_one(
            'SELECT COUNT(*) AS n FROM mkt_td_waitlist WHERE ip=%s AND created_at >= %s',
            (ip, since))
        return int(row['n']) if row else 0

    def find_active_waitlist(self, page_id: int, phone: str) -> dict:
        """The still-open ('new') entry for this phone on this event, if any --
        used to keep a repeat submit idempotent instead of stacking rows."""
        return self.query_one(
            "SELECT * FROM mkt_td_waitlist WHERE page_id=%s AND customer_phone_e164=%s "
            "AND status='new' ORDER BY created_at DESC LIMIT 1", (page_id, phone))

    def set_waitlist_status(self, wid: int, status: str, handled_by=None) -> dict:
        return self.execute(
            "UPDATE mkt_td_waitlist SET status=%s, "
            "handled_at = CASE WHEN %s = 'new' THEN NULL ELSE NOW() END, "
            "handled_by = %s WHERE id=%s RETURNING *",
            (status, status, handled_by, wid), returning=True)

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

    def reassign_booking_atomic(self, booking_id, new_slot_id, new_car_id, new_advisor_id,
                                vin, frm, to, fp_row, old_fp_id) -> dict:
        """Move a booking to a different slot (a slot = car+interval, so this covers
        both time-move and car-swap) under the per-VIN advisory lock. Deletes the
        booking's old PLANNED fișă FIRST (so it can't self-conflict), re-runs the
        3-way availability check for the NEW car/time, re-points the booking (the
        partial-unique active-slot index guards a double-book -> TdConflict), and
        rebuilds the PLANNED fișă when the booking had one. Returns {'fp_id': id|None}."""
        def _work(cursor):
            cursor.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', (vin,))
            if old_fp_id:
                cursor.execute("DELETE FROM foi_de_parcurs WHERE id=%s AND status='PLANNED'", (old_fp_id,))
                if cursor.rowcount == 0:
                    # The linked fișă is no longer PLANNED (car handed over / drive in
                    # progress) — it survives the delete and the rebuild below would
                    # collide on the UNIQUE contract_id. Refuse rather than 500.
                    raise TdConflict('drive already in progress')
            cursor.execute(self._CONFLICT_SQL, (vin, to, frm))
            if cursor.fetchone():
                raise TdConflict('overlapping TD session')
            cursor.execute(self._LOCK_SQL, (vin,))
            if cursor.fetchone():
                raise TdConflict('vehicle locked/blocked')
            cursor.execute(self._OPEN_SQL, (vin,))
            if cursor.fetchone():
                raise TdConflict('vehicle already out')
            try:
                cursor.execute(
                    "UPDATE mkt_td_bookings SET slot_id=%s, car_id=%s, advisor_user_id=%s, "
                    "updated_at=NOW() WHERE id=%s", (new_slot_id, new_car_id, new_advisor_id, booking_id))
            except psycopg2.errors.UniqueViolation:
                # The active-slot partial-unique index rejected the move: that slot
                # is already held by another pending/confirmed booking.
                raise TdConflict('slot already booked')
            new_fp_id = None
            if fp_row is not None:
                cols = list(fp_row.keys())
                ph = ', '.join(['%s'] * len(cols))
                cursor.execute(
                    f"INSERT INTO foi_de_parcurs ({', '.join(cols)}) VALUES ({ph}) RETURNING id",
                    tuple(fp_row[c] for c in cols))
                new_fp_id = cursor.fetchone()['id']
                cursor.execute("UPDATE mkt_td_bookings SET foi_de_parcurs_id=%s WHERE id=%s",
                               (new_fp_id, booking_id))
            return {'fp_id': new_fp_id}
        return self.execute_many(_work)
