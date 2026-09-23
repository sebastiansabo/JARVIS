"""Slot materialization + live availability for public test-drive booking.

TdSlotService turns a page's booking windows into concrete per-car slots
(materialize_slots) and, at read time, filters open slots down to the ones
that are actually bookable right now (available_slots), backed by the same
3-way live check (is_car_free) used to gate a real test-drive: no conflicting
Foaie de Parcurs session, no lockout, and no currently-open session on the VIN.
"""
from datetime import datetime, timedelta, date as ddate, time as dtime

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
        """The read-time 3-way live check: no overlapping TD conflict, no
        effective lockout (manual or scheduled), and no already-open session
        on the VIN."""
        if self.fp.find_conflicts(vin, frm, to):
            return False
        lock = self.veh.get_lock_by_vin(vin)
        if lock and lock.get('locked_out'):
            return False
        if self.fp.get_open_session(vin):
            return False
        return True

    def available_slots(self, page_id: int, now: datetime) -> list:
        """Open slots for the page, filtered by lead time and the live 3-way
        check. Returns [{id, car_id, vin, starts_at, ends_at}, ...]."""
        page = self.repo.get_page(page_id)
        lead = timedelta(minutes=page['min_lead_minutes']) if page else timedelta()
        earliest = now + lead
        out = []
        for s in self.repo.list_open_slots(page_id):
            starts_at = _as_datetime(s['starts_at'])
            ends_at = _as_datetime(s['ends_at'])
            if starts_at < earliest:
                continue
            if self.is_car_free(s['vin'], starts_at, ends_at):
                out.append({
                    'id': s['id'], 'car_id': s['car_id'], 'vin': s['vin'],
                    'starts_at': starts_at, 'ends_at': ends_at,
                })
        return out


# BaseRepository.query_one/query_all (via dict_from_row) serialize every date/time/
# datetime column to its ISO string on the way out, so values read back from the DB
# need parsing before they can be combined/compared as real date/time objects again.

def _as_date(v):
    return v if isinstance(v, ddate) else ddate.fromisoformat(str(v))


def _as_time(v):
    return v if isinstance(v, dtime) else dtime.fromisoformat(str(v))


def _as_datetime(v):
    return v if isinstance(v, datetime) else datetime.fromisoformat(str(v))
