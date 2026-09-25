"""Slot materialization + live availability for public test-drive booking.

TdSlotService turns a page's booking windows into concrete per-car slots
(materialize_slots) and, at read time, filters open slots down to the ones
that are actually bookable right now (available_slots), backed by the same
live availability check (is_car_free) used to gate a real test-drive: no
conflicting Foaie de Parcurs session, no lockout, no currently-open session on
the VIN, and no still-live pending TD hold overlapping the slot.
"""
from datetime import datetime, timedelta, timezone, date as ddate, time as dtime

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - py<3.9 fallback, unused in this repo
    from backports.zoneinfo import ZoneInfo

from marketing.repositories.td_booking_repository import TdBookingRepository
from foi_parcurs.repositories.foi_parcurs_repository import FoiParcursRepository
from foi_parcurs.repositories.vehicle_repository import FPVehicleRepository

_LOCAL_TZ = ZoneInfo('Europe/Bucharest')


class TdSlotService:
    def __init__(self):
        self.repo = TdBookingRepository()
        self.fp = FoiParcursRepository()
        self.veh = FPVehicleRepository()

    def materialize_slots(self, page_id: int) -> int:
        """Generate [start_time, end_time) slots of slot_minutes length
        (separated by buffer_minutes) for every active car on every window
        of the page, and bulk-insert them idempotently. Returns the number
        of newly-inserted rows (bulk_insert_slots no-ops on conflict)."""
        page = self.repo.get_page(page_id)
        if not page:
            return 0
        default_slot_minutes = page['slot_minutes']
        buffer_minutes = page['buffer_minutes']
        cars = self.repo.list_cars(page_id)
        windows = self.repo.list_windows(page_id)
        rows = []
        for w in windows:
            step = w.get('slot_minutes') or default_slot_minutes
            window_date = _as_date(w['window_date'])
            window_start = datetime.combine(
                window_date, _as_time(w['start_time']), tzinfo=_LOCAL_TZ)
            window_end = datetime.combine(
                window_date, _as_time(w['end_time']), tzinfo=_LOCAL_TZ)
            for car in cars:
                cursor_dt = window_start
                while cursor_dt + timedelta(minutes=step) <= window_end:
                    slot_end = cursor_dt + timedelta(minutes=step)
                    rows.append({
                        'page_id': page_id, 'car_id': car['id'], 'vin': car['vin'],
                        'starts_at': cursor_dt, 'ends_at': slot_end,
                    })
                    cursor_dt = slot_end + timedelta(minutes=buffer_minutes)
        return self.repo.bulk_insert_slots(rows)

    def is_car_free(self, vin: str, frm, to) -> bool:
        """The read-time availability check: no overlapping TD conflict, no
        effective lockout (manual or scheduled), no already-open session on the
        VIN, and no still-live pending TD hold overlapping [frm, to).

        The pending-hold check is what makes a `pending_confirm` booking actually
        reserve its interval until it confirms or its window expires: it has no
        foi_de_parcurs row yet, so the fp checks below can't see it, and without
        it an OVERLAPPING slot on the same car (e.g. the same VIN offered on
        another page) would look free while the hold is outstanding."""
        if self.fp.find_conflicts(vin, frm, to):
            return False
        lock = self.veh.get_lock_by_vin(vin)
        if lock and lock.get('locked_out'):
            return False
        if self.fp.get_open_session(vin):
            return False
        if self.repo.has_pending_overlap(vin, datetime.now(timezone.utc), frm, to):
            return False
        return True

    def available_slots(self, page_id: int, now: datetime) -> list:
        """Open slots for the page, filtered by lead time and live availability.
        Returns [{id, car_id, vin, starts_at, ends_at}, ...].

        Same four availability gates as is_car_free (lockout, open session, FP
        conflicts, pending holds) but computed in BULK -- once per distinct VIN,
        not once per slot. The per-VIN invariants (lockout, open session) run once;
        FP conflicts and pending holds are fetched across the VIN's whole slot span
        in a single query each, then overlap-checked in memory per slot. This
        replaces the old per-slot N x 4 query fan-out that made a large event's
        public page take seconds to open. list_open_slots' (car_id, starts_at)
        ordering is preserved."""
        page = self.repo.get_page(page_id)
        lead = timedelta(minutes=page['min_lead_minutes']) if page else timedelta()
        earliest = now + lead
        # Lead-time filter first, keeping list_open_slots' (car_id, starts_at) order.
        slots = [s for s in self.repo.list_open_slots(page_id)
                 if _as_datetime(s['starts_at']) >= earliest]
        if not slots:
            return []

        # Group surviving slots by VIN so each availability check runs once per car.
        by_vin: dict = {}
        for s in slots:
            by_vin.setdefault(s['vin'], []).append(s)

        now_utc = datetime.now(timezone.utc)  # real-now cutoff for pending-hold expiry
        # free_by_vin[vin] is None when the whole car is unavailable (locked or a
        # session is out), else (conflicts, holds) to overlap-check per slot in memory.
        free_by_vin: dict = {}
        for vin, vin_slots in by_vin.items():
            lock = self.veh.get_lock_by_vin(vin)
            if (lock and lock.get('locked_out')) or self.fp.get_open_session(vin):
                free_by_vin[vin] = None
                continue
            span_start = min(_as_datetime(s['starts_at']) for s in vin_slots)
            span_end = max(_as_datetime(s['ends_at']) for s in vin_slots)
            free_by_vin[vin] = (
                self.fp.find_conflicts(vin, span_start, span_end),
                self.repo.pending_hold_windows(vin, now_utc),
            )

        out = []
        for s in slots:  # original order preserved
            data = free_by_vin[s['vin']]
            if data is None:
                continue
            conflicts, holds = data
            st = _as_datetime(s['starts_at'])
            en = _as_datetime(s['ends_at'])
            # FP-conflict overlap is INCLUSIVE (mirror find_conflicts SQL):
            # existing.departure <= slot.end AND COALESCE(return, departure) >= slot.start.
            if any(_as_datetime(c['departure_datetime']) <= en
                   and _as_datetime(c.get('return_datetime') or c['departure_datetime']) >= st
                   for c in conflicts):
                continue
            # Pending-hold overlap is HALF-OPEN (mirror has_pending_overlap):
            # hold.start < slot.end AND hold.end > slot.start.
            if any(_as_datetime(h['starts_at']) < en and _as_datetime(h['ends_at']) > st
                   for h in holds):
                continue
            out.append({
                'id': s['id'], 'car_id': s['car_id'], 'vin': s['vin'],
                'starts_at': st, 'ends_at': en,
            })
        return out

    def free_open_slots(self, page_id: int) -> list:
        """list_open_slots (car mark/model/plate enriched) filtered by the live
        is_car_free check, so the admin reservation editor's move/swap picker only
        offers slots where the car is genuinely available -- matching the public
        form's real availability, not just TD-booking occupancy. No lead-time
        cutoff (staff may rebook near-term)."""
        return [
            s for s in self.repo.list_open_slots(page_id)
            if self.is_car_free(s['vin'], _as_datetime(s['starts_at']), _as_datetime(s['ends_at']))
        ]


# BaseRepository.query_one/query_all (via dict_from_row) serialize every date/time/
# datetime column to its ISO string on the way out, so values read back from the DB
# need parsing before they can be combined/compared as real date/time objects again.

def _as_date(v):
    return v if isinstance(v, ddate) else ddate.fromisoformat(str(v))


def _as_time(v):
    return v if isinstance(v, dtime) else dtime.fromisoformat(str(v))


def _as_datetime(v):
    return v if isinstance(v, datetime) else datetime.fromisoformat(str(v))
